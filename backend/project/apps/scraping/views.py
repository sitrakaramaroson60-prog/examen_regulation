from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import log as audit_log
from apps.common.permissions import ARTEC_REGULATOR, OPERATOR_USER, roles_required

from . import services, tasks
from .models import ScrapedRecord, ScrapingExecution, ScrapingJob, ScrapingSource
from .serializers import ExecutionSerializer, JobSerializer, RecordSerializer, SourceSerializer

Collectors = roles_required(OPERATOR_USER, ARTEC_REGULATOR)


class OrgScoped:
    def get_queryset(self):
        return self.queryset.filter(**{self.org_lookup: self.request.user.organization_id})


class StatusView(APIView):
    permission_classes = [Collectors]

    @extend_schema(responses={200: dict})
    def get(self, request):
        domains = settings.SCRAPING_ALLOWED_DOMAINS
        return Response({"configured": bool(domains), "allowed_domains": domains if domains else [], "message": "" if domains else "Aucun domaine autorisé : le web scraping n'est pas encore configuré."})


class SourceViewSet(OrgScoped, viewsets.ModelViewSet):
    queryset = ScrapingSource.objects.all()
    org_lookup = "organization"
    serializer_class = SourceSerializer
    permission_classes = [Collectors]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_create(self, serializer):
        u = self.request.user
        serializer.save(organization=u.organization, created_by=u)


class JobViewSet(OrgScoped, viewsets.ModelViewSet):
    queryset = ScrapingJob.objects.select_related("source")
    org_lookup = "organization"
    serializer_class = JobSerializer
    permission_classes = [Collectors]
    filterset_fields = ["status", "frequency", "data_type"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_create(self, serializer):
        u = self.request.user
        job = serializer.save(organization=u.organization, created_by=u)
        audit_log(u, "scraping.job_created", "ScrapingJob", job.pk, {"url": job.url}, request=self.request)

    @extend_schema(request=None, responses={202: dict})
    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        job = self.get_object()
        tasks.run_job_task.delay(job.pk)
        return Response({"detail": "Exécution lancée.", "job": job.pk}, status=status.HTTP_202_ACCEPTED)

    @extend_schema(responses=ExecutionSerializer(many=True))
    @action(detail=True, methods=["get"])
    def executions(self, request, pk=None):
        return Response(ExecutionSerializer(self.get_object().executions.all()[:50], many=True).data)


class RecordViewSet(OrgScoped, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = ScrapedRecord.objects.all()
    org_lookup = "organization"
    serializer_class = RecordSerializer
    permission_classes = [Collectors]
    filterset_fields = ["job", "validation_status"]

    @extend_schema(request=None, responses=RecordSerializer)
    @action(detail=True, methods=["post"])
    def validate(self, request, pk=None):
        return Response(RecordSerializer(services.set_record_validation(self.get_object(), request.user, "VALIDATED", request)).data)

    @extend_schema(request=None, responses=RecordSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return Response(RecordSerializer(services.set_record_validation(self.get_object(), request.user, "REJECTED", request)).data)
