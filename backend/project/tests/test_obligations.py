from datetime import date, timedelta

from django.utils import timezone

from apps.regulation.models import ComplianceAlert, RegulatoryCase, RegulatoryDecision

from .helpers import add_measurements

NOW = timezone.now()


def ob_payload(**extra):
    return {
        "operator": "YAS", "title": "Disponibilité minimale du réseau", "legal_basis": "Cahier des charges (exemple de test)", "metric_name": "availability",
        "unit": "%", "comparison": "GTE", "target_value": 99.0, "measurement_method": "supervision", "min_samples": 5, "evaluation_window_days": 30,
        "valid_from": "2026-01-01", **extra,
    }


def mk_ob(api, regulator, **extra):
    r = api(regulator).post("/api/v1/regulation/obligations/", ob_payload(**extra), format="json")
    assert r.status_code == 201, r.data
    return r.data["id"]


def recent(values, **kw):
    return add_measurements(kw.pop("operator", "YAS"), "availability", values, unit="%", method=kw.pop("method", "supervision"), start=NOW - timedelta(days=len(values) + 1), **kw)


def test_only_regulator_manages_obligations(api, regulator, yas, publisher):
    assert api(yas).post("/api/v1/regulation/obligations/", ob_payload(), format="json").status_code == 403
    assert api(publisher).get("/api/v1/regulation/obligations/").status_code == 403
    assert api(regulator).post("/api/v1/regulation/obligations/", ob_payload(legal_basis=""), format="json").status_code == 400
    assert api(regulator).post("/api/v1/regulation/obligations/", ob_payload(measurement_method=""), format="json").status_code == 400
    assert api(regulator).post("/api/v1/regulation/obligations/", ob_payload(unit="ms"), format="json").status_code == 400
    mk_ob(api, regulator)


def test_operator_sees_only_its_obligations(api, regulator, yas, airtel):
    oid = mk_ob(api, regulator)
    assert api(yas).get("/api/v1/regulation/obligations/").data["count"] == 1
    assert api(airtel).get("/api/v1/regulation/obligations/").data["count"] == 0
    assert api(airtel).get(f"/api/v1/regulation/obligations/{oid}/").status_code == 404
    assert api(yas).post(f"/api/v1/regulation/obligations/{oid}/evaluate/").status_code == 403
    assert api(yas).patch(f"/api/v1/regulation/obligations/{oid}/", {"target_value": 50}, format="json").status_code == 403


def test_evaluation_statuses(api, regulator):
    oid = mk_ob(api, regulator)
    c = api(regulator)
    assert c.post(f"/api/v1/regulation/obligations/{oid}/evaluate/").data["evaluation"]["status"] == "INSUFFICIENT_DATA"
    recent([99.9] * 6)
    r = c.post(f"/api/v1/regulation/obligations/{oid}/evaluate/").data
    assert r["evaluation"]["status"] == "COMPLIANT" and r["alert"] is None


def test_gap_creates_single_algorithmic_alert(api, regulator):
    oid = mk_ob(api, regulator)
    recent([92.0] * 8)
    c = api(regulator)
    r = c.post(f"/api/v1/regulation/obligations/{oid}/evaluate/").data
    assert r["evaluation"]["status"] == "NON_COMPLIANT" and round(r["evaluation"]["gap"], 1) == -7.0
    assert r["alert"]["severity"] == "WARNING" and r["alert"]["nature"].startswith("ALERTE_ALGORITHMIQUE")
    again = c.post(f"/api/v1/regulation/obligations/{oid}/evaluate/").data
    assert again["alert"] is None and ComplianceAlert.objects.count() == 1  # pas de doublon tant que l'alerte est ouverte


