from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_organization = serializers.CharField(source="actor_organization.code", default=None, read_only=True)

    class Meta:
        model = AuditLog
        fields = ["id", "actor_email", "actor_organization", "action", "resource_type", "resource_id", "timestamp", "metadata"]
        read_only_fields = fields
