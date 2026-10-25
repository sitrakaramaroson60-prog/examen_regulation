from django.utils import timezone

from apps.notifications.models import Notification
from apps.regulation.models import RegulatoryDecision
from apps.regulation.services import notify_deadlines

from .conftest import client_for  # noqa: F401


def open_case(api, regulator, op="YAS", **extra):
    r = api(regulator).post("/api/v1/regulation/cases/", {"operator": op, "case_type": "QOS_ANOMALY", "title": "Anomalie débit", "description": "Débit anormalement bas", **extra}, format="json")
    assert r.status_code == 201, r.data
    return r.data


def add_ev(api, regulator, cid, visible=True):
    r = api(regulator).post(f"/api/v1/regulation/cases/{cid}/evidence/", {"kind": "DOCUMENT", "description": "Rapport de mesures", "visible_to_operator": visible}, format="json")
    assert r.status_code == 201, r.data
    return r.data["id"]


def test_case_creation_reference_and_timeline(api, regulator):
    c = open_case(api, regulator)
    assert c["reference_number"].startswith("RC-") and c["status"] == "OPEN"
    tl = api(regulator).get(f"/api/v1/regulation/cases/{c['id']}/timeline/").data
    assert tl[0]["kind"] == "OPENED"


def test_full_workflow(api, regulator, yas):
    c = open_case(api, regulator)
    cid = c["id"]
    reg, op = api(regulator), api(yas)
    ev = add_ev(api, regulator, cid)
    assert reg.post(f"/api/v1/regulation/cases/{cid}/request-explanation/", {"message": "Expliquez la baisse de débit", "deadline": "2030-01-31"}, format="json").data["status"] == "AWAITING_OPERATOR_RESPONSE"
    assert Notification.objects.filter(recipient=yas, notification_type="EXPLANATION_REQUESTED").exists()
    assert reg.post(f"/api/v1/regulation/cases/{cid}/decide/", {"category": "WARNING", "justification": "Avertissement motivé par les mesures.", "evidence": [ev]}, format="json").status_code == 400
    assert op.post(f"/api/v1/regulation/cases/{cid}/respond/", {"content": "Maintenance planifiée sur la zone."}, format="json").status_code == 201
    assert Notification.objects.filter(recipient=regulator, notification_type="RESPONSE_RECEIVED").exists()
    assert op.post(f"/api/v1/regulation/cases/{cid}/respond/", {"content": "bis"}, format="json").status_code == 400  # plus de réponse attendue
    short = reg.post(f"/api/v1/regulation/cases/{cid}/decide/", {"category": "WARNING", "justification": "court", "evidence": [ev]}, format="json")
    assert short.status_code == 400
    no_ev = reg.post(f"/api/v1/regulation/cases/{cid}/decide/", {"category": "WARNING", "justification": "Justification suffisamment détaillée."}, format="json")
    assert no_ev.status_code == 400
    d = reg.post(f"/api/v1/regulation/cases/{cid}/decide/", {"category": "WARNING", "justification": "Justification suffisamment détaillée.", "evidence": [ev]}, format="json")
    assert d.status_code == 201 and d.data["is_current"] and d.data["decided_by"] == regulator.email
    assert op.get(f"/api/v1/regulation/cases/{cid}/").data["status"] == "DECIDED"
    ca = reg.post(f"/api/v1/regulation/cases/{cid}/corrective-actions/", {"description": "Rétablir le débit nominal", "due_date": "2035-01-01"}, format="json")
    assert ca.status_code == 201
    assert reg.post(f"/api/v1/regulation/cases/{cid}/close/", {}, format="json").status_code == 400  # action en cours
    assert op.post(f"/api/v1/regulation/corrective-actions/{ca.data['id']}/update-progress/", {"status": "SUBMITTED", "report": "Fait"}, format="json").status_code == 200
    assert reg.post(f"/api/v1/regulation/corrective-actions/{ca.data['id']}/verify/", {"compliant": True, "comment": "OK"}, format="json").data["status"] == "VERIFIED"
    assert reg.post(f"/api/v1/regulation/cases/{cid}/close/", {"comment": "Clos"}, format="json").data["status"] == "CLOSED"
    kinds = [e["kind"] for e in reg.get(f"/api/v1/regulation/cases/{cid}/timeline/").data]
    assert {"OPENED", "EXPLANATION_REQUESTED", "OPERATOR_RESPONSE", "DECISION", "CLOSED"} <= set(kinds)
    assert reg.post(f"/api/v1/regulation/cases/{cid}/decide/", {"category": "CLOSURE", "justification": "Tentative après clôture."}, format="json").status_code == 400


