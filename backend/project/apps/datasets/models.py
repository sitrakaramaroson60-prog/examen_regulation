from django.db import models

from apps.common.files import private_storage
from apps.common.models import TimeStampedModel

from .schemas import DATA_TYPES


class Dataset(models.Model):
    class Source(models.TextChoices):
        TECHNICAL = "TECHNICAL", "Mesures techniques"
        DECLARED = "DECLARED", "Déclaré par l'opérateur"
        SURVEY = "SURVEY", "Sondage"
        SCRAPED = "SCRAPED", "Web scraping"

    owner_organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="datasets")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    data_type = models.CharField(max_length=30, choices=DATA_TYPES)
    source_type = models.CharField(max_length=15, choices=Source.choices, default=Source.DECLARED)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="datasets")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["owner_organization", "data_type"])]
        constraints = [models.UniqueConstraint(fields=["owner_organization", "name"], name="uniq_dataset_name_per_org")]

    def __str__(self):
        return self.name


def version_path(instance, filename):
    # nom de fichier remplacé : on ne conserve jamais le nom fourni par l'utilisateur sur disque
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"datasets/{instance.dataset_id}/v{instance.version_number}.{ext}"


class DatasetVersion(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    file = models.FileField(upload_to=version_path, storage=private_storage)
    original_name = models.CharField(max_length=255)
    file_format = models.CharField(max_length=10)
    checksum = models.CharField(max_length=64)
    schema_definition = models.JSONField(default=dict, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["dataset", "-version_number"]
        constraints = [models.UniqueConstraint(fields=["dataset", "version_number"], name="uniq_version_per_dataset")]

    def __str__(self):
        return f"{self.dataset.name} v{self.version_number}"


class DatasetValidationReport(models.Model):
    class Status(models.TextChoices):
        VALID = "VALID", "Valide"
        VALID_WITH_WARNINGS = "VALID_WITH_WARNINGS", "Valide avec avertissements"
        INVALID = "INVALID", "Invalide"

    dataset_version = models.OneToOneField(DatasetVersion, on_delete=models.CASCADE, related_name="report")
    status = models.CharField(max_length=25, choices=Status.choices)
    row_count = models.PositiveIntegerField(default=0)
    missing_columns = models.JSONField(default=list)
    type_errors = models.JSONField(default=dict)
    missing_values = models.JSONField(default=dict)
    duplicate_rows = models.PositiveIntegerField(default=0)
    quality_score = models.FloatField(default=0)
    messages = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now=True)


class DatasetSubmission(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Soumis"
        UNDER_REVIEW = "UNDER_REVIEW", "En examen"
        CORRECTION_REQUIRED = "CORRECTION_REQUIRED", "Correction demandée"
        ACCEPTED = "ACCEPTED", "Accepté"
        REJECTED = "REJECTED", "Rejeté"

    reference = models.CharField(max_length=30, unique=True, blank=True)
    dataset_version = models.ForeignKey(DatasetVersion, on_delete=models.PROTECT, related_name="submissions")
    submitted_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    reviewed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    review_comment = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.reference:
            self.reference = f"DS-{self.submitted_at.year}-{self.pk:04d}"
            super().save(update_fields=["reference"])


class SubmissionEvent(models.Model):
    """Historique des décisions et transitions (jamais modifié)."""

    submission = models.ForeignKey(DatasetSubmission, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    from_status = models.CharField(max_length=25, blank=True)
    to_status = models.CharField(max_length=25)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
