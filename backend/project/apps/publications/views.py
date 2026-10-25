from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.permissions import ARTEC_PUBLISHER, ARTEC_REGULATOR, OPERATOR_USER, roles_required

from . import services
from .models import Comment, CommentReport, Publication, PublicationAttachment
from .permissions import REGULATOR_CATEGORIES, CanManagePublications
from .serializers import (
    AttachmentSerializer,
    AttachmentUploadSerializer,
    CommentModerationSerializer,
    CommentPublicSerializer,
    CommentReportSerializer,
    PublicationSerializer,
    PublicPublicationSerializer,
    SchedulePublicationSerializer,
)


def public_publications():
    return Publication.objects.filter(
        status=Publication.Status.PUBLISHED, audience=Publication.Audience.PUBLIC, published_at__lte=timezone.now()
    ).select_related("organization")


class PublicPublicationViewSet(viewsets.ReadOnlyModelViewSet):
    """Publications publiques (publiées, audience publique). Lecture anonyme autorisée."""

    permission_classes = [AllowAny]
    serializer_class = PublicPublicationSerializer
    lookup_field = "slug"
    filterset_fields = ["category", "organization__code"]
    search_fields = ["title", "content"]
    ordering_fields = ["published_at", "title"]

    def get_queryset(self):
        return public_publications()


class PublicationViewSet(viewsets.ModelViewSet):
    """Gestion des publications : chaque organisme gère les siennes."""

    serializer_class = PublicationSerializer
    permission_classes = [CanManagePublications]
    filterset_fields = ["status", "category", "audience"]
    search_fields = ["title", "content"]
    ordering_fields = ["created_at", "published_at", "title"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        qs = Publication.objects.select_related("organization").prefetch_related("attachments")
        if user.role in (ARTEC_PUBLISHER, OPERATOR_USER):
            return qs.filter(organization=user.organization)
        if user.role == ARTEC_REGULATOR:  # rapports et consultations seulement
            return qs.filter(organization=user.organization, category__in=REGULATOR_CATEGORIES)
        # lecture seule pour régulateur / admin : uniquement le contenu déjà publié
        return qs.filter(status=Publication.Status.PUBLISHED)

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == ARTEC_REGULATOR and serializer.validated_data.get("category") not in REGULATOR_CATEGORIES:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"category": "ARTEC Régulation publie des rapports et des consultations (catégories REPORT ou CONSULTATION)."})
        serializer.save(author=user, organization=user.organization)

    def perform_update(self, serializer):
        if self.request.user.role == ARTEC_REGULATOR and serializer.validated_data.get("category", serializer.instance.category) not in REGULATOR_CATEGORIES:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"category": "Catégorie réservée à ARTEC Publications."})
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status == Publication.Status.PUBLISHED:
            from rest_framework.exceptions import ValidationError

            raise ValidationError("Une publication publiée doit être archivée, pas supprimée.")
        instance.delete()

    @extend_schema(request=None, responses=PublicationSerializer)
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        return Response(PublicationSerializer(services.publish(self.get_object(), request.user, request)).data)

    @extend_schema(request=SchedulePublicationSerializer, responses=PublicationSerializer)
    @action(detail=True, methods=["post"])
    def schedule(self, request, pk=None):
        s = SchedulePublicationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(PublicationSerializer(services.schedule(self.get_object(), s.validated_data["published_at"], request.user, request)).data)

    @extend_schema(request=None, responses=PublicationSerializer)
    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        return Response(PublicationSerializer(services.archive(self.get_object(), request.user, request)).data)

    @extend_schema(request=AttachmentUploadSerializer, responses=AttachmentSerializer)
    @action(detail=True, methods=["post"], url_path="attachments")
    def add_attachment(self, request, pk=None):
        publication = self.get_object()
        s = AttachmentUploadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        f = s.validated_data["file"]
        att = PublicationAttachment.objects.create(publication=publication, file=f, original_name=f.name[:255], size=f.size)
        return Response(AttachmentSerializer(att).data, status=status.HTTP_201_CREATED)


class CommentViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Dépôt public (modéré) + liste publique des commentaires approuvés + modération."""

    filterset_fields = ["publication", "status"]

    def get_permissions(self):
        if self.action in ("create", "report") or (self.action == "list" and not self.request.user.is_authenticated):
            return [AllowAny()]
        if self.action == "list":
            return [AllowAny()]
        return [roles_required(ARTEC_PUBLISHER, OPERATOR_USER, ARTEC_REGULATOR)()]

    def get_throttles(self):
        if self.action in ("create", "report"):
            self.throttle_scope = "public_comment"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_authenticators(self):
        return super().get_authenticators()

    def get_serializer_class(self):
        return CommentPublicSerializer if self.action == "create" else CommentModerationSerializer

    def _is_moderator(self):
        u = self.request.user
        return u.is_authenticated and u.role in (ARTEC_PUBLISHER, OPERATOR_USER, ARTEC_REGULATOR)

    def get_queryset(self):
        qs = Comment.objects.select_related("publication")
        if self._is_moderator():
            user = self.request.user
            qs = qs.filter(publication__organization=user.organization)
            return qs.filter(publication__category__in=REGULATOR_CATEGORIES) if user.role == ARTEC_REGULATOR else qs
        return qs.filter(status=Comment.Status.APPROVED, publication__status=Publication.Status.PUBLISHED, publication__audience=Publication.Audience.PUBLIC)

    def list(self, request, *args, **kwargs):
        # Anonyme : uniquement les commentaires approuvés, champs publics.
        if not self._is_moderator():
            qs = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(qs)
            data = [{"id": c.id, "publication": c.publication_id, "content": c.content, "author_name": c.author_name or "Anonyme", "created_at": c.created_at} for c in page]
            return self.get_paginated_response(data)
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        s = CommentPublicSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        comment = s.save(status=Comment.Status.PENDING)
        return Response({"id": comment.id, "status": comment.status, "message": "Votre commentaire sera publié après modération."}, status=status.HTTP_201_CREATED)

    def _moderate(self, request, new_status):
        comment = self.get_object()
        comment.status = new_status
        comment.moderated_by = request.user
        comment.save(update_fields=["status", "moderated_by", "updated_at"])
        from apps.audit.services import log

        log(request.user, f"comment.{new_status.lower()}", "Comment", comment.pk, request=request)
        return Response(CommentModerationSerializer(comment).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._moderate(request, Comment.Status.APPROVED)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._moderate(request, Comment.Status.REJECTED)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def hide(self, request, pk=None):
        return self._moderate(request, Comment.Status.HIDDEN)

    @extend_schema(request=CommentReportSerializer, responses={202: None})
    @action(detail=True, methods=["post"])
    def report(self, request, pk=None):
        comment = Comment.objects.filter(pk=pk, status=Comment.Status.APPROVED).first()
        if comment is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        s = CommentReportSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        CommentReport.objects.create(comment=comment, reason=s.validated_data.get("reason", ""))
        comment.report_count += 1
        comment.save(update_fields=["report_count"])
        return Response(status=status.HTTP_202_ACCEPTED)


class OverviewView(APIView):
    """Chiffres réels pour le tableau de bord éditorial (ARTEC Publications) et opérateur (ses propres contenus)."""

    permission_classes = [roles_required(ARTEC_PUBLISHER, OPERATOR_USER, ARTEC_REGULATOR)]

    @extend_schema(responses={200: dict})
    def get(self, request):
        from django.db.models import Count

        from apps.surveys.models import Survey, SurveyResponse

        org = request.user.organization
        pubs = Publication.objects.filter(organization=org)
        surveys = Survey.objects.filter(organization=org)
        return Response({
            "publications": dict(pubs.values_list("status").annotate(n=Count("id"))),
            "comments_pending": Comment.objects.filter(publication__organization=org, status=Comment.Status.PENDING).count(),
            "comments_reported": Comment.objects.filter(publication__organization=org, report_count__gt=0).exclude(status__in=["REJECTED", "HIDDEN"]).count(),
            "surveys": dict(surveys.values_list("status").annotate(n=Count("id"))),
            "surveys_pending_approval": Survey.objects.filter(status=Survey.Status.PENDING_APPROVAL).count() if request.user.role in (ARTEC_PUBLISHER, ARTEC_REGULATOR) else 0,
            "responses_total": SurveyResponse.objects.filter(survey__organization=org).count(),
        })
