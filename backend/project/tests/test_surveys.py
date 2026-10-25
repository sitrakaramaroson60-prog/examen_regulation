import pytest
from django.utils import timezone

from apps.organizations.models import City, Region
from apps.surveys.models import Survey, SurveyResponse


def survey_payload(**extra):
    return {
        "title": "Qualité internet",
        "questions": [
            {"text": "Satisfaction", "question_type": "SATISFACTION", "is_required": True},
            {"text": "Service", "question_type": "SINGLE_CHOICE", "choices": [{"label": "4G"}, {"label": "3G"}]},
            {"text": "Commentaire", "question_type": "SHORT_TEXT"},
        ],
        **extra,
    }


def published_survey(api, publisher, **extra):
    c = api(publisher)
    s = c.post("/api/v1/surveys/", survey_payload(**extra), format="json")
    assert s.status_code == 201, s.data
    assert c.post(f"/api/v1/surveys/{s.data['id']}/publish/").status_code == 200
    return Survey.objects.get(pk=s.data["id"])


def loc(**extra):
    r = Region.objects.get(name="Analamanga")
    return {"region": r.pk, "city": City.objects.get(name="Antananarivo").pk, "location_context": "USAGE", **extra}


def token(anon, survey):
    return anon.get(f"/api/v1/surveys/{survey.pk}/participation-token/").data["participation_token"]


def answers(survey, sat=4):
    q = {x.question_type: x for x in survey.questions.all()}
    return [{"question": q["SATISFACTION"].id, "value": sat}, {"question": q["SINGLE_CHOICE"].id, "value": q["SINGLE_CHOICE"].choices.first().id}]


def test_publish_and_public_listing(api, anon, publisher):
    s = published_survey(api, publisher)
    assert anon.get("/api/v1/surveys/").data["count"] == 1
    assert anon.get(f"/api/v1/surveys/{s.pk}/").status_code == 200


def test_draft_not_public(api, anon, publisher):
    api(publisher).post("/api/v1/surveys/", survey_payload(), format="json")
    assert anon.get("/api/v1/surveys/").data["count"] == 0


def test_public_response_ok(api, anon, publisher):
    s = published_survey(api, publisher)
    r = anon.post(f"/api/v1/surveys/{s.pk}/responses/", {**loc(), "answers": answers(s), "participation_token": token(anon, s)}, format="json")
    assert r.status_code == 201, r.data
    resp = SurveyResponse.objects.get()
    assert len(resp.fingerprint) == 64 and "127.0.0.1" not in resp.fingerprint


def test_region_city_mismatch_rejected(api, anon, publisher):
    s = published_survey(api, publisher)
    bad = loc()
    bad["city"] = City.objects.get(name="Antsirabe").pk
    r = anon.post(f"/api/v1/surveys/{s.pk}/responses/", {**bad, "answers": answers(s), "participation_token": token(anon, s)}, format="json")
    assert r.status_code == 400


def test_required_question_enforced_and_invalid_values(api, anon, publisher):
    s = published_survey(api, publisher)
    t = token(anon, s)
    r = anon.post(f"/api/v1/surveys/{s.pk}/responses/", {**loc(), "answers": [], "participation_token": t}, format="json")
    assert r.status_code == 400
    r = anon.post(f"/api/v1/surveys/{s.pk}/responses/", {**loc(), "answers": answers(s, sat=99), "participation_token": t}, format="json")
    assert r.status_code == 400
    r = anon.post(f"/api/v1/surveys/{s.pk}/responses/", {**loc(), "answers": [{"question": 999999, "value": 1}], "participation_token": t}, format="json")
    assert r.status_code == 400
    assert SurveyResponse.objects.count() == 0


def test_missing_or_forged_token_rejected(api, anon, publisher):
    s = published_survey(api, publisher)
    for tok in (None, "forged"):
        body = {**loc(), "answers": answers(s)}
        if tok:
            body["participation_token"] = tok
        assert anon.post(f"/api/v1/surveys/{s.pk}/responses/", body, format="json").status_code == 400


def test_honeypot_blocks_bots(api, anon, publisher):
    s = published_survey(api, publisher)
    r = anon.post(f"/api/v1/surveys/{s.pk}/responses/", {**loc(), "answers": answers(s), "participation_token": token(anon, s), "website": "http://spam"}, format="json")
    assert r.status_code == 400


def test_duplicate_policy(api, anon, publisher):
    s = published_survey(api, publisher, duplicate_policy="ONE_PER_DAY")
    body = lambda: {**loc(), "answers": answers(s), "participation_token": token(anon, s)}  # noqa: E731
    assert anon.post(f"/api/v1/surveys/{s.pk}/responses/", body(), format="json").status_code == 201
    assert anon.post(f"/api/v1/surveys/{s.pk}/responses/", body(), format="json").status_code == 400


