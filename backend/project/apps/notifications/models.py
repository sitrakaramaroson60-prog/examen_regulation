from django.db import models


class Notification(models.Model):
    class Type(models.TextChoices):
        DATASET_SUBMITTED = "DATASET_SUBMITTED", "Nouvelle soumission de dataset"
        CORRECTION_REQUESTED = "CORRECTION_REQUESTED", "Demande de correction"
        DATASET_ACCEPTED = "DATASET_ACCEPTED", "Dataset accepté"
        DATASET_REJECTED = "DATASET_REJECTED", "Dataset rejeté"
        CONTESTATION = "CONTESTATION", "Nouvelle contestation"
        EXPLANATION_REQUESTED = "EXPLANATION_REQUESTED", "Demande d'explication"
        RESPONSE_RECEIVED = "RESPONSE_RECEIVED", "Réponse reçue"
        DECISION = "DECISION", "Décision rendue"
        DEADLINE = "DEADLINE", "Échéance proche"
        SCRAPING_FAILED = "SCRAPING_FAILED", "Échec de scraping"
        PREDICTION_DONE = "PREDICTION_DONE", "Prédiction terminée"
        SURVEY_APPROVAL = "SURVEY_APPROVAL", "Sondage à valider"
        OTHER = "OTHER", "Autre"

    recipient = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    notification_type = models.CharField(max_length=30, choices=Type.choices, default=Type.OTHER)
    related_resource_type = models.CharField(max_length=60, blank=True)
    related_resource_id = models.CharField(max_length=64, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["recipient", "is_read"])]
