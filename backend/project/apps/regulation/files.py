"""Dossier de suivi d'un opérateur : engagements, résultats mesurés, écarts, actions correctives, décisions."""
from datetime import timedelta

from django.utils import timezone

from apps.qos.dashboard import build_dashboard
from apps.qos.models import QoSMeasurement

from .models import ComplianceAlert, CorrectiveAction, FollowUpCheck, Obligation, ObligationEvaluation, RegulatoryCase, RegulatoryDecision

OPEN_CASE = ["OPEN", "UNDER_REVIEW", "AWAITING_OPERATOR_RESPONSE", "UNDER_CORRECTION", "DECIDED"]


def _eval(ev):
    return None if ev is None else {
        "status": ev.status, "measured_value": ev.measured_value, "gap": ev.gap, "gap_pct": ev.gap_pct, "samples": ev.sample_count, "evaluated_at": ev.evaluated_at,
    }


def operator_file(org, as_regulator):
    obligations = []
    for ob in Obligation.objects.filter(operator=org).select_related("region"):
        last = ob.evaluations.first()
        obligations.append({
            "id": ob.id, "title": ob.title, "metric_name": ob.metric_name, "unit": ob.unit, "comparison": ob.comparison, "target_value": ob.target_value,
            "measurement_method": ob.measurement_method, "technology": ob.technology, "region": ob.region.name if ob.region else None,
            "legal_basis": ob.legal_basis, "is_active": ob.is_active, "latest_evaluation": _eval(last),
        })
    evaluated = [o for o in obligations if o["latest_evaluation"] and o["latest_evaluation"]["status"] != ObligationEvaluation.Status.INSUFFICIENT_DATA]
    compliant = sum(1 for o in evaluated if o["latest_evaluation"]["status"] == "COMPLIANT")
    cases = RegulatoryCase.objects.filter(operator=org)
    decisions = [d for d in RegulatoryDecision.objects.filter(case__operator=org).select_related("case") if d.is_current]
    actions = CorrectiveAction.objects.filter(case__operator=org).exclude(status__in=["VERIFIED", "NOT_COMPLIED"]).select_related("case")
    checks = FollowUpCheck.objects.filter(corrective_action__case__operator=org, status="PLANNED").select_related("corrective_action")
    snapshot = build_dashboard(QoSMeasurement.objects.filter(operator=org, validation_status="VALIDATED"), {"date_from": timezone.now() - timedelta(days=30), "only_operator": org.code})
    quality = [{"metric": i["metric"], "label": i["label"], "average": i["groups"][0]["operators"][0]["average"], "unit": i["groups"][0]["unit"], "status": i["groups"][0]["operators"][0]["status"]}
               for i in snapshot["indicators"] if i["groups"] and i["groups"][0]["operators"][0]["count"]]
    out = {
        "operator": {"code": org.code, "name": org.name},
        "summary": {
            "obligations_total": len(obligations), "obligations_evaluated": len(evaluated), "obligations_compliant": compliant,
            "obligations_with_gap": len(evaluated) - compliant,
            "open_cases": cases.filter(status__in=OPEN_CASE).exclude(status="DECIDED").count(),
            "awaiting_response": cases.filter(status="AWAITING_OPERATOR_RESPONSE").count(),
            "warnings": sum(1 for d in decisions if d.category == "WARNING"),
            "congratulations": sum(1 for d in decisions if d.category == "CONGRATULATIONS"),
            "pending_corrective_actions": actions.count(),
        },
        "obligations": obligations,
        "quality_last_30_days": quality,
        "cases": [{"id": c.id, "reference_number": c.reference_number, "title": c.title, "status": c.status, "deadline": c.deadline} for c in cases.order_by("-opened_at")[:10]],
        "decisions": [{"id": d.id, "case": d.case.reference_number, "category": d.category, "decided_at": d.decided_at} for d in sorted(decisions, key=lambda x: x.decided_at, reverse=True)[:20]],
        "corrective_actions": [{"id": a.id, "case": a.case.reference_number, "description": a.description, "due_date": a.due_date, "status": a.status} for a in actions],
        "planned_checks": [{"id": c.id, "due_date": c.due_date, "action": c.corrective_action.description[:120]} for c in checks],
    }
    if as_regulator:  # les alertes algorithmiques restent internes tant qu'aucun dossier n'est ouvert
        out["alerts"] = [{"id": a.id, "severity": a.severity, "status": a.status, "message": a.message, "created_at": a.created_at}
                         for a in ComplianceAlert.objects.filter(obligation__operator=org).exclude(status="DISMISSED")[:20]]
        out["summary"]["open_alerts"] = ComplianceAlert.objects.filter(obligation__operator=org, status__in=["NEW", "ACKNOWLEDGED"]).count()
    return out
