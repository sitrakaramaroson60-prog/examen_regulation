from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    OPERATOR_USER = "OPERATOR_USER", "Utilisateur opérateur"
    ARTEC_PUBLISHER = "ARTEC_PUBLISHER", "ARTEC — Publications"
    ARTEC_REGULATOR = "ARTEC_REGULATOR", "ARTEC — Régulation et prédiction"
    SYSTEM_ADMIN = "SYSTEM_ADMIN", "Administrateur système"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("L'adresse email est obligatoire.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.full_clean(exclude=["password"])
        user.save()
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("role", Role.SYSTEM_ADMIN)
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._create(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    organization = models.ForeignKey(
        "organizations.Organization", null=True, blank=True, on_delete=models.PROTECT, related_name="users"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.OPERATOR_USER)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["email"]
        indexes = [models.Index(fields=["role"]), models.Index(fields=["organization", "role"])]

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()
        org = self.organization
        if self.role == Role.OPERATOR_USER:
            if org is None or org.organization_type != "OPERATOR":
                raise ValidationError({"organization": "Un compte opérateur doit appartenir à YAS, AIRTEL ou ORANGE."})
        elif self.role in (Role.ARTEC_PUBLISHER, Role.ARTEC_REGULATOR):
            if org is None or org.code != "ARTEC":
                raise ValidationError({"organization": "Ce rôle exige l'appartenance à l'organisation ARTEC."})
        elif self.role == Role.SYSTEM_ADMIN:
            if org is not None and org.code != "ARTEC":
                raise ValidationError({"organization": "Un administrateur système ne peut pas appartenir à un opérateur."})

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        self.clean()
        super().save(*args, **kwargs)

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    @property
    def space(self):
        return {
            Role.OPERATOR_USER: "operator",
            Role.ARTEC_PUBLISHER: "publications",
            Role.ARTEC_REGULATOR: "regulation",
            Role.SYSTEM_ADMIN: "admin",
        }[self.role]
