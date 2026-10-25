from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.common.files import private_storage
from apps.common.models import TimeStampedModel


class Publication(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        SCHEDULED = "SCHEDULED", "Planifiée"
        PUBLISHED = "PUBLISHED", "Publiée"
        ARCHIVED = "ARCHIVED", "Archivée"

    class Audience(models.TextChoices):
        PUBLIC = "PUBLIC", "Public"
        INTERNAL = "INTERNAL", "Interne (organismes connectés)"

    class Category(models.TextChoices):
        REPORT = "REPORT", "Rapport"
        PRESS_RELEASE = "PRESS_RELEASE", "Communiqué"
        INFORMATION = "INFORMATION", "Information"
        CONSULTATION = "CONSULTATION", "Consultation"
        OTHER = "OTHER", "Autre"

    author = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="publications")
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="publications")
    title = models.CharField(max_length=250)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    content = models.TextField()
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.INFORMATION)
    audience = models.CharField(max_length=10, choices=Audience.choices, default=Audience.PUBLIC)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:240] or "publication"
            slug, i = base, 1
            while Publication.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def is_publicly_visible(self):
        return (
            self.status == self.Status.PUBLISHED
            and self.audience == self.Audience.PUBLIC
            and self.published_at is not None
            and self.published_at <= timezone.now()
        )


def attachment_path(instance, filename):
    return f"publications/{instance.publication_id}/{filename}"


ALLOWED_ATTACHMENT_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "docx", "xlsx", "csv"}


class PublicationAttachment(models.Model):
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=attachment_path, storage=private_storage)
    original_name = models.CharField(max_length=255)
    size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class Comment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        APPROVED = "APPROVED", "Approuvé"
        REJECTED = "REJECTED", "Rejeté"
        HIDDEN = "HIDDEN", "Masqué"

    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name="comments")
    content = models.TextField(max_length=2000)
    author_name = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    report_count = models.PositiveIntegerField(default=0)
    moderated_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class CommentReport(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="reports")
    reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
