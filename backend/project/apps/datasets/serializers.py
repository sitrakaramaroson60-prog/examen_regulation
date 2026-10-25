from rest_framework import serializers

from .models import Dataset, DatasetSubmission, DatasetValidationReport, DatasetVersion, SubmissionEvent
from .schemas import DATA_TYPES


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatasetValidationReport
        fields = ["status", "row_count", "missing_columns", "type_errors", "missing_values", "duplicate_rows", "quality_score", "messages", "created_at"]
        read_only_fields = fields


class VersionSerializer(serializers.ModelSerializer):
    report = ReportSerializer(read_only=True)
    dataset_name = serializers.CharField(source="dataset.name", read_only=True)
    data_type = serializers.CharField(source="dataset.data_type", read_only=True)
    owner_organization = serializers.CharField(source="dataset.owner_organization.code", read_only=True)

    class Meta:
        model = DatasetVersion
        fields = ["id", "dataset", "dataset_name", "data_type", "owner_organization", "version_number", "original_name", "file_format", "checksum", "schema_definition", "row_count", "created_at", "report"]
        read_only_fields = fields


class VersionUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class DatasetSerializer(serializers.ModelSerializer):
    owner_organization = serializers.CharField(source="owner_organization.code", read_only=True)
    data_type = serializers.ChoiceField(choices=DATA_TYPES)
    latest_version = serializers.SerializerMethodField()

    class Meta:
        model = Dataset
        fields = ["id", "owner_organization", "name", "description", "data_type", "source_type", "created_at", "latest_version"]
        read_only_fields = ["id", "owner_organization", "created_at", "latest_version"]

    def get_latest_version(self, obj):
        v = obj.versions.order_by("-version_number").first()
        return None if v is None else {"id": v.id, "version_number": v.version_number, "report_status": v.report.status}

    def validate_source_type(self, value):
        if value not in ("TECHNICAL", "DECLARED"):
            raise serializers.ValidationError("Valeurs admises : TECHNICAL (mesures de sondes, drive tests, speed tests) ou DECLARED (indicateurs déclarés).")
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        qs = Dataset.objects.filter(owner_organization=user.organization, name=attrs.get("name"))
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if "name" in attrs and qs.exists():
            raise serializers.ValidationError({"name": "Un dataset de ce nom existe déjà."})
        return attrs


class EventSerializer(serializers.ModelSerializer):
    actor = serializers.CharField(source="actor.email", default=None, read_only=True)

    class Meta:
        model = SubmissionEvent
        fields = ["actor", "from_status", "to_status", "comment", "created_at"]
        read_only_fields = fields


class SubmissionSerializer(serializers.ModelSerializer):
    organization = serializers.CharField(source="dataset_version.dataset.owner_organization.code", read_only=True)
    dataset_name = serializers.CharField(source="dataset_version.dataset.name", read_only=True)
    data_type = serializers.CharField(source="dataset_version.dataset.data_type", read_only=True)
    version_number = serializers.IntegerField(source="dataset_version.version_number", read_only=True)
    report_status = serializers.CharField(source="dataset_version.report.status", read_only=True)
    quality_score = serializers.FloatField(source="dataset_version.report.quality_score", read_only=True)
    events = EventSerializer(many=True, read_only=True)

    class Meta:
        model = DatasetSubmission
        fields = [
            "id", "reference", "organization", "dataset_name", "data_type", "dataset_version", "version_number", "status",
            "report_status", "quality_score", "review_comment", "submitted_at", "reviewed_at", "events",
        ]
        read_only_fields = fields


class ReviewActionSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000)
