from rest_framework import viewsets

from apps.common.permissions import (
    ARTEC_PUBLISHER,
    ARTEC_REGULATOR,
    OPERATOR_USER,
    SYSTEM_ADMIN,
    roles_required,
)

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Consultation seule. SYSTEM_ADMIN et ARTEC_REGULATOR : vue globale ; les autres : leur organisation."""

    serializer_class = AuditLogSerializer
    permission_classes = [roles_required(OPERATOR_USER, ARTEC_PUBLISHER, ARTEC_REGULATOR, SYSTEM_ADMIN)]
    filterset_fields = ["action", "resource_type", "resource_id"]
    search_fields = ["action", "actor_email"]

    def get_queryset(self):
        qs = AuditLog.objects.select_related("actor_organization")
        user = self.request.user
        if user.role in (SYSTEM_ADMIN, ARTEC_REGULATOR):
            return qs
        return qs.filter(actor_organization=user.organization)
