from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.common.permissions import ARTEC_PUBLISHER, ARTEC_REGULATOR, OPERATOR_USER, SYSTEM_ADMIN

# L'ARTEC Régulation ne publie que des contenus réglementaires : rapports, indicateurs agrégés, consultations.
REGULATOR_CATEGORIES = ("REPORT", "CONSULTATION")


class CanManagePublications(BasePermission):
    """Écriture : ARTEC_PUBLISHER (toutes les publications ARTEC), ARTEC_REGULATOR (rapports et consultations) et
    OPERATOR_USER (publications de son organisme). Lecture : tous les rôles professionnels (dans les limites du queryset)."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated and u.is_active):
            return False
        if request.method in SAFE_METHODS:
            return u.role in (ARTEC_PUBLISHER, OPERATOR_USER, ARTEC_REGULATOR, SYSTEM_ADMIN)
        return u.role in (ARTEC_PUBLISHER, OPERATOR_USER, ARTEC_REGULATOR)
