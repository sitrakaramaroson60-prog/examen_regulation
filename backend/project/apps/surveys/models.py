from django.db import models

from apps.common.models import TimeStampedModel


class Survey(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        PENDING_APPROVAL = "PENDING_APPROVAL", "En attente de validation"
        PUBLISHED = "PUBLISHED", "Publié"
        CLOSED = "CLOSED", "Clos"
        ARCHIVED = "ARCHIVED", "Archivé"

    class DuplicatePolicy(models.TextChoices):
        NONE = "NONE", "Aucune restriction (limitation de débit seulement)"
        ONE_PER_DAY = "ONE_PER_DAY", "Une réponse par jour et par empreinte anonyme"
        ONE_TOTAL = "ONE_TOTAL", "Une seule réponse par empreinte anonyme"

    title = models.CharField(max_length=250)
    description = models.TextField(blank=True)
    creator = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="surveys")
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="surveys")
    target_operator = models.ForeignKey(
        "organizations.Organization", null=True, blank=True, on_delete=models.PROTECT, related_name="targeted_surveys",
        help_text="Opérateur évalué (vide = tous les opérateurs).",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    estimated_minutes = models.PositiveSmallIntegerField(default=4)
    results_public = models.BooleanField(default=False)
    duplicate_policy = models.CharField(max_length=15, choices=DuplicatePolicy.choices, default=DuplicatePolicy.ONE_PER_DAY)
    require_participation_token = models.BooleanField(default=True)
    rejection_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self):
        return self.title


class SurveyQuestion(models.Model):
    class Type(models.TextChoices):
        SHORT_TEXT = "SHORT_TEXT", "Texte court"
        LONG_TEXT = "LONG_TEXT", "Texte long"
        SINGLE_CHOICE = "SINGLE_CHOICE", "Choix unique"
        MULTIPLE_CHOICE = "MULTIPLE_CHOICE", "Choix multiple"
        SATISFACTION = "SATISFACTION", "Échelle de satisfaction"
        NUMBER = "NUMBER", "Nombre"
        YES_NO = "YES_NO", "Oui/non"

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="questions")
    text = models.CharField(max_length=500)
    question_type = models.CharField(max_length=20, choices=Type.choices)
    is_required = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)
    min_value = models.FloatField(null=True, blank=True)
    max_value = models.FloatField(null=True, blank=True)
    max_length = models.PositiveSmallIntegerField(null=True, blank=True)
    qos_metric = models.CharField(
        max_length=40, blank=True,
        help_text="Indicateur QoS alimenté par les réponses (questions numériques ou de satisfaction).",
    )

    class Meta:
        ordering = ["order", "id"]


class SurveyChoice(models.Model):
    question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE, related_name="choices")
    label = models.CharField(max_length=200)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]


class SurveyResponse(models.Model):
    class Context(models.TextChoices):
        RESIDENCE = "RESIDENCE", "Lieu de résidence"
        USAGE = "USAGE", "Lieu d'utilisation du service"

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="responses")
    region = models.ForeignKey("organizations.Region", on_delete=models.PROTECT, related_name="+")
    city = models.ForeignKey("organizations.City", on_delete=models.PROTECT, related_name="+")
    location_context = models.CharField(max_length=10, choices=Context.choices)
    operator = models.ForeignKey("organizations.Organization", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    service_type = models.CharField(max_length=30, blank=True)
    # Empreinte anonyme salée (HMAC) — ni IP ni identifiant direct n'est conservé.
    fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["survey", "region"])]


class SurveyAnswer(models.Model):
    response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE, related_name="answers")
    text_value = models.TextField(blank=True)
    number_value = models.FloatField(null=True, blank=True)
    bool_value = models.BooleanField(null=True, blank=True)
    choices = models.ManyToManyField(SurveyChoice, blank=True, related_name="answers")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["response", "question"], name="one_answer_per_question")]
