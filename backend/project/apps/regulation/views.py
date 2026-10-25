from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import log as audit_log
from apps.common.permissions import ARTEC_REGULATOR, OPERATOR_USER, roles_required

from . import compliance, files, services
from .models import CaseEvent, ComplianceAlert, CorrectiveAction, FollowUpCheck, Obligation, ObligationEvaluation, RegulatoryCase, RegulatoryDecision
from .serializers import (
    AlertActionSerializer,
    AlertSerializer,
    CheckCompleteSerializer,
    CheckSerializer,
    EvaluationSerializer,
    ObligationSerializer,
    ActionUpdateSerializer,
    CaseSerializer,
    CloseSerializer,
    CorrectiveActionSerializer,
    DecisionInputSerializer,
    DecisionSerializer,
    EventSerializer,
    EvidenceSerializer,
    ExplanationSerializer,
    NoteSerializer,
    RespondSerializer,
    ResponseSerializer,
    VerifySerializer,
)

Participants = roles_required(OPERATOR_USER, ARTEC_REGULATOR)


def is_regulator(user):
    return user.role == ARTEC_REGULATOR


def require_regulator(request):
    if not is_regulator(request.user):
        raise PermissionDenied("Opération réservée à ARTEC Régulation et Prédiction.")


class CaseViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = CaseSerializer
    permission_classes = [Participants]
    filterset_fields = ["status", "case_type", "operator__code"]
    search_fields = ["reference_number", "title", "description"]
    ordering_fields = ["opened_at", "deadline"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = RegulatoryCase.objects.select_related("operator").prefetch_related("decisions__evidence")
        user = self.request.user
        if is_regulator(user):
            return qs
        return qs.filter(operator=user.organization)  # isolation stricte : 404 pour les dossiers d'un concurrent

    def perform_create(self, serializer):
        require_regulator(self.request)
        data = dict(serializer.validated_data)
        case = services.open_case(data, self.request.user, self.request)
        serializer.instance = case

    def perform_update(self, serializer):
        require_regulator(self.request)
        if serializer.instance.status == "CLOSED":
            from rest_framework.exceptions import ValidationError

            raise ValidationError("Dossier clos : modification impossible.")
        serializer.save()

    def _visible_events(self, case):
        qs = case.events.select_related("actor")
        return qs if is_regulator(self.request.user) else qs.filter(internal=False)

    @extend_schema(responses=EventSerializer(many=True))
    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        return Response(EventSerializer(self._visible_events(self.get_object()), many=True).data)

    @extend_schema(request=NoteSerializer, responses=EventSerializer)
    @action(detail=True, methods=["post"])
    def note(self, request, pk=None):
        require_regulator(request)
        s = NoteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        ev = services.add_event(self.get_object(), CaseEvent.Kind.NOTE, request.user, s.validated_data["message"], internal=True)
        return Response(EventSerializer(ev).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ExplanationSerializer, responses=CaseSerializer)
    @action(detail=True, methods=["post"], url_path="request-explanation")
    def request_explanation(self, request, pk=None):
        require_regulator(request)
        s = ExplanationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        case = services.request_explanation(self.get_object(), request.user, s.validated_data["message"], s.validated_data.get("deadline"), request)
        return Response(CaseSerializer(case).data)

    @extend_schema(request=RespondSerializer, responses=ResponseSerializer)
    @action(detail=True, methods=["post"])
    def respond(self, request, pk=None):
        if request.user.role != OPERATOR_USER:
            raise PermissionDenied("Seul l'opérateur concerné peut répondre.")
        s = RespondSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        resp = services.operator_respond(self.get_object(), request.user, s.validated_data["content"], request)
        return Response(ResponseSerializer(resp).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=ResponseSerializer(many=True))
    @action(detail=True, methods=["get"])
    def responses(self, request, pk=None):
        return Response(ResponseSerializer(self.get_object().responses.select_related("responder"), many=True).data)

    @extend_schema(request=EvidenceSerializer, responses=EvidenceSerializer(many=True))
    @action(detail=True, methods=["get", "post"])
    def evidence(self, request, pk=None):
        case = self.get_object()
        if request.method == "GET":
            qs = case.evidence.select_related("added_by")
            if not is_regulator(request.user):
                qs = qs.filter(visible_to_operator=True)
            return Response(EvidenceSerializer(qs, many=True).data)
        require_regulator(request)
        s = EvidenceSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        ev = services.add_evidence(case, request.user, dict(s.validated_data), request)
        return Response(EvidenceSerializer(ev).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=DecisionInputSerializer, responses=DecisionSerializer)
    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        require_regulator(request)
        s = DecisionInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = services.decide(self.get_object(), request.user, s.validated_data["category"], s.validated_data["justification"], s.validated_data["evidence"], request)
        return Response(DecisionSerializer(d).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=CorrectiveActionSerializer, responses=CorrectiveActionSerializer(many=True))
    @action(detail=True, methods=["get", "post"], url_path="corrective-actions")
    def corrective_actions(self, request, pk=None):
        case = self.get_object()
        if request.method == "GET":
            return Response(CorrectiveActionSerializer(case.corrective_actions.all(), many=True).data)
        require_regulator(request)
        s = CorrectiveActionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        decision = s.validated_data.get("decision")
        if decision is not None and decision.case_id != case.pk:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"decision": "Décision étrangère à ce dossier."})
        a = services.create_corrective_action(case, request.user, s.validated_data["description"], s.validated_data["due_date"], decision, request)
        return Response(CorrectiveActionSerializer(a).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=CloseSerializer, responses=CaseSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        require_regulator(request)
        s = CloseSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(CaseSerializer(services.close_case(self.get_object(), request.user, s.validated_data.get("comment", ""), request)).data)


class DecisionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = DecisionSerializer
    permission_classes = [Participants]
    filterset_fields = ["case", "category"]

    def get_queryset(self):
        qs = RegulatoryDecision.objects.select_related("decided_by", "case").prefetch_related("evidence")
        user = self.request.user
        return qs if is_regulator(user) else qs.filter(case__operator=user.organization)

    @extend_schema(request=DecisionInputSerializer, responses=DecisionSerializer)
    @action(detail=True, methods=["post"])
    def amend(self, request, pk=None):
        require_regulator(request)
        s = DecisionInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        new = services.amend_decision(self.get_object(), request.user, d["category"], d["justification"], d.get("reason", ""), d["evidence"], request)
        return Response(DecisionSerializer(new).data, status=status.HTTP_201_CREATED)


class CorrectiveActionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = CorrectiveActionSerializer
    permission_classes = [Participants]
    filterset_fields = ["status", "case"]

    def get_queryset(self):
        qs = CorrectiveAction.objects.select_related("case")
        user = self.request.user
        return qs if is_regulator(user) else qs.filter(case__operator=user.organization)

    @extend_schema(request=ActionUpdateSerializer, responses=CorrectiveActionSerializer)
    @action(detail=True, methods=["post"], url_path="update-progress")
    def update_progress(self, request, pk=None):
        if request.user.role != OPERATOR_USER:
            raise PermissionDenied("Réservé à l'opérateur concerné.")
        s = ActionUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(CorrectiveActionSerializer(services.operator_update_action(self.get_object(), request.user, s.validated_data["status"], s.validated_data.get("report", ""), request)).data)

    @extend_schema(request=CheckSerializer, responses={201: CheckSerializer})
    @action(detail=True, methods=["post"], url_path="schedule-check")
    def schedule_check(self, request, pk=None):
        require_regulator(request)
        due = request.data.get("due_date")
        s = CheckSerializer(data={"corrective_action": self.get_object().pk, "due_date": due})
        s.is_valid(raise_exception=True)
        check = FollowUpCheck.objects.create(corrective_action=self.get_object(), due_date=s.validated_data["due_date"], planned_by=request.user)
        audit_log(request.user, "check.planned", "FollowUpCheck", check.pk, {"due": str(check.due_date)}, request=request)
        return Response(CheckSerializer(check).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=VerifySerializer, responses=CorrectiveActionSerializer)
    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        require_regulator(request)
        s = VerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(CorrectiveActionSerializer(services.verify_action(self.get_object(), request.user, s.validated_data["compliant"], s.validated_data.get("comment", ""), request)).data)


class OverviewView(APIView):
    """Indicateurs synthétiques pour le tableau de bord de régulation (chiffres réels, non simulés)."""

    permission_classes = [roles_required(ARTEC_REGULATOR)]

    @extend_schema(responses={200: dict})
    def get(self, request):
        from apps.datasets.models import DatasetSubmission
        from apps.predictions.models import PredictionRun

        subs = DatasetSubmission.objects
        cases = RegulatoryCase.objects.exclude(status="CLOSED")
        return Response(
            {
                "submissions_total": subs.count(),
                "submissions_pending_review": subs.filter(status__in=["SUBMITTED", "UNDER_REVIEW"]).count(),
                "submissions_by_status": dict(subs.values_list("status").annotate(n=Count("id"))),
                "predictions_total": PredictionRun.objects.count(),
                "predictions_completed": PredictionRun.objects.filter(status="COMPLETED").count(),
                "cases_open": cases.count(),
                "cases_awaiting_operator": cases.filter(status="AWAITING_OPERATOR_RESPONSE").count(),
                "alerts_open": ComplianceAlert.objects.filter(status__in=["NEW", "ACKNOWLEDGED"]).count(),
                "alerts_critical": ComplianceAlert.objects.filter(status__in=["NEW", "ACKNOWLEDGED"], severity="CRITICAL").count(),
                "obligations_active": Obligation.objects.filter(is_active=True).count(),
                "checks_planned": FollowUpCheck.objects.filter(status="PLANNED").count(),
            }
        )


class ObligationViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Engagements des opérateurs. ARTEC Régulation : gestion complète ; opérateur : lecture de ses propres engagements."""

    serializer_class = ObligationSerializer
    permission_classes = [Participants]
    filterset_fields = ["operator__code", "metric_name", "is_active"]
    search_fields = ["title", "legal_basis"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = Obligation.objects.select_related("operator", "region").prefetch_related("evaluations")
        return qs if is_regulator(self.request.user) else qs.filter(operator=self.request.user.organization)

    def perform_create(self, serializer):
        require_regulator(self.request)
        ob = serializer.save(created_by=self.request.user)
        audit_log(self.request.user, "obligation.created", "Obligation", ob.pk, {"operator": ob.operator.code, "legal_basis": ob.legal_basis}, request=self.request)

    def perform_update(self, serializer):
        require_regulator(self.request)
        ob = serializer.save()
        audit_log(self.request.user, "obligation.updated", "Obligation", ob.pk, request=self.request)

    @extend_schema(responses=EvaluationSerializer(many=True))
    @action(detail=True, methods=["get"])
    def evaluations(self, request, pk=None):
        return Response(EvaluationSerializer(self.get_object().evaluations.all()[:50], many=True).data)

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=["post"])
    def evaluate(self, request, pk=None):
        require_regulator(request)
        ev, alert = compliance.evaluate(self.get_object(), request.user)
        return Response({"evaluation": EvaluationSerializer(ev).data, "alert": AlertSerializer(alert).data if alert else None})

    @extend_schema(request=None, responses={200: dict})
    @action(detail=False, methods=["post"], url_path="evaluate-all")
    def evaluate_all(self, request):
        require_regulator(request)
        return Response(compliance.evaluate_all(request.user))


class AlertViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Alertes algorithmiques : visibles de l'ARTEC Régulation uniquement. Une alerte n'est jamais une décision."""

    serializer_class = AlertSerializer
    permission_classes = [roles_required(ARTEC_REGULATOR)]
    filterset_fields = ["status", "severity", "obligation__operator__code"]
    queryset = ComplianceAlert.objects.select_related("obligation__operator", "evaluation").prefetch_related("cases")

    @extend_schema(request=AlertActionSerializer, responses=AlertSerializer)
    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        s = AlertActionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(AlertSerializer(compliance.handle_alert(self.get_object(), request.user, "acknowledge", s.validated_data.get("note", ""), request)).data)

    @extend_schema(request=AlertActionSerializer, responses=AlertSerializer)
    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        s = AlertActionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(AlertSerializer(compliance.handle_alert(self.get_object(), request.user, "dismiss", s.validated_data.get("note", ""), request)).data)

    @extend_schema(request=AlertActionSerializer, responses={201: CaseSerializer})
    @action(detail=True, methods=["post"])
    def escalate(self, request, pk=None):
        s = AlertActionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        case = compliance.escalate_alert(self.get_object(), request.user, d.get("title", ""), d.get("description", ""), d.get("deadline"), request)
        return Response(CaseSerializer(case).data, status=status.HTTP_201_CREATED)


class CheckViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = CheckSerializer
    permission_classes = [Participants]
    filterset_fields = ["status"]

    def get_queryset(self):
        qs = FollowUpCheck.objects.select_related("corrective_action__case__operator")
        user = self.request.user
        return qs if is_regulator(user) else qs.filter(corrective_action__case__operator=user.organization)

    @extend_schema(request=CheckCompleteSerializer, responses=CheckSerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        require_regulator(request)
        check = self.get_object()
        if check.status == "DONE":
            from rest_framework.exceptions import ValidationError

            raise ValidationError("Contrôle déjà réalisé.")
        s = CheckCompleteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        from django.utils import timezone

        check.status, check.outcome, check.notes = "DONE", s.validated_data["outcome"], s.validated_data["notes"]
        check.performed_by, check.performed_at = request.user, timezone.now()
        check.save()
        case = check.corrective_action.case
        services.add_event(case, CaseEvent.Kind.NOTE, request.user, f"Contrôle de suivi : {check.get_outcome_display()}.")
        audit_log(request.user, "check.completed", "FollowUpCheck", check.pk, {"outcome": check.outcome}, request=request)
        return Response(CheckSerializer(check).data)


class OperatorFileView(APIView):
    """Dossier de suivi d'un opérateur. ARTEC Régulation : tout opérateur ; opérateur : le sien uniquement."""

    permission_classes = [Participants]

    @extend_schema(responses={200: dict})
    def get(self, request, code=None):
        from apps.organizations.models import Organization
        from django.http import Http404

        user = request.user
        if code in (None, "me"):
            if is_regulator(user):
                raise Http404
            org = user.organization
        else:
            org = Organization.objects.filter(code=code.upper(), organization_type="OPERATOR").first()
            if org is None or (not is_regulator(user) and org.pk != user.organization_id):
                raise Http404
        return Response(files.operator_file(org, as_regulator=is_regulator(user)))

    def list_all(self, request):
        pass


class OperatorFilesIndexView(APIView):
    """Vue d'ensemble : une ligne par opérateur (ARTEC Régulation)."""

    permission_classes = [roles_required(ARTEC_REGULATOR)]

    @extend_schema(responses={200: dict})
    def get(self, request):
        from apps.organizations.models import Organization

        rows = []
        for org in Organization.objects.filter(organization_type="OPERATOR", is_active=True):
            f = files.operator_file(org, as_regulator=True)
            rows.append({"operator": f["operator"], **f["summary"]})
        return Response(rows)
