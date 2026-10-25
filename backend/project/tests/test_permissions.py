"""Isolation des opérateurs et séparation des deux comptes ARTEC."""
from apps.datasets.models import Dataset

from .conftest import qos_csv, csv_file


def mk_dataset(client, name="Mesures 4G", data_type="QOS_MEASUREMENT"):
    r = client.post("/api/v1/datasets/", {"name": name, "data_type": data_type}, format="json")
    assert r.status_code == 201, r.data
    return r.data["id"]


def upload(client, ds_id, text=None):
    return client.post(f"/api/v1/datasets/{ds_id}/versions/", {"file": csv_file(text or qos_csv())}, format="multipart")


def test_operator_cannot_see_competitor_dataset_even_with_exact_id(api, yas, airtel):
    ds = mk_dataset(api(yas))
    v = upload(api(yas), ds).data["id"]
    c = api(airtel)
    assert c.get(f"/api/v1/datasets/{ds}/").status_code == 404
    assert c.get(f"/api/v1/datasets/versions/{v}/").status_code == 404
    assert c.get(f"/api/v1/datasets/versions/{v}/download/").status_code == 404
    assert c.get(f"/api/v1/datasets/versions/{v}/preview/").status_code == 404
    assert c.post(f"/api/v1/datasets/versions/{v}/submit/").status_code == 404
    assert c.patch(f"/api/v1/datasets/{ds}/", {"name": "pirate"}, format="json").status_code == 404
    assert c.post(f"/api/v1/datasets/{ds}/versions/", {"file": csv_file(qos_csv())}, format="multipart").status_code == 404
    assert Dataset.objects.get(pk=ds).name == "Mesures 4G"
    assert c.get("/api/v1/datasets/").data["count"] == 0


def test_operator_cannot_modify_competitor_submission_or_case(api, yas, airtel, orange, regulator):
    ds = mk_dataset(api(yas))
    v = upload(api(yas), ds).data["id"]
    sub = api(yas).post(f"/api/v1/datasets/versions/{v}/submit/").data["id"]
    for other in (airtel, orange):
        c = api(other)
        assert c.get(f"/api/v1/submissions/{sub}/").status_code == 404
        assert c.post(f"/api/v1/submissions/{sub}/accept/").status_code in (403, 404)
    case = api(regulator).post("/api/v1/regulation/cases/", {"operator": "YAS", "case_type": "QOS_ANOMALY", "title": "t", "description": "d"}, format="json")
    assert case.status_code == 201
    cid = case.data["id"]
    assert api(orange).get(f"/api/v1/regulation/cases/{cid}/").status_code == 404
    assert api(airtel).get(f"/api/v1/regulation/cases/{cid}/timeline/").status_code == 404
    assert api(airtel).post(f"/api/v1/regulation/cases/{cid}/respond/", {"content": "x"}, format="json").status_code == 404
    assert api(orange).get("/api/v1/regulation/cases/").data["count"] == 0


def test_operator_cannot_manage_other_operator_publications_and_scraping(api, yas, airtel):
    p = api(yas).post("/api/v1/publications/", {"title": "Info YAS", "content": "contenu", "category": "INFORMATION"}, format="json")
    assert p.status_code == 201
    pid = p.data["id"]
    assert api(airtel).get(f"/api/v1/publications/{pid}/").status_code == 404
    assert api(airtel).post(f"/api/v1/publications/{pid}/publish/").status_code == 404
    assert api(airtel).get("/api/v1/publications/").data["count"] == 0


def test_publisher_cannot_run_predictions_or_decide(api, publisher):
    c = api(publisher)
    assert c.post("/api/v1/predictions/runs/", {"model_version": 1, "input_dataset_version": 1}, format="json").status_code == 403
    assert c.post("/api/v1/predictions/models/train/", {"name": "m", "training_dataset_version": 1}, format="json").status_code == 403
    assert c.post("/api/v1/regulation/cases/", {"operator": "YAS", "case_type": "OTHER", "title": "t", "description": "d"}, format="json").status_code == 403
    assert c.get("/api/v1/regulation/cases/").status_code == 403
    assert c.get("/api/v1/submissions/").status_code == 403
    assert c.get("/api/v1/datasets/").status_code == 403
    assert c.get("/api/v1/qos/measurements/").status_code == 403
    assert c.get("/api/v1/complaints/").status_code == 403


def test_regulator_publishes_only_regulatory_content(api, regulator, publisher):
    c = api(regulator)
    assert c.post("/api/v1/publications/", {"title": "x", "content": "y", "category": "INFORMATION"}, format="json").status_code == 400
    rep = c.post("/api/v1/publications/", {"title": "Rapport 2026", "content": "Synthèse", "category": "REPORT"}, format="json")
    assert rep.status_code == 201
    assert c.post(f"/api/v1/publications/{rep.data['id']}/publish/").status_code == 200
    # il ne voit ni ne gère les communications générales d'ARTEC Publications
    gen = api(publisher).post("/api/v1/publications/", {"title": "Communiqué", "content": "z", "category": "PRESS_RELEASE"}, format="json").data["id"]
    assert c.get(f"/api/v1/publications/{gen}/").status_code == 404
    assert c.post(f"/api/v1/publications/{gen}/publish/").status_code == 404


