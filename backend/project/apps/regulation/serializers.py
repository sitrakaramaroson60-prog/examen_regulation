from rest_framework import serializers

from apps.accounts.models import User
from apps.datasets.models import DatasetSubmission
from apps.organizations.models import Organization
from apps.predictions.models import PredictionRun

from .models import CaseEvent, CorrectiveAction, OperatorResponse, RegulatoryCase, RegulatoryDecision, RegulatoryEvidence


class EvidenceSerializer(serializers.ModelSerializer):
    added_by = serializers.CharField(source="added_by.email", read_only=True)

    class Meta:
        model = RegulatoryEvidence
        fields = ["id", "kind", "description", "dataset_submission", "prediction_run", "visible_to_operator", "added_by", "created_at"]
        read_only_fields = ["id", "added_by", "created_at"]


class DecisionSerializer(serializers.ModelSerializer):
    decided_by = serializers.CharField(source="decided_by.email", read_only=True)
    evidence = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    is_current = serializers.BooleanField(read_only=True)
    supersedes = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = RegulatoryDecision
        fields = ["id", "case", "category", "justification", "decided_by", "decided_at", "evidence", "supersedes", "amendment_reason", "is_current"]
        read_only_fields = fields


class DecisionInputSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=RegulatoryDecision.Category.choices)
    justification = serializers.CharField()
    evidence = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    reason = serializers.CharField(required=False, allow_blank=True)  # motif de modification


class CorrectiveActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CorrectiveAction
        fields = ["id", "case", "decision", "description", "due_date", "status", "operator_report", "verification_comment", "created_at", "updated_at"]
        read_only_fields = ["id", "case", "status", "operator_report", "verification_comment", "created_at", "updated_at"]


class ResponseSerializer(serializers.ModelSerializer):
    responder = serializers.CharField(source="responder.email", read_only=True)

    class Meta:
        model = OperatorResponse
        fields = ["id", "responder", "content", "created_at"]
        read_only_fields = fields


class EventSerializer(serializers.ModelSerializer):
    actor = serializers.CharField(source="actor.email", default=None, read_only=True)

    class Meta:
        model = CaseEvent
        fields = ["id", "kind", "actor", "message", "internal", "created_at"]
        read_only_fields = fields


class CaseSerializer(serializers.ModelSerializer):
    operator = serializers.SlugRelatedField(slug_field="code", queryset=Organization.objects.filter(organization_type="OPERATOR"))
    related_prediction = serializers.PrimaryKeyRelatedField(queryset=PredictionRun.objects.all(), required=False, allow_null=True)
    related_dataset_submission = serializers.PrimaryKeyRelatedField(queryset=DatasetSubmission.objects.all(), required=False, allow_null=True)
    assigned_to = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role="ARTEC_REGULATOR", is_active=True), required=False, allow_null=True)
    current_decision = serializers.SerializerMethodField()

    class Meta:
        model = RegulatoryCase
        fields = [
            "id", "reference_number", "operator", "case_type", "status", "title", "description", "related_prediction",
            "related_dataset_submission", "opened_by", "assigned_to", "opened_at", "deadline", "closed_at", "current_decision",
        ]
        read_only_fields = ["id", "reference_number", "status", "opened_by", "opened_at", "closed_at", "current_decision"]

    def get_current_decision(self, obj):
        for d in obj.decisions.all():
            if d.is_current:
                return {"id": d.id, "category": d.category, "decided_at": d.decided_at}
        return None


class RespondSerializer(serializers.Serializer):
    content = serializers.CharField()


class ExplanationSerializer(serializers.Serializer):
    message = serializers.CharField()
    deadline = serializers.DateField(required=False)


class CloseSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True)


class ActionUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["IN_PROGRESS", "SUBMITTED"])
    report = serializers.CharField(required=False, allow_blank=True)


class VerifySerializer(serializers.Serializer):
    compliant = serializers.BooleanField()
    comment = serializers.CharField(required=False, allow_blank=True)


class NoteSerializer(serializers.Serializer):
    message = serializers.CharField()


