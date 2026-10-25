from django.db import models

from apps.common.files import private_storage


class RegulatoryCase(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Ouvert"
        UNDER_REVIEW = "UNDER_REVIEW", "En examen"
        AWAITING_OPERATOR_RESPONSE = "AWAITING_OPERATOR_RESPONSE", "En attente de la réponse de l'opérateur"
        UNDER_CORRECTION = "UNDER_CORRECTION", "En cours de correction"
        DECIDED = "DECIDED", "Décision rendue"
        CLOSED = "CLOSED", "Clos"

    class CaseType(models.TextChoices):
        QOS_ANOMALY = "QOS_ANOMALY", "Anomalie de qualité de service"
        DATA_QUALITY = "DATA_QUALITY", "Qualité des données transmises"
        COMPLAINT_FOLLOWUP = "COMPLAINT_FOLLOWUP", "Suite à réclamation"
        OBLIGATION_FOLLOWUP = "OBLIGATION_FOLLOWUP", "Suivi d'une obligation"
        RECOGNITION = "RECOGNITION", "Reconnaissance (félicitations)"
        OTHER = "OTHER", "Autre"

    reference_number = models.CharField(max_length=30, unique=True, blank=True)
    operator = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="regulatory_cases")
    case_type = models.CharField(max_length=25, choices=CaseType.choices)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.OPEN, db_index=True)
    title = models.CharField(max_length=250)
    description = models.TextField()
    related_prediction = models.ForeignKey("predictions.PredictionRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="cases")
    related_dataset_submission = models.ForeignKey("datasets.DatasetSubmission", null=True, blank=True, on_delete=models.SET_NULL, related_name="cases")
    related_alert = models.ForeignKey("regulation.ComplianceAlert", null=True, blank=True, on_delete=models.SET_NULL, related_name="cases")
    opened_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    assigned_to = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_cases")
    opened_at = models.DateTimeField(auto_now_add=True)
    deadline = models.DateField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        indexes = [models.Index(fields=["operator", "status"])]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.reference_number:
            self.reference_number = f"RC-{self.opened_at.year}-{self.pk:04d}"
            super().save(update_fields=["reference_number"])


class CaseEvent(models.Model):
    """Historique horodaté des actions sur un dossier. Jamais modifié ni supprimé."""

    class Kind(models.TextChoices):
        OPENED = "OPENED", "Ouverture"
        EXPLANATION_REQUESTED = "EXPLANATION_REQUESTED", "Demande d'explication"
        OPERATOR_RESPONSE = "OPERATOR_RESPONSE", "Réponse de l'opérateur"
        EVIDENCE_ADDED = "EVIDENCE_ADDED", "Élément de preuve ajouté"
        DECISION = "DECISION", "Décision"
        DECISION_AMENDED = "DECISION_AMENDED", "Décision modifiée"
        CORRECTIVE_ACTION = "CORRECTIVE_ACTION", "Action corrective"
        STATUS_CHANGE = "STATUS_CHANGE", "Changement de statut"
        NOTE = "NOTE", "Note interne"
        CLOSED = "CLOSED", "Clôture"

    case = models.ForeignKey(RegulatoryCase, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=25, choices=Kind.choices)
    actor = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    message = models.TextField(blank=True)
    internal = models.BooleanField(default=False, help_text="Visible de l'ARTEC uniquement.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


def evidence_path(instance, filename):
    return f"regulation/{instance.case_id}/{filename}"


class RegulatoryEvidence(models.Model):
    class Kind(models.TextChoices):
        DATASET = "DATASET", "Dataset"
        MEASUREMENT = "MEASUREMENT", "Mesures QoS validées"
        PREDICTION = "PREDICTION", "Résultat de prédiction (indicatif)"
        DOCUMENT = "DOCUMENT", "Document"
        OTHER = "OTHER", "Autre"

    case = models.ForeignKey(RegulatoryCase, on_delete=models.CASCADE, related_name="evidence")
    kind = models.CharField(max_length=15, choices=Kind.choices)
    description = models.TextField()
    file = models.FileField(upload_to=evidence_path, storage=private_storage, null=True, blank=True)
    dataset_submission = models.ForeignKey("datasets.DatasetSubmission", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    prediction_run = models.ForeignKey("predictions.PredictionRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    visible_to_operator = models.BooleanField(default=True)
    added_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)


class OperatorResponse(models.Model):
    case = models.ForeignKey(RegulatoryCase, on_delete=models.CASCADE, related_name="responses")
    responder = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class RegulatoryDecision(models.Model):
    class Category(models.TextChoices):
        EXPLANATION_REQUEST = "EXPLANATION_REQUEST", "Demande d'explication"
        RECOMMENDATION = "RECOMMENDATION", "Recommandation"
        CORRECTION_REQUEST = "CORRECTION_REQUEST", "Demande de correction"
        WARNING = "WARNING", "Avertissement"
        CONGRATULATIONS = "CONGRATULATIONS", "Félicitation"
        NO_BREACH = "NO_BREACH", "Absence de manquement établi"
        CLOSURE = "CLOSURE", "Clôture"

    case = models.ForeignKey(RegulatoryCase, on_delete=models.PROTECT, related_name="decisions")
    category = models.CharField(max_length=25, choices=Category.choices)
    justification = models.TextField()
    decided_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    decided_at = models.DateTimeField(auto_now_add=True)
    evidence = models.ManyToManyField(RegulatoryEvidence, blank=True, related_name="decisions")
    supersedes = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="superseded_by")
    amendment_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["decided_at", "id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Une décision est immuable : utilisez la procédure de modification motivée.")
        super().save(*args, **kwargs)

    @property
    def is_current(self):
        return not hasattr(self, "superseded_by")


class CorrectiveAction(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "Demandée"
        IN_PROGRESS = "IN_PROGRESS", "En cours"
        SUBMITTED = "SUBMITTED", "Transmise pour vérification"
        VERIFIED = "VERIFIED", "Vérifiée"
        NOT_COMPLIED = "NOT_COMPLIED", "Non réalisée"

    case = models.ForeignKey(RegulatoryCase, on_delete=models.CASCADE, related_name="corrective_actions")
    decision = models.ForeignKey(RegulatoryDecision, null=True, blank=True, on_delete=models.PROTECT, related_name="corrective_actions")
    description = models.TextField()
    due_date = models.DateField()
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.REQUESTED)
    operator_report = models.TextField(blank=True)
    verification_comment = models.TextField(blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date"]


class Obligation(models.Model):
    """Engagement d'un opérateur (cahier des charges, décision, convention…). Les valeurs cibles sont saisies par l'ARTEC :
    aucune obligation « officielle » n'est livrée avec l'application."""

    class Comparison(models.TextChoices):
        GTE = "GTE", "Doit être supérieur ou égal à la cible"
        LTE = "LTE", "Doit être inférieur ou égal à la cible"

    operator = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="obligations")
    title = models.CharField(max_length=250)
    description = models.TextField(blank=True)
    legal_basis = models.CharField(max_length=500, help_text="Texte ou décision à l'origine de l'engagement (obligatoire).")
    metric_name = models.CharField(max_length=40)
    unit = models.CharField(max_length=20)
    comparison = models.CharField(max_length=3, choices=Comparison.choices)
    target_value = models.FloatField()
    measurement_method = models.CharField(max_length=60, help_text="Méthode de mesure de référence : seules ces mesures sont évaluées.")
    technology = models.CharField(max_length=20, blank=True)
    service_type = models.CharField(max_length=30, blank=True)
    region = models.ForeignKey("organizations.Region", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    evaluation_window_days = models.PositiveSmallIntegerField(default=30)
    min_samples = models.PositiveSmallIntegerField(default=10)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["operator__code", "metric_name"]
        indexes = [models.Index(fields=["operator", "is_active"])]


class ObligationEvaluation(models.Model):
    class Status(models.TextChoices):
        COMPLIANT = "COMPLIANT", "Conforme"
        NON_COMPLIANT = "NON_COMPLIANT", "Écart détecté"
        INSUFFICIENT_DATA = "INSUFFICIENT_DATA", "Données insuffisantes"

    obligation = models.ForeignKey(Obligation, on_delete=models.CASCADE, related_name="evaluations")
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    measured_value = models.FloatField(null=True, blank=True)
    sample_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices)
    gap = models.FloatField(null=True, blank=True)
    gap_pct = models.FloatField(null=True, blank=True)
    evaluated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-evaluated_at", "-id"]


class ComplianceAlert(models.Model):
    """ALERTE ALGORITHMIQUE : produite automatiquement par l'évaluation des obligations. Ce n'est ni une décision ni une
    sanction : seule une personne habilitée peut l'escalader en dossier, puis rendre une décision motivée."""

    class Severity(models.TextChoices):
        INFO = "INFO", "Information"
        WARNING = "WARNING", "Vigilance"
        CRITICAL = "CRITICAL", "Écart important"

    class Status(models.TextChoices):
        NEW = "NEW", "Nouvelle"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Prise en compte"
        DISMISSED = "DISMISSED", "Classée sans suite"
        ESCALATED = "ESCALATED", "Transformée en dossier"

    obligation = models.ForeignKey(Obligation, on_delete=models.CASCADE, related_name="alerts")
    evaluation = models.ForeignKey(ObligationEvaluation, on_delete=models.CASCADE, related_name="alerts")
    severity = models.CharField(max_length=10, choices=Severity.choices)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.NEW, db_index=True)
    message = models.CharField(max_length=500)
    handled_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    handled_at = models.DateTimeField(null=True, blank=True)
    handling_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class FollowUpCheck(models.Model):
    """Contrôle de suivi d'une action corrective."""

    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planifié"
        DONE = "DONE", "Réalisé"

    class Outcome(models.TextChoices):
        COMPLIANT = "COMPLIANT", "Conforme"
        PARTIAL = "PARTIAL", "Partiellement conforme"
        NON_COMPLIANT = "NON_COMPLIANT", "Non conforme"

    corrective_action = models.ForeignKey(CorrectiveAction, on_delete=models.CASCADE, related_name="checks")
    due_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNED)
    outcome = models.CharField(max_length=15, choices=Outcome.choices, blank=True)
    notes = models.TextField(blank=True)
    planned_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    performed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    performed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_date"]
