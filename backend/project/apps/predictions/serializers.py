from django.conf import settings
from rest_framework import serializers

from apps.datasets.models import DatasetVersion

from .frames import RISK_CLASS_LABELS, RISK_TYPES
from .models import PredictionModel, PredictionResult, PredictionRun


class PredictionModelSerializer(serializers.ModelSerializer):
    risk_label = serializers.SerializerMethodField()

    class Meta:
        model = PredictionModel
        fields = [
            "id", "name", "version", "model_type", "target_variable", "risk_type", "risk_label", "feature_schema", "training_dataset_version",
            "metrics", "status", "status_reason", "created_at",
        ]
        read_only_fields = fields

    def get_risk_label(self, obj):
        return RISK_TYPES.get(obj.risk_type, {}).get("label", obj.risk_type)


class TrainRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    training_dataset_version = serializers.PrimaryKeyRelatedField(queryset=DatasetVersion.objects.all())
    features = serializers.ListField(child=serializers.CharField(), required=False)
    risk_type = serializers.ChoiceField(choices=list(RISK_TYPES), required=False)


class BuildTrainingSetSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False)
    risk_type = serializers.ChoiceField(choices=list(RISK_TYPES), default="GENERAL_QUALITY")
    granularity = serializers.ChoiceField(choices=["week", "month"], default="month")
    sources = serializers.ListField(child=serializers.ChoiceField(choices=["TECHNICAL", "DECLARED"]), required=False, default=["TECHNICAL"])


class ForecastSerializer(serializers.Serializer):
    model_version = serializers.PrimaryKeyRelatedField(queryset=PredictionModel.objects.all())
    granularity = serializers.ChoiceField(choices=["week", "month"], required=False)
    sources = serializers.ListField(child=serializers.ChoiceField(choices=["TECHNICAL", "DECLARED"]), required=False)


class RunRequestSerializer(serializers.Serializer):
    model_version = serializers.PrimaryKeyRelatedField(queryset=PredictionModel.objects.all())
    input_dataset_version = serializers.PrimaryKeyRelatedField(queryset=DatasetVersion.objects.all())


class PredictionRunSerializer(serializers.ModelSerializer):
    model_name = serializers.CharField(source="model_version.name", read_only=True)
    risk_type = serializers.CharField(source="model_version.risk_type", read_only=True)
    model_number = serializers.IntegerField(source="model_version.version", read_only=True)

    class Meta:
        model = PredictionRun
        fields = ["id", "model_version", "model_name", "model_number", "risk_type", "input_dataset_version", "status", "started_at", "completed_at", "summary", "created_at"]
        read_only_fields = fields


class ResultSerializer(serializers.ModelSerializer):
    area = serializers.SerializerMethodField()
    risk_label = serializers.SerializerMethodField()
    needs_review = serializers.SerializerMethodField()

    class Meta:
        model = PredictionResult
        fields = [
            "id", "observation_reference", "area", "predicted_class", "risk_label", "probability_good", "probability_medium", "probability_poor",
            "confidence", "needs_review", "top_factors", "created_at",
        ]
        read_only_fields = fields

    def get_area(self, obj):
        parts = obj.observation_reference.split("|")
        return dict(zip(["operator", "region", "technology", "period"], parts)) if len(parts) == 4 else None

    def get_risk_label(self, obj):
        return RISK_CLASS_LABELS[obj.predicted_class]

    def get_needs_review(self, obj):
        return obj.confidence < settings.ML_REVIEW_CONFIDENCE