def test_regulator_creates_regulatory_surveys(api, regulator, anon):
    c = api(regulator)
    s = c.post("/api/v1/surveys/", {"title": "Sondage réglementaire", "questions": [{"text": "Q", "question_type": "SATISFACTION"}]}, format="json")
    assert s.status_code == 201
    assert c.post(f"/api/v1/surveys/{s.data['id']}/publish/").data["status"] == "PUBLISHED"  # ARTEC : pas de validation préalable
    assert anon.get("/api/v1/surveys/").data["count"] == 1


def test_regulator_can_validate_operator_surveys(api, regulator, yas):
    sid = api(yas).post("/api/v1/surveys/", {"title": "Sondage YAS", "questions": [{"text": "Q", "question_type": "YES_NO"}]}, format="json").data["id"]
    assert api(yas).post(f"/api/v1/surveys/{sid}/publish/").data["status"] == "PENDING_APPROVAL"
    assert api(regulator).post(f"/api/v1/surveys/{sid}/approve/").data["status"] == "PUBLISHED"


def test_barometer_publication_is_a_regulator_decision(api, regulator, publisher, yas, anon):
    assert anon.get("/api/v1/qos/public/").data["enabled"] is False
    for u in (publisher, yas):
        assert api(u).put("/api/v1/qos/public/settings/", {"enabled": True}, format="json").status_code == 403
    assert api(regulator).put("/api/v1/qos/public/settings/", {"enabled": True, "min_measurements": 3}, format="json").status_code == 400
    r = api(regulator).put("/api/v1/qos/public/settings/", {"enabled": True, "min_measurements": 10}, format="json")
    assert r.status_code == 200 and anon.get("/api/v1/qos/public/").data["enabled"] is True
    from apps.audit.models import AuditLog

    assert AuditLog.objects.filter(action="barometer.published").exists()


def test_regulator_manages_operator_accounts_only(api, regulator, yas, publisher, sysadmin):
    from .conftest import PASSWORD

    c = api(regulator)
    ok = c.post("/api/v1/auth/users/", {"email": "nouveau@orange.mg", "role": "OPERATOR_USER", "organization": "ORANGE", "password": PASSWORD}, format="json")
    assert ok.status_code == 201, ok.data
    for role, org in (("ARTEC_REGULATOR", "ARTEC"), ("SYSTEM_ADMIN", "ARTEC"), ("ARTEC_PUBLISHER", "ARTEC")):
        assert c.post("/api/v1/auth/users/", {"email": f"{role.lower()}@x.mg", "role": role, "organization": org, "password": PASSWORD}, format="json").status_code == 400
    emails = {u["email"] for u in c.get("/api/v1/auth/users/").data["results"]}
    assert yas.email in emails and publisher.email not in emails and sysadmin.email not in emails
    assert c.patch(f"/api/v1/auth/users/{publisher.pk}/", {"is_active": False}, format="json").status_code == 404
    assert c.patch(f"/api/v1/auth/users/{ok.data['id']}/", {"is_active": False}, format="json").status_code == 200
    assert c.patch(f"/api/v1/auth/users/{ok.data['id']}/", {"role": "ARTEC_REGULATOR", "organization": "ARTEC"}, format="json").status_code == 400
    assert api(sysadmin).get("/api/v1/auth/users/").data["count"] >= 4


def test_regulator_can_review_submissions(api, yas, regulator):
    ds = mk_dataset(api(yas))
    v = upload(api(yas), ds).data["id"]
    api(yas).post(f"/api/v1/datasets/versions/{v}/submit/")
    r = api(regulator).get("/api/v1/submissions/")
    assert r.status_code == 200 and r.data["count"] == 1
    assert api(regulator).get(f"/api/v1/datasets/versions/{v}/preview/").status_code == 200


def test_operator_cannot_review_own_submission(api, yas):
    ds = mk_dataset(api(yas))
    v = upload(api(yas), ds).data["id"]
    sub = api(yas).post(f"/api/v1/datasets/versions/{v}/submit/").data["id"]
    assert api(yas).post(f"/api/v1/submissions/{sub}/accept/").status_code == 403


def test_sysadmin_has_no_regulatory_competence(api, sysadmin):
    c = api(sysadmin)
    assert c.post("/api/v1/regulation/cases/", {"operator": "YAS", "case_type": "OTHER", "title": "t", "description": "d"}, format="json").status_code == 403
    assert c.get("/api/v1/submissions/").status_code == 403
    assert c.post("/api/v1/predictions/runs/", {}, format="json").status_code == 403


def test_audit_scoping(api, yas, airtel, regulator, sysadmin):
    from apps.audit.services import log

    log(yas, "x.test", "T", 1)
    log(airtel, "y.test", "T", 2)
    assert {r["action"] for r in api(yas).get("/api/v1/audit/?search=test").data["results"]} == {"x.test"}
    assert api(sysadmin).get("/api/v1/audit/?search=test").data["count"] == 2
    assert api(yas).post("/api/v1/audit/", {}, format="json").status_code == 405
