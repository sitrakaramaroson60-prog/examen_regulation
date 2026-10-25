import pytest

from apps.audit.models import AuditLog
from apps.audit.services import log
from apps.scraping import safe_http, services as scraping_services
from apps.scraping.models import ScrapedRecord, ScrapingJob, ScrapingSource


# ---------- réclamations ----------
def test_public_complaint_and_tracking(api, anon, regulator):
    r = anon.post("/api/v1/complaints/public/", {"category": "Coupures", "description": "Coupures répétées depuis une semaine", "target_operator": "YAS"}, format="json")
    assert r.status_code == 201 and r.data["tracking_token"]
    ref, tok = r.data["reference"], r.data["tracking_token"]
    ok = anon.post("/api/v1/complaints/public/track/", {"reference": ref, "token": tok}, format="json")
    assert ok.status_code == 200 and ok.data["status"] == "NEW"
    assert anon.post("/api/v1/complaints/public/track/", {"reference": ref, "token": "faux"}, format="json").status_code == 404
    assert api(regulator).get("/api/v1/complaints/").data["count"] == 1


def test_internal_messages_hidden_from_public_tracking(api, anon, regulator):
    r = anon.post("/api/v1/complaints/public/", {"category": "Débit", "description": "Débit très faible au quotidien"}, format="json").data
    cid = api(regulator).get("/api/v1/complaints/").data["results"][0]["id"]
    api(regulator).post(f"/api/v1/complaints/{cid}/messages/", {"content": "Note interne", "is_internal": True}, format="json")
    api(regulator).post(f"/api/v1/complaints/{cid}/messages/", {"content": "Nous traitons votre demande"}, format="json")
    t = anon.post("/api/v1/complaints/public/track/", {"reference": r["reference"], "token": r["tracking_token"]}, format="json").data
    assert [m["content"] for m in t["messages"]] == ["Nous traitons votre demande"]


def test_resolve_requires_conclusion(api, anon, regulator):
    anon.post("/api/v1/complaints/public/", {"category": "x", "description": "Description suffisamment longue"}, format="json")
    cid = api(regulator).get("/api/v1/complaints/").data["results"][0]["id"]
    assert api(regulator).post(f"/api/v1/complaints/{cid}/process/", {"status": "RESOLVED"}, format="json").status_code == 400
    assert api(regulator).post(f"/api/v1/complaints/{cid}/process/", {"status": "RESOLVED", "conclusion": "Traitée avec l'opérateur"}, format="json").status_code == 200


def test_public_complaint_honeypot(anon):
    assert anon.post("/api/v1/complaints/public/", {"category": "x", "description": "Description suffisamment longue", "website": "spam"}, format="json").status_code == 400


def test_contestation_visibility(api, yas, airtel, regulator, publisher):
    case = api(regulator).post("/api/v1/regulation/cases/", {"operator": "YAS", "case_type": "OTHER", "title": "t", "description": "d"}, format="json").data["id"]
    r = api(yas).post("/api/v1/complaints/", {"complaint_type": "OPERATOR_CONTESTATION", "category": "Contestation", "description": "Nous contestons", "related_case": case}, format="json")
    assert r.status_code == 201, r.data
    cid = r.data["id"]
    assert api(airtel).get(f"/api/v1/complaints/{cid}/").status_code == 404
    assert api(airtel).get("/api/v1/complaints/").data["count"] == 0
    assert api(publisher).get(f"/api/v1/complaints/{cid}/").status_code == 403
    assert api(regulator).get(f"/api/v1/complaints/{cid}/").status_code == 200
    # un opérateur ne peut pas contester le dossier d'un concurrent
    other = api(airtel).post("/api/v1/complaints/", {"complaint_type": "OPERATOR_CONTESTATION", "category": "c", "description": "d", "related_case": case}, format="json")
    assert other.status_code == 400
    # un opérateur ne traite pas les contestations
    assert api(yas).post(f"/api/v1/complaints/{cid}/process/", {"status": "RESOLVED", "conclusion": "x"}, format="json").status_code == 403


def test_public_complaints_not_visible_to_operators(api, anon, yas):
    anon.post("/api/v1/complaints/public/", {"category": "c", "description": "Description suffisamment longue", "target_operator": "YAS"}, format="json")
    assert api(yas).get("/api/v1/complaints/").data["count"] == 0


# ---------- scraping ----------
def test_private_ips_blocked():
    for ip in ("127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "172.16.0.1", "::1", "::ffff:127.0.0.1", "0.0.0.0"):
        assert not safe_http.is_public_ip(ip), ip
    assert safe_http.is_public_ip("93.184.216.34")


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.org/x", "http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/",
    "http://evil.com/", "http://example.org@evil.com/", "http://user:pw@example.org/", "http://example.org:8080/", "http://[::1]/",
    "http://localhost/",
])
def test_ssrf_urls_blocked(url):
    with pytest.raises(safe_http.ScrapingBlocked):
        safe_http.check_url(url)


def test_domain_resolving_to_private_ip_blocked(monkeypatch):
    import socket

    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.0.0.7", 80))])
    with pytest.raises(safe_http.ScrapingBlocked, match="privée"):
        safe_http.check_url("http://example.org/")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 80))])
    assert safe_http.check_url("http://sub.example.org/").hostname == "sub.example.org"


