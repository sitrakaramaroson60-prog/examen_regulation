from rest_framework import serializers

from .models import QoSMeasurement, QoSThreshold
from .rules import METRICS


class MeasurementSerializer(serializers.ModelSerializer):
    operator = serializers.CharField(source="operator.code", read_only=True)
    region = serializers.CharField(source="region.name", read_only=True)
    city = serializers.CharField(source="city.name", default=None, read_only=True)

    class Meta:
        model = QoSMeasurement
        fields = [
            "id", "operator", "region", "city", "service_type", "technology", "metric_name", "metric_value", "unit",
            "measurement_method", "source_type", "measured_at", "dataset_version", "validation_status",
        ]
        read_only_fields = fields


class ThresholdSerializer(serializers.ModelSerializer):
    class Meta:
        model = QoSThreshold
        fields = [
            "id", "metric_name", "technology", "service_type", "unit", "good_threshold", "poor_threshold", "higher_is_better",
            "valid_from", "valid_until", "origin", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_metric_name(self, value):
        if value not in METRICS:
            raise serializers.ValidationError(f"Indicateur inconnu. Valeurs : {', '.join(sorted(METRICS))}.")
        return value

    def validate_origin(self, value):
        if len(value.strip()) < 5:
            raise serializers.ValidationError("L'origine du seuil doit être documentée.")
        return value.strip()

    def validate(self, attrs):
        metric = attrs.get("metric_name", getattr(self.instance, "metric_name", None))
        unit = attrs.get("unit", getattr(self.instance, "unit", None))
        if metric in METRICS and unit not in METRICS[metric]:
            raise serializers.ValidationError({"unit": "Unité incompatible avec l'indicateur."})
        good, poor = attrs.get("good_threshold", getattr(self.instance, "good_threshold", None)), attrs.get("poor_threshold", getattr(self.instance, "poor_threshold", None))
        better = attrs.get("higher_is_better", getattr(self.instance, "higher_is_better", True))
        if good is not None and poor is not None and ((better and good < poor) or (not better and good > poor)):
            raise serializers.ValidationError("Seuils incohérents avec le sens de l'indicateur.")
        vf, vu = attrs.get("valid_from", getattr(self.instance, "valid_from", None)), attrs.get("valid_until", getattr(self.instance, "valid_until", None))
        if vf and vu and vu < vf:
            raise serializers.ValidationError({"valid_until": "La fin de validité précède le début."})
        return attrs


class BarometerSettingSerializer(serializers.ModelSerializer):
    class Meta:
        from .models import PublicBarometerSetting

        model = PublicBarometerSetting
        fields = ["enabled", "min_measurements", "updated_at"]
        read_only_fields = ["updated_at"]

    def validate_min_measurements(self, value):
        if value < 5:
            raise serializers.ValidationError("Au moins 5 mesures sont requises pour publier une moyenne.")
        return value
