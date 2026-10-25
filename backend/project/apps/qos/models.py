from django.db import models


class QoSMeasurement(models.Model):
    class SourceType(models.TextChoices):
        TECHNICAL = "TECHNICAL", "Mesure technique"
        DECLARED = "DECLARED", "Déclaré par l'opérateur"
        SURVEY = "SURVEY", "Sondage"
        SCRAPED = "SCRAPED", "Web scraping"

    class ValidationStatus(models.TextChoices):
        PENDING = "PENDING", "En attente"
        VALIDATED = "VALIDATED", "Validé"
        REJECTED = "REJECTED", "Rejeté"

    operator = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="qos_measurements")
    region = models.ForeignKey("organizations.Region", on_delete=models.PROTECT, related_name="+")
    city = models.ForeignKey("organizations.City", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    service_type = models.CharField(max_length=30)
    technology = models.CharField(max_length=20)
    metric_name = models.CharField(max_length=40)
    metric_value = models.FloatField()
    unit = models.CharField(max_length=20)
    measurement_method = models.CharField(max_length=60)
    source_type = models.CharField(max_length=15, choices=SourceType.choices)
    measured_at = models.DateTimeField()
    dataset_version = models.ForeignKey("datasets.DatasetVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="measurements")
    validation_status = models.CharField(max_length=10, choices=ValidationStatus.choices, default=ValidationStatus.PENDING)

    class Meta:
        ordering = ["-measured_at"]
        indexes = [
            models.Index(fields=["operator", "metric_name", "measured_at"]),
            models.Index(fields=["region", "metric_name"]),
            models.Index(fields=["validation_status"]),
        ]


class QoSThreshold(models.Model):
    """Seuil configurable. `origin` documente la source (texte réglementaire, décision interne, etc.).
    Aucun seuil officiel n'est livré avec l'application."""

    metric_name = models.CharField(max_length=40)
    technology = models.CharField(max_length=20, blank=True)
    service_type = models.CharField(max_length=30, blank=True)
    unit = models.CharField(max_length=20)
    good_threshold = models.FloatField(help_text="Valeur à partir de laquelle la mesure est considérée BONNE.")
    poor_threshold = models.FloatField(help_text="Valeur en deçà de laquelle la mesure est considérée MAUVAISE.")
    higher_is_better = models.BooleanField(default=True)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    origin = models.CharField(max_length=500, help_text="Source documentaire du seuil (obligatoire).")
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["metric_name", "-valid_from"]
        indexes = [models.Index(fields=["metric_name", "technology", "service_type"])]


class PublicBarometerSetting(models.Model):
    """Réglage unique (singleton) : l'ARTEC décide de publier ou non les indicateurs agrégés au public."""

    enabled = models.BooleanField(default=False)
    min_measurements = models.PositiveIntegerField(default=30)
    updated_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        from django.conf import settings

        obj, _ = cls.objects.get_or_create(pk=1, defaults={"enabled": settings.QOS_PUBLIC_ENABLED, "min_measurements": settings.QOS_PUBLIC_MIN_MEASUREMENTS})
        return obj