def test_declared_data_and_other_methods_are_ignored(api, regulator):
    oid = mk_ob(api, regulator)
    recent([100.0] * 8, source="DECLARED")            # déclarations parfaites : ne comptent pas
    recent([90.0] * 8, method="autre-methode")        # méthode différente : ne compte pas
    assert api(regulator).post(f"/api/v1/regulation/obligations/{oid}/evaluate/").data["evaluation"]["status"] == "INSUFFICIENT_DATA"
    recent([90.0] * 8)
    assert api(regulator).post(f"/api/v1/regulation/obligations/{oid}/evaluate/").data["evaluation"]["status"] == "NON_COMPLIANT"


def test_alert_never_creates_decision_or_case(api, regulator):
    oid = mk_ob(api, regulator)
    recent([70.0] * 8)
    api(regulator).post(f"/api/v1/regulation/obligations/{oid}/evaluate/")
    assert ComplianceAlert.objects.filter(severity="CRITICAL").count() == 1
    assert RegulatoryDecision.objects.count() == 0 and RegulatoryCase.objects.count() == 0


def test_alerts_are_internal_to_regulation(api, regulator, yas, publisher):
    oid = mk_ob(api, regulator)
    recent([90.0] * 8)
    api(regulator).post(f"/api/v1/regulation/obligations/{oid}/evaluate/")
    assert api(regulator).get("/api/v1/regulation/alerts/").data["count"] == 1
    assert api(yas).get("/api/v1/regulation/alerts/").status_code == 403
    assert api(publisher).get("/api/v1/regulation/alerts/").status_code == 403
    assert "alerts" not in api(yas).get("/api/v1/regulation/operator-files/me/").data
    assert "alerts" in api(regulator).get("/api/v1/regulation/operator-files/YAS/").data


def test_dismiss_needs_reason_and_escalate_opens_case(api, regulator, yas):
    oid = mk_ob(api, regulator)
    recent([90.0] * 8)
    api(regulator).post(f"/api/v1/regulation/obligations/{oid}/evaluate/")
    aid = api(regulator).get("/api/v1/regulation/alerts/").data["results"][0]["id"]
    assert api(regulator).post(f"/api/v1/regulation/alerts/{aid}/dismiss/", {"note": "non"}, format="json").status_code == 400
    case = api(regulator).post(f"/api/v1/regulation/alerts/{aid}/escalate/", {}, format="json")
    assert case.status_code == 201 and case.data["case_type"] == "OBLIGATION_FOLLOWUP"
    assert RegulatoryCase.objects.get().related_alert_id == aid and RegulatoryDecision.objects.count() == 0
    assert api(regulator).get(f"/api/v1/regulation/alerts/{aid}/").data["status"] == "ESCALATED"
    assert api(regulator).post(f"/api/v1/regulation/alerts/{aid}/escalate/", {}, format="json").status_code == 400
    # l'opérateur voit le dossier et la preuve chiffrée, mais jamais l'alerte
    cid = case.data["id"]
    assert api(yas).get(f"/api/v1/regulation/cases/{cid}/").status_code == 200
    assert len(api(yas).get(f"/api/v1/regulation/cases/{cid}/evidence/").data) == 1


def test_operator_file_isolation_and_content(api, regulator, yas, airtel):
    oid = mk_ob(api, regulator)
    recent([95.0] * 8)
    api(regulator).post(f"/api/v1/regulation/obligations/{oid}/evaluate/")
    f = api(yas).get("/api/v1/regulation/operator-files/me/").data
    assert f["operator"]["code"] == "YAS" and f["summary"]["obligations_with_gap"] == 1 and f["obligations"][0]["latest_evaluation"]["status"] == "NON_COMPLIANT"
    assert any(q["metric"] == "availability" for q in f["quality_last_30_days"])
    assert api(yas).get("/api/v1/regulation/operator-files/AIRTEL/").status_code == 404
    assert api(airtel).get("/api/v1/regulation/operator-files/YAS/").status_code == 404
    assert api(regulator).get("/api/v1/regulation/operator-files/me/").status_code == 404
    idx = api(regulator).get("/api/v1/regulation/operator-files/").data
    assert {r["operator"]["code"] for r in idx} == {"YAS", "AIRTEL", "ORANGE"}
    assert api(yas).get("/api/v1/regulation/operator-files/").status_code == 403


