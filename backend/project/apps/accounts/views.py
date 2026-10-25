from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.audit.services import log as audit_log
from apps.common.permissions import ARTEC_REGULATOR, SYSTEM_ADMIN, roles_required

from .models import User
from .serializers import (
    AdminUserSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    UserSerializer,
)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "login"
    throttle_classes = [ScopedRateThrottle]

    @extend_schema(request=LoginSerializer, responses={200: dict})
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class RefreshView(TokenRefreshView):
    throttle_scope = "login"
    throttle_classes = [ScopedRateThrottle]


class LogoutView(APIView):
    @extend_schema(request=LogoutSerializer, responses={204: None})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            if str(token.get("user_id")) != str(request.user.pk):
                return Response({"detail": "Jeton invalide."}, status=status.HTTP_400_BAD_REQUEST)
            token.blacklist()
        except TokenError:
            return Response({"detail": "Jeton invalide ou déjà révoqué."}, status=status.HTTP_400_BAD_REQUEST)
        audit_log(request.user, "auth.logout", "User", request.user.pk, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    @extend_schema(responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    @extend_schema(request=ChangePasswordSerializer, responses={204: None})
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        # révoque les sessions (refresh tokens) existantes
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

        for outstanding in OutstandingToken.objects.filter(user=request.user):
            BlacklistedToken.objects.get_or_create(token=outstanding)
        audit_log(request.user, "auth.password_changed", "User", request.user.pk, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserAdminViewSet(viewsets.ModelViewSet):
    """Gestion des comptes. SYSTEM_ADMIN : tous les comptes. ARTEC Régulation : comptes des opérateurs uniquement
    (jamais de compte ARTEC ni administrateur : pas d'élévation de privilèges). Pas de suppression : désactivation."""

    serializer_class = AdminUserSerializer
    permission_classes = [roles_required(SYSTEM_ADMIN, ARTEC_REGULATOR)]
    filterset_fields = ["role", "organization__code", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = User.objects.select_related("organization")
        return qs if self.request.user.role == SYSTEM_ADMIN else qs.filter(role="OPERATOR_USER")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "operators_only": self.request.user.role != SYSTEM_ADMIN}

    def perform_create(self, serializer):
        user = serializer.save()
        audit_log(self.request.user, "user.created", "User", user.pk, {"role": user.role, "organization": getattr(user.organization, "code", None)}, request=self.request)

    def perform_update(self, serializer):
        before = {"role": serializer.instance.role, "is_active": serializer.instance.is_active}
        user = serializer.save()
        audit_log(
            self.request.user,
            "user.updated",
            "User",
            user.pk,
            {"before": before, "after": {"role": user.role, "is_active": user.is_active}},
            request=self.request,
        )