def test_operator_cannot_decide_or_open_cases(api, yas, regulator):
    assert api(yas).post("/api/v1/regulation/cases/", {"operator": "YAS", "case_type": "OTHER", "title": "t", "description": "d"}, format="json").status_code == 403
    cid = open_case(api, regulator)["id"]
    assert api(yas).post(f"/api/v1/regulation/cases/{cid}/decide/", {"category": "CONGRATULATIONS", "justification": "x" * 30}, format="json").status_code == 403
    assert api(yas).post(f"/api/v1/regulation/cases/{cid}/request-explanation/", {"message": "m"}, format="json").status_code == 403
    assert api(yas).post(f"/api/v1/regulation/cases/{cid}/evidence/", {"kind": "OTHER", "description": "d"}, format="json").status_code == 403


def test_internal_evidence_and_notes_hidden_from_operator(api, yas, regulator):
    cid = open_case(api, regulator)["id"]
    add_ev(api, regulator, cid, visible=False)
    api(regulator).post(f"/api/v1/regulation/cases/{cid}/note/", {"message": "Note confidentielle"}, format="json")
    assert api(yas).get(f"/api/v1/regulation/cases/{cid}/evidence/").data == []
    assert all(not e["internal"] and e["kind"] != "NOTE" for e in api(yas).get(f"/api/v1/regulation/cases/{cid}/timeline/").data)


def test_decision_immutable_and_amendment_traced(api, regulator):
    cid = open_case(api, regulator)["id"]
    reg = api(regulator)
    d = reg.post(f"/api/v1/regulation/cases/{cid}/decide/", {"category": "RECOMMENDATION", "justification": "Recommandation initiale détaillée."}, format="json").data
    assert reg.patch(f"/api/v1/regulation/decisions/{d['id']}/", {"justification": "x"}, format="json").status_code == 405
    assert reg.post(f"/api/v1/regulation/decisions/{d['id']}/amend/", {"category": "NO_BREACH", "justification": "Nouvelle analyse détaillée.", "reason": ""}, format="json").status_code == 400
    n = reg.post(f"/api/v1/regulation/decisions/{d['id']}/amend/", {"category": "NO_BREACH", "justification": "Nouvelle analyse détaillée.", "reason": "Élément nouveau reçu"}, format="json")
    assert n.status_code == 201 and n.data["supersedes"] == d["id"]
    old = RegulatoryDecision.objects.get(pk=d["id"])
    assert old.justification == "Recommandation initiale détaillée." and not old.is_current
    assert reg.post(f"/api/v1/regulation/decisions/{d['id']}/amend/", {"category": "WARNING", "justification": "x" * 30, "reason": "reason long"}, format="json").status_code == 400
    assert "DECISION_AMENDED" in [e["kind"] for e in reg.get(f"/api/v1/regulation/cases/{cid}/timeline/").data]
    from apps.audit.models import AuditLog

    assert AuditLog.objects.filter(action="case.decision_amended").exists()


def test_deadline_notifications_once_per_day(api, regulator):
    open_case(api, regulator, deadline=str(timezone.localdate()))
    assert notify_deadlines() == 1
    assert notify_deadlines() == 0


def test_overview_numbers(api, regulator, yas):
    open_case(api, regulator)
    assert api(regulator).get("/api/v1/regulation/overview/").data["cases_open"] == 1
    assert api(yas).get("/api/v1/regulation/overview/").status_code == 403
