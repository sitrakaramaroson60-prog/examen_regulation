from django.utils import timezone

from apps.publications.models import Comment, Publication
from apps.publications.services import publish_due


def mk(api, user, **extra):
    r = api(user).post("/api/v1/publications/", {"title": "Rapport trimestriel", "content": "Contenu", "category": "REPORT", **extra}, format="json")
    assert r.status_code == 201, r.data
    return r.data


def test_publish_flow_and_public_visibility(api, anon, publisher):
    p = mk(api, publisher)
    assert anon.get("/api/v1/publications/public/").data["count"] == 0
    assert api(publisher).post(f"/api/v1/publications/{p['id']}/publish/").data["status"] == "PUBLISHED"
    pub = anon.get("/api/v1/publications/public/").data
    assert pub["count"] == 1
    assert anon.get(f"/api/v1/publications/public/{p['slug']}/").status_code == 200


def test_internal_audience_not_public(api, anon, publisher):
    p = mk(api, publisher, audience="INTERNAL")
    api(publisher).post(f"/api/v1/publications/{p['id']}/publish/")
    assert anon.get("/api/v1/publications/public/").data["count"] == 0


def test_schedule_then_publish_due(api, anon, publisher):
    p = mk(api, publisher)
    when = (timezone.now() + timezone.timedelta(hours=1)).isoformat()
    assert api(publisher).post(f"/api/v1/publications/{p['id']}/schedule/", {"published_at": when}, format="json").status_code == 200
    assert anon.get("/api/v1/publications/public/").data["count"] == 0
    Publication.objects.filter(pk=p["id"]).update(published_at=timezone.now() - timezone.timedelta(minutes=1))
    assert publish_due() == 1
    assert anon.get("/api/v1/publications/public/").data["count"] == 1


def test_past_schedule_rejected(api, publisher):
    p = mk(api, publisher)
    when = (timezone.now() - timezone.timedelta(hours=1)).isoformat()
    assert api(publisher).post(f"/api/v1/publications/{p['id']}/schedule/", {"published_at": when}, format="json").status_code == 400


def test_archive_and_no_delete_when_published(api, publisher):
    p = mk(api, publisher)
    c = api(publisher)
    c.post(f"/api/v1/publications/{p['id']}/publish/")
    assert c.delete(f"/api/v1/publications/{p['id']}/").status_code == 400
    assert c.post(f"/api/v1/publications/{p['id']}/archive/").data["status"] == "ARCHIVED"


def test_search_filter_pagination(api, publisher):
    mk(api, publisher)
    mk(api, publisher, title="Autre sujet", category="PRESS_RELEASE")
    c = api(publisher)
    assert c.get("/api/v1/publications/?search=Autre").data["count"] == 1
    assert c.get("/api/v1/publications/?category=REPORT").data["count"] == 1


def test_comment_moderation_flow(api, anon, publisher):
    p = mk(api, publisher)
    api(publisher).post(f"/api/v1/publications/{p['id']}/publish/")
    r = anon.post("/api/v1/comments/", {"publication": p["id"], "content": "<script>alert(1)</script>Bonne initiative", "author_name": "<b>Jean</b>"}, format="json")
    assert r.status_code == 201 and r.data["status"] == "PENDING"
    c = Comment.objects.get()
    assert "<script>" not in c.content and "<b>" not in c.author_name
    assert anon.get(f"/api/v1/comments/?publication={p['id']}").data["count"] == 0
    assert api(publisher).post(f"/api/v1/comments/{c.pk}/approve/").status_code == 200
    assert anon.get(f"/api/v1/comments/?publication={p['id']}").data["count"] == 1
    assert anon.post(f"/api/v1/comments/{c.pk}/report/", {"reason": "spam"}, format="json").status_code == 202
    assert api(publisher).post(f"/api/v1/comments/{c.pk}/hide/").status_code == 200
    assert anon.get(f"/api/v1/comments/?publication={p['id']}").data["count"] == 0


def test_comment_on_unpublished_or_honeypot_rejected(api, anon, publisher):
    p = mk(api, publisher)
    assert anon.post("/api/v1/comments/", {"publication": p["id"], "content": "Salut tout le monde"}, format="json").status_code == 400
    api(publisher).post(f"/api/v1/publications/{p['id']}/publish/")
    assert anon.post("/api/v1/comments/", {"publication": p["id"], "content": "Salut tout le monde", "website": "x"}, format="json").status_code == 400
    assert anon.post("/api/v1/comments/", {"publication": p["id"], "content": "x" * 2001}, format="json").status_code == 400


def test_anonymous_cannot_moderate(api, anon, publisher):
    p = mk(api, publisher)
    api(publisher).post(f"/api/v1/publications/{p['id']}/publish/")
    anon.post("/api/v1/comments/", {"publication": p["id"], "content": "Un commentaire"}, format="json")
    c = Comment.objects.get()
    assert anon.post(f"/api/v1/comments/{c.pk}/approve/").status_code in (401, 403)


def test_operator_cannot_moderate_artec_comments(api, anon, publisher, yas):
    p = mk(api, publisher)
    api(publisher).post(f"/api/v1/publications/{p['id']}/publish/")
    anon.post("/api/v1/comments/", {"publication": p["id"], "content": "Un commentaire"}, format="json")
    c = Comment.objects.get()
    assert api(yas).post(f"/api/v1/comments/{c.pk}/approve/").status_code == 404


def test_publications_overview_is_scoped(api, publisher, yas):
    mk(api, publisher)
    api(yas).post("/api/v1/publications/", {"title": "Info YAS", "content": "x"}, format="json")
    assert api(publisher).get("/api/v1/publications/overview/").data["publications"] == {"DRAFT": 1}
    assert api(yas).get("/api/v1/publications/overview/").data["publications"] == {"DRAFT": 1}
