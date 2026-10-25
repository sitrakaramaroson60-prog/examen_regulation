"""Permissions réutilisables. Le rôle est TOUJOURS lu depuis la base (request.user), jamais depuis le client."""
from rest_framework.permissions import SAFE_METHODS, BasePermission

OPERATOR_USER = "OPERATOR_USER"
ARTEC_PUBLISHER = "ARTEC_PUBLISHER"
ARTEC_REGULATOR = "ARTEC_REGULATOR"
SYSTEM_ADMIN = "SYSTEM_ADMIN"


def has_role(user, *roles):
    return bool(user and user.is_authenticated and user.is_active and user.role in roles)


def roles_required(*roles, read_only_roles=()):
    """Fabrique une classe de permission : rôles autorisés (+ rôles en lecture seule)."""

    class _RolePermission(BasePermission):
        message = "Votre rôle ne permet pas cette opération."

        def has_permission(self, request, view):
            user = request.user
            if not (user and user.is_authenticated and user.is_active):
                return False
            if user.role in roles:
                return True
            return request.method in SAFE_METHODS and user.role in read_only_roles

    _RolePermission.__name__ = "Roles_" + "_".join(roles)
    return _RolePermission


IsOperatorUser = roles_required(OPERATOR_USER)
IsArtecPublisher = roles_required(ARTEC_PUBLISHER)
IsArtecRegulator = roles_required(ARTEC_REGULATOR)
IsSystemAdmin = roles_required(SYSTEM_ADMIN)
IsProfessional = roles_required(OPERATOR_USER, ARTEC_PUBLISHER, ARTEC_REGULATOR, SYSTEM_ADMIN)


class OrganizationScopedMixin:
    """Filtre un queryset par organisation de l'utilisateur connecté (isolation des opérateurs).

    Les vues définissent `org_field` ; un objet d'une autre organisation répond 404
    (et non 403) afin de ne pas révéler son existence.
    """

    org_field = "organization"

    def scope_to_user_org(self, queryset):
        user = self.request.user
        if not user.is_authenticated or user.organization_id is None:
            return queryset.none()
        return queryset.filter(**{self.org_field: user.organization_id})
