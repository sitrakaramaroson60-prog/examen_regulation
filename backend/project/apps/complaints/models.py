from django.db import models

from apps.common.files import private_storage


class Complaint(models.Model):
    class Type(models.TextChoices):
        PUBLIC_COMPLAINT = "PUBLIC_COMPLAINT", "Réclamation du public"
        REPORT = "REPORT", "Signalement"
        OPERATOR_CONTESTATION = "OPERATOR_CONTESTATION", "Contestation d'opérateur"
        REVIEW_REQUEST = "REVIEW_REQUEST", "Demande de réexamen"

    class Status(models.TextChoices):
        NEW = "NEW", "Nouvelle"
        IN_REVIEW = "IN_REVIEW", "En traitement"
        AWAITING_INFO = "AWAITING_INFO", "En attente d'informations"
        RESOLVED = "RESOLVED", "Traitée"
        REJECTED = "REJECTED", "Rejetée"
        CLOSED = "CLOSED", "Clôturée"

    reference = models.CharField(max_length=30, unique=True, blank=True)
    complaint_type = models.CharField(max_length=25, choices=Type.choices)
    category = models.CharField(max_length=60)
    description = models.TextField()
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.NEW, db_index=True)
    submitter = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="complaints")
    organization = models.ForeignKey("organizations.Organization", null=True, blank=True, on_delete=models.PROTECT, related_name="complaints",
                                     help_text="Organisme déposant (contestations).")
    target_operator = models.ForeignKey("organizations.Organization", null=True, blank=True, on_delete=models.PROTECT, related_name="complaints_about")
    region = models.ForeignKey("organizations.Region", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    city = models.ForeignKey("organizations.City", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    contact_email = models.EmailField(blank=True)
    tracking_token_hash = models.CharField(max_length=64, blank=True)
    related_case = models.ForeignKey("regulation.RegulatoryCase", null=True, blank=True, on_delete=models.SET_NULL, related_name="complaints")
    related_decision = models.ForeignKey("regulation.RegulatoryDecision", null=True, blank=True, on_delete=models.SET_NULL, related_name="complaints")
    assigned_to = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_complaints")
    deadline = models.DateField(null=True, blank=True)
    conclusion = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.reference:
            self.reference = f"CMP-{self.created_at.year}-{self.pk:05d}"
            super().save(update_fields=["reference"])


class ComplaintMessage(models.Model):
    class Author(models.TextChoices):
        SUBMITTER = "SUBMITTER", "Déposant"
        ARTEC = "ARTEC", "ARTEC"

    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name="messages")
    author_user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    author_kind = models.CharField(max_length=10, choices=Author.choices)
    content = models.TextField()
    is_internal = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


def attachment_path(instance, filename):
    return f"complaints/{instance.complaint_id}/{filename}"


class ComplaintAttachment(models.Model):
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=attachment_path, storage=private_storage)
    original_name = models.CharField(max_length=255)
    size = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
