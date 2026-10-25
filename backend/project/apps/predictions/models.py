from django.db import models


class PredictionModel(models.Model):
    class Status(models.TextChoices):
        TRAINING = "TRAINING", "Entraînement en cours"
        READY = "READY", "Prêt"
        NOT_READY = "NOT_READY", "Non prêt (données insuffisantes)"
        LOW_QUALITY = "LOW_QUALITY", "Performances insuffisantes"
        FAILED = "FAILED", "Échec"
        RETIRED = "RETIRED", "Retiré"

    name = models.CharField(max_length=100)
    version = models.PositiveIntegerField()
    model_type = models.CharField(max_length=40, default="softmax_logistic_regression")
    target_variable = models.CharField(max_length=60, default="quality_class")
    risk_type = models.CharField(max_length=30, default="GENERAL_QUALITY")
    feature_schema = models.JSONField(default=list)
    training_dataset_version = models.ForeignKey("datasets.DatasetVersion", on_delete=models.PROTECT, related_name="trained_models")
    metrics = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.TRAINING, db_index=True)
    status_reason = models.CharField(max_length=500, blank=True)
    artifact = models.CharField(max_length=300, blank=True)
    artifact_checksum = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["name", "-version"]
        constraints = [models.UniqueConstraint(fields=["name", "version"], name="uniq_model_version")]


class PredictionRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        RUNNING = "RUNNING", "En cours"
        COMPLETED = "COMPLETED", "Terminée"
        FAILED = "FAILED", "Échec"

    model_version = models.ForeignKey(PredictionModel, on_delete=models.PROTECT, related_name="runs")
    input_dataset_version = models.ForeignKey("datasets.DatasetVersion", on_delete=models.PROTECT, related_name="prediction_runs")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PredictionResult(models.Model):
    prediction_run = models.ForeignKey(PredictionRun, on_delete=models.CASCADE, related_name="results")
    observation_reference = models.CharField(max_length=100)
    predicted_class = models.CharField(max_length=10)
    probability_good = models.FloatField()
    probability_medium = models.FloatField()
    probability_poor = models.FloatField()
    confidence = models.FloatField()
    top_factors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["prediction_run", "predicted_class"])]
