from rest_framework import serializers

from . import safe_http
from .models import ScrapedRecord, ScrapingExecution, ScrapingJob, ScrapingSource


class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScrapingSource
        fields = ["id", "name", "base_url", "notes", "created_at"]
        read_only_fields = ["id", "created_at"]


class JobSerializer(serializers.ModelSerializer):
    source = serializers.PrimaryKeyRelatedField(queryset=ScrapingSource.objects.all())

    class Meta:
        model = ScrapingJob
        fields = [
            "id", "name", "source", "url", "data_type", "frequency", "status", "last_run_at", "last_result", "items_collected", "error_count", "created_at",
        ]
        read_only_fields = ["id", "last_run_at", "last_result", "items_collected", "error_count", "created_at"]

    def validate_status(self, value):
        if value not in ("ACTIVE", "PAUSED"):
            raise serializers.ValidationError("Statuts modifiables : ACTIVE, PAUSED.")
        return value

    def validate_source(self, source):
        if source.organization_id != self.context["request"].user.organization_id:
            raise serializers.ValidationError("Source introuvable.")
        return source

    def validate_url(self, url):
        try:
            safe_http.check_url(url)
        except safe_http.ScrapingNotConfigured as exc:
            raise serializers.ValidationError(str(exc))
        except safe_http.ScrapingBlocked as exc:
            raise serializers.ValidationError(str(exc))
        return url


class ExecutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScrapingExecution
        fields = ["id", "job", "status", "started_at", "finished_at", "items_collected", "errors", "log"]
        read_only_fields = fields


class RecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScrapedRecord
        fields = ["id", "job", "execution", "source_url", "final_url", "http_status", "content_type", "content_hash", "data", "fetched_at", "validation_status", "validated_at"]
        read_only_fields = fields
