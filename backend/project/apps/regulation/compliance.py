"""Évaluation des obligations par rapport aux mesures validées.

Règles : seules les mesures TECHNIQUES validées, de la méthode de référence de l'obligation, sont comparées (jamais
les déclarations de l'opérateur). Un écart produit une ALERTE ALGORITHMIQUE ; aucune décision ni sanction n'est créée.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import log as audit_log
from apps.notifications.models import Notification
from apps.notifications.services import notify, users_of
from apps.qos.models import QoSMeasurement

from .models import ComplianceAlert, Obligation, ObligationEvaluation, RegulatoryCase, RegulatoryEvidence

NATURE = "ALERTE_ALGORITHMIQUE — indication automatique, qui n'est pas une décision réglementaire."


def _severity(gap_pct):
    if gap_pct is None:
        return ComplianceAlert.Severity.WARNING
    a = abs(gap_pct)
    return ComplianceAlert.Severity.CRITICAL if a >= 20 else ComplianceAlert.Severity.WARNING if a >= 5 else ComplianceAlert.Severity.INFO


@transaction.atomic
def evaluate(obligation, actor=None, now=None):
    now = now or timezone.now()
    if not obligation.is_active or obligation.valid_from > now.date() or (obligation.valid_until and obligation.valid_until < now.date()):
        raise ValidationError("Cette obligation n'est pas en vigueur.")
    start = now - timedelta(days=obligation.evaluation_window_days)
    qs = QoSMeasurement.objects.filter(
        operator=obligation.operator, metric_name=obligation.metric_name, unit=obligation.unit, measurement_method=obligation.measurement_method,
        source_type=QoSMeasurement.SourceType.TECHNICAL, validation_status=QoSMeasurement.ValidationStatus.VALIDATED, measured_at__gte=start, measured_at__lte=now,
    )
    if obligation.technology:
        qs = qs.filter(technology=obligation.technology)
    if obligation.service_type:
        qs = qs.filter(service_type=obligation.service_type)
    if obligation.region_id:
        qs = qs.filter(region_id=obligation.region_id)
    agg = qs.aggregate(avg=Avg("metric_value"), n=Count("id"))
    n, value = agg["n"], agg["avg"]
    ev = ObligationEvaluation(obligation=obligation, period_start=start, period_end=now, sample_count=n)
    if n < obligation.min_samples or value is None:
        ev.status = ObligationEvaluation.Status.INSUFFICIENT_DATA
        ev.save()
        return ev, None
    ok = value >= obligation.target_value if obligation.comparison == Obligation.Comparison.GTE else value <= obligation.target_value
    ev.measured_value = round(value, 4)
    ev.gap = round(value - obligation.target_value, 4)
    ev.gap_pct = round(ev.gap / obligation.target_value * 100, 2) if obligation.target_value else None
    ev.status = ObligationEvaluation.Status.COMPLIANT if ok else ObligationEvaluation.Status.NON_COMPLIANT
    ev.save()
    alert = None
    if not ok:
        open_alert = obligation.alerts.filter(status__in=[ComplianceAlert.Status.NEW, ComplianceAlert.Status.ACKNOWLEDGED]).first()
        if open_alert is None:
            sym = "≥" if obligation.comparison == "GTE" else "≤"
            alert = ComplianceAlert.objects.create(
                obligation=obligation, evaluation=ev, severity=_severity(ev.gap_pct),
                message=f"{obligation.operator.code} — {obligation.title} : valeur mesurée {ev.measured_value} {obligation.unit} (cible {sym} {obligation.target_value}), {n} mesures sur {obligation.evaluation_window_days} jours.",
            )
            notify(users_of(roles=("ARTEC_REGULATOR",)), "Alerte de conformité", alert.message[:300] + " (alerte algorithmique à examiner)", Notification.Type.OTHER, alert)
    audit_log(actor, "obligation.evaluated", "Obligation", obligation.pk, {"status": ev.status, "value": ev.measured_value, "samples": n})
    return ev, alert


def evaluate_all(actor=None):
    now = timezone.now()
    results = {"evaluated": 0, "alerts": 0, "skipped": 0}
    for ob in Obligation.objects.filter(is_active=True).select_related("operator"):
        try:
            _, alert = evaluate(ob, actor, now)
        except ValidationError:
            results["skipped"] += 1
            continue
        results["evaluated"] += 1
        results["alerts"] += 1 if alert else 0
    return results


@transaction.atomic
def handle_alert(alert, user, action, note="", request=None):
    if alert.status in (ComplianceAlert.Status.DISMISSED, ComplianceAlert.Status.ESCALATED):
        raise ValidationError("Cette alerte est déjà traitée.")
    note = (note or "").strip()
    if action == "dismiss" and len(note) < 10:
        raise ValidationError({"note": "Un motif (10 caractères minimum) est obligatoire pour classer une alerte sans suite."})
    alert.status = {"acknowledge": ComplianceAlert.Status.ACKNOWLEDGED, "dismiss": ComplianceAlert.Status.DISMISSED}[action]
    alert.handled_by, alert.handled_at, alert.handling_note = user, timezone.now(), note
    alert.save()
    audit_log(user, f"alert.{action}", "ComplianceAlert", alert.pk, {"note": note}, request=request)
    return alert


@transaction.atomic
def escalate_alert(alert, user, title="", description="", deadline=None, request=None):
    """Ouvre un dossier réglementaire À PARTIR d'une alerte, sur décision d'un régulateur. Aucune décision n'est prise ici."""
    from . import services

    if alert.status in (ComplianceAlert.Status.DISMISSED, ComplianceAlert.Status.ESCALATED):
        raise ValidationError("Cette alerte est déjà traitée.")
    ob, ev = alert.obligation, alert.evaluation
    case = services.open_case(
        {"operator": ob.operator, "case_type": RegulatoryCase.CaseType.OBLIGATION_FOLLOWUP, "title": title or f"Écart : {ob.title}",
         "description": description or alert.message, "deadline": deadline, "related_alert": alert},
        user, request,
    )
    services.add_evidence(
        case, user,
        {"kind": RegulatoryEvidence.Kind.MEASUREMENT, "visible_to_operator": True,
         "description": f"Évaluation du {ev.evaluated_at:%d/%m/%Y} : {ev.measured_value} {ob.unit} sur {ev.sample_count} mesures validées (méthode « {ob.measurement_method} »), cible {ob.target_value}."},
        request,
    )
    alert.status, alert.handled_by, alert.handled_at = ComplianceAlert.Status.ESCALATED, user, timezone.now()
    alert.save()
    audit_log(user, "alert.escalated", "ComplianceAlert", alert.pk, {"case": case.pk}, request=request)
    return case
