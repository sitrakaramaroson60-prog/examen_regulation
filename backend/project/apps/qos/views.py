from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import SAFE_METHODS, AllowAny, BasePermission
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.audit.services import log as audit_log
from apps.common.permissions import ARTEC_REGULATOR, OPERATOR_USER, roles_required

from . import services
from .models import QoSMeasurement, QoSThreshold
from .dashboard import build_dashboard
from .rules import INDICATORS, METRICS
from .serializers import BarometerSettingSerializer, MeasurementSerializer, ThresholdSerializer


def measurements_for(user):
    qs = QoSMeasurement.objects.select_related("operator", "region", "city")
    if user.role == OPERATOR_USER:
        return qs.filter(operator=user.organization)
    if user.role == ARTEC_REGULATOR:
        return qs.filter(validation_status=QoSMeasurement.ValidationStatus.VALIDATED)
    return qs.none()


class MeasurementViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Mesures QoS en lecture seule (alimentées par les datasets acceptés)."""

    serializer_class = MeasurementSerializer
    permission_classes = [roles_required(OPERATOR_USER, ARTEC_REGULATOR)]
    filterset_fields = {
        "operator__code": ["exact"], "region": ["exact"], "city": ["exact"], "metric_name": ["exact"], "service_type": ["exact"],
        "technology": ["exact"], "source_type": ["exact"], "measured_at": ["gte", "lte"],
    }
    ordering_fields = ["measured_at", "metric_value"]

    def get_queryset(self):
        return measurements_for(self.request.user)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Moyennes par opérateur/indicateur/méthode/technologie/source (jamais mélangées entre méthodes)."""
        qs = self.filter_queryset(self.get_queryset())
        return Response(services.summarize(qs))

    @action(detail=False, methods=["get"])
    def metrics(self, request):
        return Response([{"metric": k, "label": v["label"], "unit": v["unit"], "units": sorted(METRICS[k]), "higher_is_better": v["higher_is_better"]} for k, v in INDICATORS.items()])

    @action(detail=False, methods=["get"])
    def dashboard(self, request):
        """Supervision : indicateurs comparables par opérateur (ARTEC : tous ; opérateur : lui-même seulement)."""
        from django.utils.dateparse import parse_datetime, parse_date
        from django.utils import timezone as tz

        q = request.query_params

        def dt(name, end=False):
            raw = q.get(name)
            if not raw:
                return None
            val = parse_datetime(raw) or (lambda d: tz.make_aware(tz.datetime.combine(d, tz.datetime.max.time() if end else tz.datetime.min.time())) if d else None)(parse_date(raw))
            if val is None:
                from rest_framework.exceptions import ValidationError

                raise ValidationError({name: "Date invalide (AAAA-MM-JJ)."})
            return val

        params = {
            "date_from": dt("date_from"), "date_to": dt("date_to", end=True), "region": q.get("region"), "technology": q.get("technology"),
            "service_type": q.get("service_type"), "sources": [s for s in q.get("sources", "").split(",") if s],
        }
        if request.user.role == OPERATOR_USER:
            params["only_operator"] = request.user.organization.code  # un opérateur ne voit jamais les chiffres des concurrents
        return Response(build_dashboard(self.get_queryset(), params))


class ThresholdPermission(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        if not (u.is_authenticated and u.is_active):
            return False
        if request.method in SAFE_METHODS:
            return u.role in (ARTEC_REGULATOR, OPERATOR_USER)
        return u.role == ARTEC_REGULATOR


class ThresholdViewSet(viewsets.ModelViewSet):
    queryset = QoSThreshold.objects.all()
    serializer_class = ThresholdSerializer
    permission_classes = [ThresholdPermission]
    filterset_fields = ["metric_name", "technology", "service_type"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_create(self, serializer):
        t = serializer.save(created_by=self.request.user)
        audit_log(self.request.user, "threshold.created", "QoSThreshold", t.pk, {"metric": t.metric_name, "origin": t.origin}, request=self.request)

    def perform_update(self, serializer):
        t = serializer.save()
        audit_log(self.request.user, "threshold.updated", "QoSThreshold", t.pk, {"metric": t.metric_name}, request=self.request)


class PublicSummaryView(APIView):
    """Données publiques agrégées (compteurs de participation + baromètre si activé par l'ARTEC)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses={200: dict})
    def get(self, request):
        from .public import public_summary

        return Response(public_summary())


class BarometerSettingView(APIView):
    """Publication des indicateurs agrégés au public : décision de l'ARTEC Régulation (tracée dans l'audit)."""

    permission_classes = [roles_required(ARTEC_REGULATOR)]

    @extend_schema(responses=BarometerSettingSerializer)
    def get(self, request):
        from .models import PublicBarometerSetting

        return Response(BarometerSettingSerializer(PublicBarometerSetting.current()).data)

    @extend_schema(request=BarometerSettingSerializer, responses=BarometerSettingSerializer)
    def put(self, request):
        from .models import PublicBarometerSetting

        cfg = PublicBarometerSetting.current()
        s = BarometerSettingSerializer(cfg, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        cfg = s.save(updated_by=request.user)
        audit_log(request.user, "barometer.published" if cfg.enabled else "barometer.unpublished", "PublicBarometerSetting", cfg.pk, {"min_measurements": cfg.min_measurements}, request=request)
        return Response(BarometerSettingSerializer(cfg).data)
