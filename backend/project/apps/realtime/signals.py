"""Chaque écriture métier importante publie un événement ciblé. Aucun service métier n'est modifié :
les règles ci-dessous disent, pour chaque modèle, QUI doit être prévenu et sur QUEL thème."""
from django.db.models.signals import post_delete, post_save

from .bus import PUBLIC, org, publish, role, user

REG, PUB, ADMIN, OPS = role("ARTEC_REGULATOR"), role("ARTEC_PUBLISHER"), role("SYSTEM_ADMIN"), role("OPERATOR_USER")


def _case_aud(case):
    return [org(case.operator_id), REG]


RULES = {
    # modèle : (thème, fonction(instance) -> liste de publics)
    "accounts.User": ("users", lambda o: [ADMIN, REG, user(o.pk)]),
    "datasets.Dataset": ("datasets", lambda o: [org(o.owner_organization_id), REG]),
    "datasets.DatasetVersion": ("datasets", lambda o: [org(o.dataset.owner_organization_id), REG]),
    "datasets.DatasetSubmission": ("submissions", lambda o: [org(o.dataset_version.dataset.owner_organization_id), REG]),
    "surveys.Survey": ("surveys", lambda o: [org(o.organization_id), PUB, REG] + ([PUBLIC] if o.status in ("PUBLISHED", "CLOSED") else [])),
    "surveys.SurveyResponse": ("surveys", lambda o: [org(o.survey.organization_id)] + ([PUBLIC, REG] if o.survey.results_public else [])),
    "publications.Publication": ("publications", lambda o: [org(o.organization_id)] + ([PUBLIC] if o.status == "PUBLISHED" and o.audience == "PUBLIC" else [])),
    "publications.Comment": ("comments", lambda o: [org(o.publication.organization_id)] + ([PUBLIC] if o.status == "APPROVED" else [])),
    "regulation.RegulatoryCase": ("cases", _case_aud),
    "regulation.CaseEvent": ("cases", lambda o: [REG] if o.internal else _case_aud(o.case)),
    "regulation.RegulatoryDecision": ("cases", lambda o: _case_aud(o.case)),
    "regulation.RegulatoryEvidence": ("cases", lambda o: _case_aud(o.case) if o.visible_to_operator else [REG]),
    "regulation.OperatorResponse": ("cases", lambda o: _case_aud(o.case)),
    "regulation.CorrectiveAction": ("cases", lambda o: _case_aud(o.case)),
    "regulation.FollowUpCheck": ("cases", lambda o: _case_aud(o.corrective_action.case)),
    "regulation.Obligation": ("obligations", lambda o: [org(o.operator_id), REG]),
    "regulation.ObligationEvaluation": ("obligations", lambda o: [org(o.obligation.operator_id), REG]),
    "regulation.ComplianceAlert": ("obligations", lambda o: [REG]),  # alertes internes : jamais côté opérateur
    "complaints.Complaint": ("complaints", lambda o: [REG] + ([org(o.organization_id)] if o.organization_id else [])),
    "complaints.ComplaintMessage": ("complaints", lambda o: [REG] + ([] if o.is_internal or not o.complaint.organization_id else [org(o.complaint.organization_id)])),
    "predictions.PredictionModel": ("predictions", lambda o: [REG]),
    "predictions.PredictionRun": ("predictions", lambda o: [REG]),
    "scraping.ScrapingJob": ("scraping", lambda o: [org(o.organization_id)]),
    "scraping.ScrapingExecution": ("scraping", lambda o: [org(o.job.organization_id)]),
    "scraping.ScrapedRecord": ("scraping", lambda o: [org(o.organization_id)]),
    "qos.QoSThreshold": ("thresholds", lambda o: [REG, OPS]),
    "qos.PublicBarometerSetting": ("qos", lambda o: [REG, PUBLIC]),
    "notifications.Notification": ("notifications", lambda o: [user(o.recipient_id)]),
    "audit.AuditLog": ("audit", lambda o: [ADMIN, REG] + ([org(o.actor_organization_id)] if o.actor_organization_id else [])),
}


SKIP_ON_CREATE = {"qos.PublicBarometerSetting"}  # création paresseuse du réglage par défaut : pas un événement


def _make_handler(topic, resolver, action_on_create="created"):
    def handler(sender, instance, created=False, raw=False, **kwargs):
        if raw or (created and sender._meta.label in SKIP_ON_CREATE):
            return
        try:
            audiences = resolver(instance)
        except Exception:  # noqa: BLE001 — une relation absente ne doit jamais bloquer l'enregistrement
            return
        publish(topic, audiences, ref=instance, action=action_on_create if created else "updated")

    return handler


for label, (topic, resolver) in RULES.items():
    post_save.connect(_make_handler(topic, resolver), sender=label, weak=False, dispatch_uid=f"rt-save-{label}")

for label in ("publications.Publication", "publications.Comment", "scraping.ScrapingJob"):
    topic, resolver = RULES[label]

    def _deleted(sender, instance, _t=topic, _r=resolver, **kw):
        try:
            publish(_t, _r(instance), ref=instance, action="deleted")
        except Exception:  # noqa: BLE001
            pass

    post_delete.connect(_deleted, sender=label, weak=False, dispatch_uid=f"rt-del-{label}")
