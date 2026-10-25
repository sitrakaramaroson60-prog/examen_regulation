from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.common.permissions import ARTEC_PUBLISHER, ARTEC_REGULATOR, OPERATOR_USER, SYSTEM_ADMIN

from . import services
from .models import Survey
from .serializers import PublicSurveyListSerializer, SurveyResponseInSerializer, SurveySerializer

EDITORS = (ARTEC_PUBLISHER, ARTEC_REGULATOR, OPERATOR_USER)
ARTEC_ROLES = (ARTEC_PUBLISHER, ARTEC_REGULATOR)


def is_editor(user):
    return user.is_authenticated and user.is_active and user.role in EDITORS


def public_surveys():
    now = timezone.now()
    return (
        Survey.objects.filter(status__in=[Survey.Status.PUBLISHED, Survey.Status.CLOSED])
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .select_related("organization", "target_operator")
        .annotate(responses_count=Count("responses"))
    )


class SurveyPermission(BasePermission):
    public_actions = {"list", "retrieve", "responses", "participation_token", "results"}

    def has_permission(self, request, view):
        if view.action in self.public_actions:
            return True
        return is_editor(request.user)


class SurveyViewSet(viewsets.ModelViewSet):
    permission_classes = [SurveyPermission]
    http_method_names = ["get", "post", "patch", "head", "options"]
    search_fields = ["title", "description"]
    filterset_fields = ["status"]
    ordering_fields = ["created_at", "ends_at", "published_at"]

    def get_serializer_class(self):
        if self.action == "list" and not is_editor(self.request.user):
            return PublicSurveyListSerializer
        return SurveySerializer

    def get_queryset(self):
        user = self.request.user
        if is_editor(user):
            qs = Survey.objects.filter(organization=user.organization)
            if user.role in ARTEC_ROLES:  # ARTEC valide aussi les sondages d'opérateurs en attente
                qs = Survey.objects.filter(Q(organization=user.organization) | Q(status=Survey.Status.PENDING_APPROVAL))
            return qs.select_related("organization", "target_operator").prefetch_related("questions__choices")
        return public_surveys()

    def get_object(self):
        obj = super().get_object()
        if not self.request.user.is_authenticated or not is_editor(self.request.user):
            return obj
        return obj

    def retrieve(self, request, *args, **kwargs):
        survey = self.get_object()
        if is_editor(request.user):
            return Response(SurveySerializer(survey, context={"request": request}).data)
        data = SurveySerializer(survey, context={"request": request}).data
        for k in ("rejection_reason",):
            data.pop(k, None)
        data["is_open"] = services.is_open(survey)
        return Response(data)

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(creator=user, organization=user.organization)

    def _own(self, request, survey):
        if survey.organization_id != request.user.organization_id:
            raise PermissionDenied("Ce sondage n'appartient pas à votre organisme.")

    def perform_update(self, serializer):
        self._own(self.request, serializer.instance)
        serializer.save()

    @extend_schema(request=None, responses=SurveySerializer)
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        survey = self.get_object()
        self._own(request, survey)
        return Response(SurveySerializer(services.publish_survey(survey, request.user, request), context={"request": request}).data)

    @extend_schema(request=None, responses=SurveySerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        survey = self.get_object()
        self._own(request, survey)
        return Response(SurveySerializer(services.close_survey(survey, request.user, request), context={"request": request}).data)

    @extend_schema(request=None, responses=SurveySerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        if request.user.role not in ARTEC_ROLES:
            raise PermissionDenied("Validation réservée à l'ARTEC.")
        return Response(SurveySerializer(services.approve_survey(self.get_object(), request.user, request), context={"request": request}).data)

    @extend_schema(request=None, responses=SurveySerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        if request.user.role not in ARTEC_ROLES:
            raise PermissionDenied("Validation réservée à l'ARTEC.")
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"reason": "Motif obligatoire."})
        return Response(SurveySerializer(services.reject_survey(self.get_object(), request.user, reason, request), context={"request": request}).data)

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=["get"], url_path="participation-token")
    def participation_token(self, request, pk=None):
        survey = self.get_object()
        if not services.is_open(survey):
            from rest_framework.exceptions import ValidationError

            raise ValidationError("Ce sondage n'accepte pas de réponses.")
        return Response({"participation_token": services.issue_token(survey)})

    @extend_schema(request=SurveyResponseInSerializer, responses={201: dict})
    @action(detail=True, methods=["post"], throttle_classes=[ScopedRateThrottle])
    def responses(self, request, pk=None):
        survey = Survey.objects.filter(pk=pk).first()
        if survey is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        s = SurveyResponseInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        response = services.submit_response(survey, s.validated_data, request)
        return Response({"id": response.pk, "submitted_at": response.submitted_at}, status=status.HTTP_201_CREATED)

    def get_throttles(self):
        if getattr(self, "action", None) == "responses":
            self.throttle_scope = "public_survey"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=["get"])
    def results(self, request, pk=None):
        user = request.user
        survey = Survey.objects.filter(pk=pk).select_related("organization").first()
        if survey is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        authorized = False
        if user.is_authenticated and user.is_active:
            if user.role in EDITORS and survey.organization_id == user.organization_id:
                authorized = True
            elif user.role == ARTEC_REGULATOR and survey.results_public:
                authorized = True
        if authorized:
            return Response(services.aggregate_results(survey, public=False))
        if survey.results_public and survey.status in (Survey.Status.PUBLISHED, Survey.Status.CLOSED):
            return Response(services.aggregate_results(survey, public=True))
        # Ne pas révéler l'existence d'un sondage non public.
        return Response({"error": {"code": "not_found", "message": "Introuvable.", "details": None}}, status=status.HTTP_404_NOT_FOUND)
