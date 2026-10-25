from django.db import transaction
from django.utils.html import strip_tags
from rest_framework import serializers

from apps.organizations.models import City, Organization, Region

from .models import Survey, SurveyChoice, SurveyQuestion, SurveyResponse


class ChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyChoice
        fields = ["id", "label", "order"]
        read_only_fields = ["id"]


class QuestionSerializer(serializers.ModelSerializer):
    choices = ChoiceSerializer(many=True, required=False)

    class Meta:
        model = SurveyQuestion
        fields = ["id", "text", "question_type", "is_required", "order", "min_value", "max_value", "max_length", "qos_metric", "choices"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        qtype = attrs.get("question_type")
        choices = attrs.get("choices", [])
        if qtype in ("SINGLE_CHOICE", "MULTIPLE_CHOICE") and len(choices) < 2:
            raise serializers.ValidationError({"choices": "Au moins deux choix sont requis."})
        if qtype not in ("SINGLE_CHOICE", "MULTIPLE_CHOICE") and choices:
            raise serializers.ValidationError({"choices": "Cette question n'accepte pas de choix."})
        metric = attrs.get("qos_metric", "")
        if metric:
            from apps.qos.rules import INDICATORS

            if metric not in INDICATORS:
                raise serializers.ValidationError({"qos_metric": "Indicateur QoS inconnu."})
            if qtype not in ("SATISFACTION", "NUMBER"):
                raise serializers.ValidationError({"qos_metric": "Seules les questions numériques ou de satisfaction peuvent alimenter un indicateur."})
            if qtype == "SATISFACTION" and metric != "satisfaction":
                raise serializers.ValidationError({"qos_metric": "Une échelle de satisfaction alimente l'indicateur « satisfaction »."})
        lo, hi = attrs.get("min_value"), attrs.get("max_value")
        if lo is not None and hi is not None and lo > hi:
            raise serializers.ValidationError({"min_value": "Minimum supérieur au maximum."})
        return attrs


class SurveySerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, required=False)
    organization_code = serializers.CharField(source="organization.code", read_only=True)
    target_operator = serializers.SlugRelatedField(slug_field="code", queryset=Organization.objects.filter(organization_type="OPERATOR"), required=False, allow_null=True)
    responses_count = serializers.SerializerMethodField()

    class Meta:
        model = Survey
        fields = [
            "id", "title", "description", "organization_code", "target_operator", "status", "starts_at", "ends_at", "published_at",
            "estimated_minutes", "results_public", "duplicate_policy", "require_participation_token", "rejection_reason",
            "questions", "responses_count", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "published_at", "organization_code", "rejection_reason", "responses_count", "created_at", "updated_at"]

    def get_responses_count(self, obj):
        return getattr(obj, "n_responses", None) if hasattr(obj, "n_responses") else obj.responses.count()

    def validate(self, attrs):
        s, e = attrs.get("starts_at", getattr(self.instance, "starts_at", None)), attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if s and e and e <= s:
            raise serializers.ValidationError({"ends_at": "La fin doit suivre le début."})
        user = self.context["request"].user
        target = attrs.get("target_operator")
        if user.role == "OPERATOR_USER" and target is not None and target.pk != user.organization_id:
            raise serializers.ValidationError({"target_operator": "Un opérateur ne peut évaluer que lui-même."})
        return attrs

    def _title_clean(self, attrs):
        for f in ("title", "description"):
            if f in attrs:
                attrs[f] = strip_tags(attrs[f]).strip()

    def _save_questions(self, survey, questions):
        for i, qd in enumerate(questions):
            choices = qd.pop("choices", [])
            qd.setdefault("order", i)
            q = SurveyQuestion.objects.create(survey=survey, **qd)
            for j, cd in enumerate(choices):
                SurveyChoice.objects.create(question=q, label=strip_tags(cd["label"]), order=cd.get("order", j))

    @transaction.atomic
    def create(self, validated_data):
        self._title_clean(validated_data)
        questions = validated_data.pop("questions", [])
        survey = Survey.objects.create(**validated_data)
        self._save_questions(survey, questions)
        return survey

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status not in (Survey.Status.DRAFT,):
            allowed = {"ends_at", "results_public"}
            if set(validated_data) - allowed:
                raise serializers.ValidationError("Seuls la date de fin et la visibilité des résultats sont modifiables après publication.")
        self._title_clean(validated_data)
        questions = validated_data.pop("questions", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if questions is not None:
            instance.questions.all().delete()
            self._save_questions(instance, questions)
        return instance


class PublicSurveyListSerializer(serializers.ModelSerializer):
    organization_code = serializers.CharField(source="organization.code", read_only=True)
    target_operator = serializers.CharField(source="target_operator.code", default=None, read_only=True)
    responses_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Survey
        fields = ["id", "title", "description", "organization_code", "target_operator", "status", "starts_at", "ends_at", "estimated_minutes", "results_public", "responses_count"]
        read_only_fields = fields


class AnswerInSerializer(serializers.Serializer):
    question = serializers.IntegerField()
    value = serializers.JSONField(required=False, allow_null=True)


class SurveyResponseInSerializer(serializers.Serializer):
    region = serializers.PrimaryKeyRelatedField(queryset=Region.objects.filter(is_active=True))
    city = serializers.PrimaryKeyRelatedField(queryset=City.objects.filter(is_active=True))
    location_context = serializers.ChoiceField(choices=SurveyResponse.Context.choices)
    operator = serializers.SlugRelatedField(slug_field="code", queryset=Organization.objects.filter(organization_type="OPERATOR"), required=False, allow_null=True)
    service_type = serializers.CharField(max_length=30, required=False, allow_blank=True)
    answers = AnswerInSerializer(many=True)
    participation_token = serializers.CharField(required=False, allow_blank=True)
    website = serializers.CharField(required=False, allow_blank=True)  # honeypot

    def validate(self, attrs):
        if attrs.get("website"):
            raise serializers.ValidationError("Soumission refusée.")
        if attrs["city"].region_id != attrs["region"].pk:
            raise serializers.ValidationError({"city": "Cette ville n'appartient pas à la région indiquée."})
        if len(attrs["answers"]) > 100:
            raise serializers.ValidationError({"answers": "Trop de réponses."})
        return attrs
