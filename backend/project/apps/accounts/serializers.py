from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.services import log as audit_log
from apps.organizations.models import Organization
from apps.organizations.serializers import OrganizationBriefSerializer

from .models import Role, User


class UserSerializer(serializers.ModelSerializer):
    organization = OrganizationBriefSerializer(read_only=True)
    space = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "organization", "role", "space", "is_active", "date_joined", "last_login"]
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    GENERIC = "Identifiants invalides ou compte indisponible."

    def validate(self, attrs):
        request = self.context.get("request")
        email = attrs["email"].lower()
        user = User.objects.filter(email=email).first()
        if user and user.is_locked:
            audit_log(None, "auth.login_blocked", "User", user.pk, {"email": email}, request=request)
            raise AuthenticationFailed(self.GENERIC)
        auth_user = authenticate(request=request, username=email, password=attrs["password"])
        if auth_user is None:
            if user and user.is_active:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
                    user.locked_until = timezone.now() + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
                    user.failed_login_attempts = 0
                user.save(update_fields=["failed_login_attempts", "locked_until"])
            audit_log(None, "auth.login_failed", "User", user.pk if user else "", {"email": email}, request=request)
            raise AuthenticationFailed(self.GENERIC)
        auth_user.failed_login_attempts = 0
        auth_user.locked_until = None
        auth_user.last_login = timezone.now()
        auth_user.save(update_fields=["failed_login_attempts", "locked_until", "last_login"])
        refresh = RefreshToken.for_user(auth_user)
        audit_log(auth_user, "auth.login", "User", auth_user.pk, request=request)
        return {"access": str(refresh.access_token), "refresh": str(refresh), "user": UserSerializer(auth_user).data}


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value

    def validate_new_password(self, value):
        try:
            validate_password(value, self.context["request"].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class AdminUserSerializer(serializers.ModelSerializer):
    """Création / gestion des comptes professionnels — réservée à SYSTEM_ADMIN."""

    organization = serializers.SlugRelatedField(slug_field="code", queryset=Organization.objects.filter(is_active=True), required=False, allow_null=True)
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "organization", "role", "is_active", "password", "date_joined", "last_login"]
        read_only_fields = ["id", "date_joined", "last_login"]

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def validate(self, attrs):
        if self.context.get("operators_only"):
            role = attrs.get("role", getattr(self.instance, "role", Role.OPERATOR_USER))
            org = attrs.get("organization", getattr(self.instance, "organization", None))
            if role != Role.OPERATOR_USER or (org is not None and org.organization_type != "OPERATOR"):
                raise serializers.ValidationError({"role": "Vous ne pouvez gérer que des comptes d'opérateurs."})
        probe = User(
            email=attrs.get("email", getattr(self.instance, "email", "")),
            role=attrs.get("role", getattr(self.instance, "role", Role.OPERATOR_USER)),
            organization=attrs.get("organization", getattr(self.instance, "organization", None)),
        )
        try:
            probe.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError({"password": "Mot de passe obligatoire à la création."})
        return User.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