def test_closed_survey_refuses_responses(api, anon, publisher):
    s = published_survey(api, publisher, duplicate_policy="NONE")
    t = token(anon, s)
    assert api(publisher).post(f"/api/v1/surveys/{s.pk}/close/").status_code == 200
    r = anon.post(f"/api/v1/surveys/{s.pk}/responses/", {**loc(), "answers": answers(s), "participation_token": t}, format="json")
    assert r.status_code == 400


def test_ends_at_in_past_refuses(api, anon, publisher):
    s = published_survey(api, publisher)
    t = token(anon, s)
    Survey.objects.filter(pk=s.pk).update(ends_at=timezone.now() - timezone.timedelta(hours=1))
    r = anon.post(f"/api/v1/surveys/{s.pk}/responses/", {**loc(), "answers": answers(s), "participation_token": t}, format="json")
    assert r.status_code == 400


def test_operator_survey_needs_approval(api, anon, yas, publisher):
    c = api(yas)
    s = c.post("/api/v1/surveys/", survey_payload(), format="json").data["id"]
    assert c.post(f"/api/v1/surveys/{s}/publish/").data["status"] == "PENDING_APPROVAL"
    assert anon.get("/api/v1/surveys/").data["count"] == 0
    assert c.post(f"/api/v1/surveys/{s}/approve/").status_code == 403  # l'opérateur ne s'auto-valide pas
    assert api(publisher).post(f"/api/v1/surveys/{s}/approve/").data["status"] == "PUBLISHED"
    assert anon.get("/api/v1/surveys/").data["count"] == 1


def test_operator_cannot_edit_competitor_or_publisher_surveys(api, yas, airtel):
    s = api(yas).post("/api/v1/surveys/", survey_payload(), format="json").data["id"]
    assert api(airtel).patch(f"/api/v1/surveys/{s}/", {"title": "x"}, format="json").status_code == 404
    assert api(airtel).post(f"/api/v1/surveys/{s}/publish/").status_code == 404
    assert api(airtel).get(f"/api/v1/surveys/{s}/results/").status_code == 404


def test_results_access_and_public_aggregation(api, anon, publisher, yas):
    s = published_survey(api, publisher, results_public=True)
    for i in range(3):
        anon2 = type(anon)()
        anon2.defaults = {"REMOTE_ADDR": f"10.0.0.{i + 1}"}
        r = anon2.post(f"/api/v1/surveys/{s.pk}/responses/", {**loc(), "answers": answers(s, sat=i + 2), "participation_token": token(anon2, s)}, format="json")
        assert r.status_code == 201, r.data
    pub = anon.get(f"/api/v1/surveys/{s.pk}/results/")
    assert pub.status_code == 200 and pub.data["total_responses"] == 3
    assert all("texts" not in q for q in pub.data["questions"])
    assert api(publisher).get(f"/api/v1/surveys/{s.pk}/results/").data["total_responses"] == 3


def test_private_results_hidden(api, anon, publisher, yas):
    s = published_survey(api, publisher, results_public=False)
    assert anon.get(f"/api/v1/surveys/{s.pk}/results/").status_code == 404
    assert api(yas).get(f"/api/v1/surveys/{s.pk}/results/").status_code == 404


def test_small_sample_suppressed_publicly(api, anon, publisher):
    s = published_survey(api, publisher, results_public=True)
    anon.post(f"/api/v1/surveys/{s.pk}/responses/", {**loc(), "answers": answers(s), "participation_token": token(anon, s)}, format="json")
    data = anon.get(f"/api/v1/surveys/{s.pk}/results/").data
    assert data.get("suppressed") is True and data["questions"] == []


def test_survey_answers_feed_qos_perception(api, anon, publisher):
    from apps.qos.models import QoSMeasurement

    c = api(publisher)
    payload = {
        "title": "Satisfaction YAS", "target_operator": "YAS",
        "questions": [{"text": "Satisfaction globale", "question_type": "SATISFACTION", "is_required": True, "qos_metric": "satisfaction"}],
    }
    sid = c.post("/api/v1/surveys/", payload, format="json")
    assert sid.status_code == 201, sid.data
    c.post(f"/api/v1/surveys/{sid.data['id']}/publish/")
    s = Survey.objects.get(pk=sid.data["id"])
    q = s.questions.get()
    r = anon.post(f"/api/v1/surveys/{s.pk}/responses/", {**loc(), "answers": [{"question": q.id, "value": 4}], "participation_token": token(anon, s)}, format="json")
    assert r.status_code == 201, r.data
    m = QoSMeasurement.objects.get()
    assert (m.operator.code, m.metric_name, m.metric_value, m.source_type) == ("YAS", "satisfaction", 4.0, "SURVEY")


def test_qos_metric_validation_on_questions(api, publisher):
    bad = {"title": "t", "questions": [{"text": "q", "question_type": "SHORT_TEXT", "qos_metric": "latency"}]}
    assert api(publisher).post("/api/v1/surveys/", bad, format="json").status_code == 400
    bad2 = {"title": "t", "questions": [{"text": "q", "question_type": "SATISFACTION", "qos_metric": "latency"}]}
    assert api(publisher).post("/api/v1/surveys/", bad2, format="json").status_code == 400