# ---------- obligations, alertes, contrôles de suivi ----------
from apps.organizations.models import Region  # noqa: E402
from apps.qos.rules import METRICS  # noqa: E402

from .compliance import NATURE  # noqa: E402
from .models import ComplianceAlert, FollowUpCheck, Obligation, ObligationEvaluation  # noqa: E402


class EvaluationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ObligationEvaluation
        fields = ["id", "period_start", "period_end", "measured_value", "sample_count", "status", "gap", "gap_pct", "evaluated_at"]
        read_only_fields = fields


class ObligationSerializer(serializers.ModelSerializer):
    operator = serializers.SlugRelatedField(slug_field="code", queryset=Organization.objects.filter(organization_type="OPERATOR"))
    region = serializers.PrimaryKeyRelatedField(queryset=Region.objects.all(), required=False, allow_null=True)
    latest_evaluation = serializers.SerializerMethodField()

    class Meta:
        model = Obligation
        fields = [
            "id", "operator", "title", "description", "legal_basis", "metric_name", "unit", "comparison", "target_value", "measurement_method",
            "technology", "service_type", "region", "evaluation_window_days", "min_samples", "valid_from", "valid_until", "is_active",
            "latest_evaluation", "created_at",
        ]
        read_only_fields = ["id", "latest_evaluation", "created_at"]

    def get_latest_evaluation(self, obj):
        ev = obj.evaluations.first()
        return EvaluationSerializer(ev).data if ev else None

    def validate_legal_basis(self, value):
        if len(value.strip()) < 5:
            raise serializers.ValidationError("L'origine de l'engagement (texte, décision, convention) doit être documentée.")
        return value.strip()

    def validate(self, attrs):
        metric = attrs.get("metric_name", getattr(self.instance, "metric_name", None))
        unit = attrs.get("unit", getattr(self.instance, "unit", None))
        if metric not in METRICS:
            raise serializers.ValidationError({"metric_name": f"Indicateur inconnu ({', '.join(sorted(METRICS))})."})
        if unit not in METRICS[metric] or unit == "kbps":
            raise serializers.ValidationError({"unit": "Unité incompatible avec l'indicateur (unité canonique requise)."})
        if not (attrs.get("measurement_method", getattr(self.instance, "measurement_method", "")) or "").strip():
            raise serializers.ValidationError({"measurement_method": "La méthode de mesure de référence est obligatoire."})
        vf, vu = attrs.get("valid_from", getattr(self.instance, "valid_from", None)), attrs.get("valid_until", getattr(self.instance, "valid_until", None))
        if vf and vu and vu < vf:
            raise serializers.ValidationError({"valid_until": "La fin de validité précède le début."})
        return attrs


class AlertSerializer(serializers.ModelSerializer):
    operator = serializers.CharField(source="obligation.operator.code", read_only=True)
    obligation_title = serializers.CharField(source="obligation.title", read_only=True)
    measured_value = serializers.FloatField(source="evaluation.measured_value", read_only=True)
    nature = serializers.SerializerMethodField()
    cases = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = ComplianceAlert
        fields = ["id", "operator", "obligation", "obligation_title", "severity", "status", "message", "measured_value", "nature", "handling_note", "handled_at", "cases", "created_at"]
        read_only_fields = fields

    def get_nature(self, obj):
        return NATURE


class AlertActionSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True)
    title = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    deadline = serializers.DateField(required=False, allow_null=True)


class CheckSerializer(serializers.ModelSerializer):
    action_description = serializers.CharField(source="corrective_action.description", read_only=True)
    case = serializers.CharField(source="corrective_action.case.reference_number", read_only=True)
    operator = serializers.CharField(source="corrective_action.case.operator.code", read_only=True)

    class Meta:
        model = FollowUpCheck
        fields = ["id", "corrective_action", "case", "operator", "action_description", "due_date", "status", "outcome", "notes", "performed_at"]
        read_only_fields = ["id", "case", "operator", "action_description", "status", "outcome", "notes", "performed_at"]


class CheckCompleteSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=FollowUpCheck.Outcome.choices)
    notes = serializers.CharField(min_length=5)