def test_scraping_disabled_when_not_configured(settings, api, yas):
    settings.SCRAPING_ALLOWED_DOMAINS = []
    assert api(yas).get("/api/v1/scraping/status/").data["configured"] is False
    src = api(yas).post("/api/v1/scraping/sources/", {"name": "S", "base_url": "http://example.org/"}, format="json").data["id"]
    r = api(yas).post("/api/v1/scraping/jobs/", {"name": "J", "source": src, "url": "http://example.org/p"}, format="json")
    assert r.status_code == 400 and "pas configuré" in str(r.data)


def test_scraping_job_run_isolated_and_validation(api, yas, airtel, monkeypatch, regulator):
    monkeypatch.setattr(safe_http, "check_url", lambda url: None)
    src = api(yas).post("/api/v1/scraping/sources/", {"name": "S", "base_url": "http://example.org/"}, format="json").data["id"]
    job = api(yas).post("/api/v1/scraping/jobs/", {"name": "J", "source": src, "url": "http://example.org/page"}, format="json")
    assert job.status_code == 201, job.data
    html = b"<html><head><title>Couverture</title></head><body><h1>Zones</h1><script>evil()</script><p>Texte</p></body></html>"
    monkeypatch.setattr(safe_http, "fetch", lambda url: (url, 200, "text/html", html))
    assert api(yas).post(f"/api/v1/scraping/jobs/{job.data['id']}/run/").status_code == 202
    rec = ScrapedRecord.objects.get()
    assert rec.validation_status == "PENDING" and rec.data["title"] == "Couverture" and "evil" not in rec.data["text_excerpt"]
    assert rec.source_url == "http://example.org/page"
    j = ScrapingJob.objects.get()
    assert j.items_collected == 1 and j.last_run_at
    # isolation
    assert api(airtel).get(f"/api/v1/scraping/jobs/{j.pk}/").status_code == 404
    assert api(airtel).get(f"/api/v1/scraping/records/{rec.pk}/").status_code == 404
    assert api(airtel).post(f"/api/v1/scraping/jobs/{j.pk}/run/").status_code == 404
    assert api(airtel).post(f"/api/v1/scraping/records/{rec.pk}/validate/").status_code == 404
    assert api(yas).post(f"/api/v1/scraping/records/{rec.pk}/validate/").data["validation_status"] == "VALIDATED"


def test_blocked_execution_records_failure_and_notifies(api, yas, monkeypatch):
    monkeypatch.setattr(safe_http, "check_url", lambda url: None)
    src = ScrapingSource.objects.create(organization=yas.organization, name="S", base_url="http://example.org/", created_by=yas)
    job = ScrapingJob.objects.create(organization=yas.organization, source=src, name="J", url="http://example.org/x", created_by=yas)

    def blocked(url):
        raise safe_http.ScrapingBlocked("Collecte interdite par robots.txt.")

    ex = scraping_services.run_job(job.pk, fetcher=blocked)
    job.refresh_from_db()
    assert ex.status == "BLOCKED" and job.error_count == 1 and "robots" in job.last_result
    assert yas.notifications.filter(notification_type="SCRAPING_FAILED").exists()


# ---------- audit / notifications ----------
def test_audit_immutable_and_secrets_masked(yas):
    entry = log(yas, "test.action", "X", 1, {"password": "secret123", "nested": {"access_token": "abc"}, "ok": "visible"})
    assert entry.metadata["password"] == "[masqué]" and entry.metadata["nested"]["access_token"] == "[masqué]" and entry.metadata["ok"] == "visible"
    entry.action = "hacked"
    with pytest.raises(PermissionError):
        entry.save()
    with pytest.raises(PermissionError):
        entry.delete()
    with pytest.raises(PermissionError):
        AuditLog.objects.all().delete()
    with pytest.raises(PermissionError):
        AuditLog.objects.all().update(action="x")


def test_login_actions_are_audited(anon, yas):
    anon.post("/api/v1/auth/login/", {"email": yas.email, "password": "bad"}, format="json")
    assert AuditLog.objects.filter(action="auth.login_failed").exists()
    assert not any("bad" in str(a.metadata) for a in AuditLog.objects.all())


def test_notifications_are_private(api, yas, airtel):
    from apps.notifications.services import notify

    notify([yas], "Pour YAS", "msg")
    assert api(yas).get("/api/v1/notifications/").data["count"] == 1
    assert api(airtel).get("/api/v1/notifications/").data["count"] == 0
    nid = yas.notifications.first().pk
    assert api(airtel).post(f"/api/v1/notifications/{nid}/read/").status_code == 404
    assert api(yas).post(f"/api/v1/notifications/{nid}/read/").data["is_read"] is True
    assert api(yas).get("/api/v1/notifications/unread-count/").data["count"] == 0


def test_error_format_is_uniform(anon):
    r = anon.get("/api/v1/auth/me/")
    assert set(r.data["error"]) == {"code", "message", "details"}


def test_throttling_login(settings, anon, yas, monkeypatch):
    from rest_framework.throttling import SimpleRateThrottle

    monkeypatch.setattr(SimpleRateThrottle, "THROTTLE_RATES", {"login": "3/min", "anon": "1000/min", "user": "1000/min"})
    from django.core.cache import cache

    cache.clear()
    codes = [anon.post("/api/v1/auth/login/", {"email": "nobody@t.mg", "password": "x"}, format="json").status_code for _ in range(5)]
    assert 429 in codes
    cache.clear()