def test_evaluate_all(api, regulator):
    mk_ob(api, regulator)
    mk_ob(api, regulator, operator="AIRTEL", title="Disponibilité AIRTEL")
    recent([80.0] * 8)
    r = api(regulator).post("/api/v1/regulation/obligations/evaluate-all/").data
    assert r["evaluated"] == 2 and r["alerts"] == 1


def test_complete_regulatory_cycle(api, regulator, yas):
    reg, op = api(regulator), api(yas)
    oid = mk_ob(api, regulator)
    recent([92.0] * 8)
    reg.post(f"/api/v1/regulation/obligations/{oid}/evaluate/")
    aid = reg.get("/api/v1/regulation/alerts/").data["results"][0]["id"]
    cid = reg.post(f"/api/v1/regulation/alerts/{aid}/escalate/", {"deadline": str(date.today() + timedelta(days=30))}, format="json").data["id"]
    ev = reg.get(f"/api/v1/regulation/cases/{cid}/evidence/").data[0]["id"]
    assert reg.post(f"/api/v1/regulation/cases/{cid}/request-explanation/", {"message": "Expliquez l'écart de disponibilité."}, format="json").status_code == 200
    assert op.post(f"/api/v1/regulation/cases/{cid}/respond/", {"content": "Incident électrique sur deux sites."}, format="json").status_code == 201
    d = reg.post(f"/api/v1/regulation/cases/{cid}/decide/", {"category": "CORRECTION_REQUEST", "justification": "Plan correctif exigé suite à l'écart constaté.", "evidence": [ev]}, format="json")
    assert d.status_code == 201
    ca = reg.post(f"/api/v1/regulation/cases/{cid}/corrective-actions/", {"description": "Doubler l'alimentation de secours", "due_date": str(date.today() + timedelta(days=60))}, format="json").data
    chk = reg.post(f"/api/v1/regulation/corrective-actions/{ca['id']}/schedule-check/", {"due_date": str(date.today() + timedelta(days=90))}, format="json")
    assert chk.status_code == 201
    assert op.get("/api/v1/regulation/checks/").data["count"] == 1
    assert op.post(f"/api/v1/regulation/checks/{chk.data['id']}/complete/", {"outcome": "COMPLIANT", "notes": "ok ok ok"}, format="json").status_code == 403
    op.post(f"/api/v1/regulation/corrective-actions/{ca['id']}/update-progress/", {"status": "SUBMITTED", "report": "Installé"}, format="json")
    assert reg.post(f"/api/v1/regulation/checks/{chk.data['id']}/complete/", {"outcome": "COMPLIANT", "notes": "Contrôle sur site conforme."}, format="json").data["status"] == "DONE"
    reg.post(f"/api/v1/regulation/corrective-actions/{ca['id']}/verify/", {"compliant": True, "comment": "OK"}, format="json")
    assert reg.post(f"/api/v1/regulation/cases/{cid}/close/", {}, format="json").data["status"] == "CLOSED"
    assert op.get("/api/v1/regulation/operator-files/me/").data["summary"]["pending_corrective_actions"] == 0


def test_official_congratulations_on_a_recognition_case(api, regulator, yas):
    c = api(regulator).post("/api/v1/regulation/cases/", {"operator": "YAS", "case_type": "RECOGNITION", "title": "Excellente disponibilité 2026", "description": "Cible dépassée sur toute la période."}, format="json")
    assert c.status_code == 201
    d = api(regulator).post(f"/api/v1/regulation/cases/{c.data['id']}/decide/", {"category": "CONGRATULATIONS", "justification": "Objectifs de disponibilité dépassés sur douze mois."}, format="json")
    assert d.status_code == 201
    f = api(yas).get("/api/v1/regulation/operator-files/me/").data
    assert f["summary"]["congratulations"] == 1 and f["decisions"][0]["category"] == "CONGRATULATIONS"
