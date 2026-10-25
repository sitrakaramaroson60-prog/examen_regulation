from django.db import models


class ScrapingSource(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="scraping_sources")
    name = models.CharField(max_length=150)
    base_url = models.URLField(max_length=500)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="uniq_source_name_per_org")]


class ScrapingJob(models.Model):
    class Frequency(models.TextChoices):
        MANUAL = "MANUAL", "Manuelle"
        HOURLY = "HOURLY", "Horaire"
        DAILY = "DAILY", "Quotidienne"
        WEEKLY = "WEEKLY", "Hebdomadaire"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        PAUSED = "PAUSED", "En pause"
        RUNNING = "RUNNING", "En cours"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="scraping_jobs")
    source = models.ForeignKey(ScrapingSource, on_delete=models.PROTECT, related_name="jobs")
    name = models.CharField(max_length=150)
    url = models.URLField(max_length=500, help_text="URL autorisée (domaine présent dans la liste blanche).")
    data_type = models.CharField(max_length=50, default="web_page")
    frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.MANUAL)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_result = models.CharField(max_length=300, blank=True)
    items_collected = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["organization", "status"])]


class ScrapingExecution(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "En cours"
        SUCCESS = "SUCCESS", "Succès"
        FAILED = "FAILED", "Échec"
        BLOCKED = "BLOCKED", "Bloquée (politique de sécurité)"

    job = models.ForeignKey(ScrapingJob, on_delete=models.CASCADE, related_name="executions")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    items_collected = models.PositiveIntegerField(default=0)
    errors = models.PositiveIntegerField(default=0)
    log = models.JSONField(default=list)

    class Meta:
        ordering = ["-started_at"]


class ScrapedRecord(models.Model):
    class Validation(models.TextChoices):
        PENDING = "PENDING", "À valider"
        VALIDATED = "VALIDATED", "Validée"
        REJECTED = "REJECTED", "Rejetée"

    job = models.ForeignKey(ScrapingJob, on_delete=models.CASCADE, related_name="records")
    execution = models.ForeignKey(ScrapingExecution, on_delete=models.CASCADE, related_name="records")
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="scraped_records")
    source_url = models.URLField(max_length=1000)  # provenance
    final_url = models.URLField(max_length=1000, blank=True)
    http_status = models.PositiveSmallIntegerField(null=True)
    content_type = models.CharField(max_length=100, blank=True)
    content_hash = models.CharField(max_length=64)
    data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)
    validation_status = models.CharField(max_length=10, choices=Validation.choices, default=Validation.PENDING, db_index=True)
    validated_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    validated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fetched_at"]
        indexes = [models.Index(fields=["organization", "validation_status"])]
