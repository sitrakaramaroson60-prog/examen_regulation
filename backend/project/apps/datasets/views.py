import csv

from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.common.permissions import ARTEC_REGULATOR, OPERATOR_USER, roles_required

from . import services
from .models import Dataset, DatasetSubmission, DatasetVersion
from .serializers import (
    DatasetSerializer,
    ReviewActionSerializer,
    SubmissionSerializer,
    VersionSerializer,
    VersionUploadSerializer,
)

DatasetWriters = roles_required(OPERATOR_USER, ARTEC_REGULATOR)


def visible_datasets(user):
    qs = Dataset.objects.select_related("owner_organization")
    if user.role == OPERATOR_USER:
        return qs.filter(owner_organization=user.organization)
    if user.role == ARTEC_REGULATOR:
        # Propres datasets de l'ARTEC + datasets d'opérateurs ayant fait l'objet d'une soumission
        from django.db.models import Q

        return qs.filter(Q(owner_organization=user.organization) | Q(versions__submissions__isnull=False)).distinct()
    return qs.none()


class DatasetViewSet(viewsets.ModelViewSet):
    serializer_class = DatasetSerializer
    permission_classes = [DatasetWriters]
    filterset_fields = ["data_type", "source_type"]
    search_fields = ["name", "description"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return visible_datasets(self.request.user)

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(owner_organization=user.organization, created_by=user)

    def _only_own(self, dataset):
        if dataset.owner_organization_id != self.request.user.organization_id:
            raise PermissionDenied("Ce dataset appartient à un autre organisme.")

    def perform_update(self, serializer):
        self._only_own(serializer.instance)
        serializer.save()

    @extend_schema(request=VersionUploadSerializer, responses={201: VersionSerializer})
    @action(detail=True, methods=["post", "get"], url_path="versions")
    def versions(self, request, pk=None):
        dataset = self.get_object()
        if request.method == "GET":
            return Response(VersionSerializer(dataset.versions.select_related("report", "dataset"), many=True).data)
        self._only_own(dataset)
        s = VersionUploadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        version = services.create_version(dataset, s.validated_data["file"], request.user, request)
        return Response(VersionSerializer(version).data, status=status.HTTP_201_CREATED)


class VersionViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = VersionSerializer
    permission_classes = [DatasetWriters]
    filterset_fields = ["dataset", "dataset__data_type"]
    pagination_class = None

    def get_queryset(self):
        return DatasetVersion.objects.select_related("report", "dataset__owner_organization").filter(dataset__in=visible_datasets(self.request.user))

    def _own(self, version):
        if version.dataset.owner_organization_id != self.request.user.organization_id:
            raise PermissionDenied("Opération réservée à l'organisme propriétaire.")

    @extend_schema(request=None, responses=VersionSerializer)
    @action(detail=True, methods=["post"])
    def validate(self, request, pk=None):
        version = self.get_object()
        self._own(version)
        services.revalidate(version)
        version.refresh_from_db()
        return Response(VersionSerializer(version).data)

    @extend_schema(request=None, responses=SubmissionSerializer)
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        version = self.get_object()
        self._own(version)
        if request.user.role != OPERATOR_USER:
            raise PermissionDenied("Seul un opérateur soumet un dataset à l'ARTEC.")
        sub = services.submit_version(version, request.user, request)
        return Response(SubmissionSerializer(sub).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses={200: None})
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        version = self.get_object()
        from apps.audit.services import log

        log(request.user, "dataset.downloaded", "DatasetVersion", version.pk, request=request)
        return FileResponse(version.file.open("rb"), as_attachment=True, filename=version.original_name)

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        version = self.get_object()
        df = services.load_dataframe(version).head(20)
        return Response({"columns": list(df.columns), "rows": df.where(df.notna(), None).values.tolist()})


class SubmissionViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Soumissions à l'ARTEC. Opérateur : les siennes. Régulation : toutes. Publications : aucun accès."""

    serializer_class = SubmissionSerializer
    permission_classes = [DatasetWriters]
    filterset_fields = ["status", "dataset_version__dataset__data_type"]
    search_fields = ["reference", "dataset_version__dataset__name"]
    ordering_fields = ["submitted_at", "status"]

    def get_queryset(self):
        qs = DatasetSubmission.objects.select_related("dataset_version__dataset__owner_organization", "dataset_version__report").prefetch_related("events__actor")
        user = self.request.user
        if user.role == OPERATOR_USER:
            return qs.filter(dataset_version__dataset__owner_organization=user.organization)
        if user.role == ARTEC_REGULATOR:
            return qs
        return qs.none()

    def _review(self, request, name):
        if request.user.role != ARTEC_REGULATOR:
            raise PermissionDenied("Examen réservé à ARTEC Régulation et Prédiction.")
        s = ReviewActionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        sub = services.review(self.get_object(), name, request.user, s.validated_data.get("comment", ""), request)
        return Response(SubmissionSerializer(sub).data)

    @extend_schema(request=ReviewActionSerializer, responses=SubmissionSerializer)
    @action(detail=True, methods=["post"], url_path="start-review")
    def start_review(self, request, pk=None):
        return self._review(request, "start-review")

    @extend_schema(request=ReviewActionSerializer, responses=SubmissionSerializer)
    @action(detail=True, methods=["post"], url_path="request-correction")
    def request_correction(self, request, pk=None):
        return self._review(request, "request-correction")

    @extend_schema(request=ReviewActionSerializer, responses=SubmissionSerializer)
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        return self._review(request, "accept")

    @extend_schema(request=ReviewActionSerializer, responses=SubmissionSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._review(request, "reject")
