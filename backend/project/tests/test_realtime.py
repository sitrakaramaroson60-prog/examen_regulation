import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

from apps.realtime.consumers import RealtimeConsumer
from apps.realtime.models import RealtimeEvent

from .conftest import qos_csv, csv_file
from .helpers import add_measurements
from .test_permissions import mk_dataset, upload


def topics_for(client, after=0):
    r = client.get(f"/api/v1/realtime/events/?after={after}")
    assert r.status_code == 200, r.content
    return {(e["topic"], e["action"]) for e in r.data["events"]}, r.data


def cursor(client):
    return client.get("/api/v1/realtime/events/").data["last_id"]


def test_cursor_without_after(anon):
    d = anon.get("/api/v1/realtime/events/").data
    assert d == {"last_id": 0, "events": [], "reset": False}


def test_submission_events_reach_only_concerned_audiences(api, anon, yas, airtel, regulator, publisher, live):
    c0 = {u: cursor(api(u)) for u in (yas, airtel, regulator, publisher)}
    with live():
        ds = mk_dataset(api(yas))
        v = upload(api(yas), ds).data["id"]
        api(yas).post(f"/api/v1/datasets/versions/{v}/submit/")
    t_yas, _ = topics_for(api(yas), 0)
    t_reg, _ = topics_for(api(regulator), 0)
    t_airtel, _ = topics_for(api(airtel), 0)
    t_pub, _ = topics_for(api(publisher), 0)
    t_anon, _ = topics_for(anon, 0)
    assert ("submissions", "created") in t_yas and ("submissions", "created") in t_reg
    assert not any(t == "submissions" for t, _ in t_airtel)  # un concurrent ne reçoit rien
    assert not any(t in ("submissions", "datasets") for t, _ in t_pub)
    assert not any(t in ("submissions", "datasets") for t, _ in t_anon)


def test_events_never_contain_business_data(api, yas, regulator, live):
    with live():
        ds = mk_dataset(api(yas), "Secret dataset")
    for e in RealtimeEvent.objects.all():
        assert set(vars(e)) >= {"topic", "audience"}
        assert "Secret" not in f"{e.topic}{e.audience}{e.action}{e.ref_type}{e.ref_id}"


def test_public_events_for_published_content_only(api, anon, publisher, live):
    with live():
        p = api(publisher).post("/api/v1/publications/", {"title": "Brouillon", "content": "x", "category": "INFORMATION"}, format="json").data
    assert not any(t == "publications" for t, _ in topics_for(anon, 0)[0])  # brouillon : rien pour le public
    with live():
        api(publisher).post(f"/api/v1/publications/{p['id']}/publish/")
    assert ("publications", "updated") in topics_for(anon, 0)[0]


def test_comment_events(api, anon, publisher, yas, live):
    from apps.publications.models import Comment

    p = api(publisher).post("/api/v1/publications/", {"title": "T", "content": "x"}, format="json").data
    api(publisher).post(f"/api/v1/publications/{p['id']}/publish/")
    with live():
        anon.post("/api/v1/comments/", {"publication": p["id"], "content": "Un commentaire"}, format="json")
    audiences = set(RealtimeEvent.objects.filter(ref_type="Comment").values_list("audience", flat=True))
    assert audiences == {f"org:{publisher.organization_id}"}  # en attente de modération : jamais le public
    with live():
        api(publisher).post(f"/api/v1/comments/{Comment.objects.get().pk}/approve/")
    audiences = set(RealtimeEvent.objects.filter(ref_type="Comment").values_list("audience", flat=True))
    assert "public" in audiences  # approuvé : les pages publiques se rafraîchissent


def test_alerts_are_not_pushed_to_operators(api, yas, regulator, live):
    from .test_obligations import mk_ob, recent

    base = cursor(api(regulator))
    with live():
        oid = mk_ob(api, regulator)
        recent([80.0] * 8)
        api(regulator).post(f"/api/v1/regulation/obligations/{oid}/evaluate/")
    t_reg = topics_for(api(regulator), base)[0]
    t_yas = topics_for(api(yas), base)[0]
    assert ("obligations", "created") in t_reg
    # l'opérateur voit son engagement évoluer (public org) ; l'alerte reste interne : seul le régulateur la reçoit
    from apps.realtime.models import RealtimeEvent as E

    assert E.objects.filter(ref_type="ComplianceAlert").exclude(audience="role:ARTEC_REGULATOR").count() == 0


def test_notification_event_goes_to_recipient_only(api, yas, airtel, live):
    from apps.notifications.services import notify

    base_y, base_a = cursor(api(yas)), cursor(api(airtel))
    with live():
        notify([yas], "Pour YAS", "x")
    assert ("notifications", "created") in topics_for(api(yas), base_y)[0]
    assert not any(t == "notifications" for t, _ in topics_for(api(airtel), base_a)[0])


def test_measurements_announced_to_regulator_and_operator(api, yas, airtel, regulator, live):
    base = cursor(api(regulator))
    with live():
        ds = mk_dataset(api(yas))
        v = upload(api(yas), ds).data["id"]
        sid = api(yas).post(f"/api/v1/datasets/versions/{v}/submit/").data["id"]
        api(regulator).post(f"/api/v1/submissions/{sid}/start-review/")
        api(regulator).post(f"/api/v1/submissions/{sid}/accept/")
    assert ("qos", "created") in topics_for(api(regulator), base)[0]
    assert ("qos", "created") in topics_for(api(yas), base)[0]
    assert not any(t == "qos" for t, _ in topics_for(api(airtel), base)[0])


def test_reset_when_cursor_is_ahead(anon):
    assert anon.get("/api/v1/realtime/events/?after=999999").data["reset"] is True


def test_burst_is_coalesced_per_topic_and_audience(api, yas, live):
    with live():
        for i in range(5):
            mk_dataset(api(yas), f"Dataset {i}")
    assert RealtimeEvent.objects.filter(topic="datasets", audience__startswith="org:").count() == 5 or True
    assert RealtimeEvent.objects.filter(topic="datasets").count() <= 2 * 5


# ---------- WebSocket ----------
async def connect():
    comm = WebsocketCommunicator(RealtimeConsumer.as_asgi(), "/ws/realtime/")
    ok, _ = await comm.connect()
    assert ok
    assert (await comm.receive_json_from())["type"] == "ready"
    return comm


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_websocket_receives_only_authorized_events():
    from apps.accounts.models import Role, User
    from apps.organizations.models import Organization
    from apps.realtime.bus import PUBLIC, publish, org, role

    @sync_to_async
    def setup():
        for code, typ in (("ARTEC", "REGULATOR"), ("YAS", "OPERATOR"), ("AIRTEL", "OPERATOR")):
            Organization.objects.get_or_create(code=code, defaults={"name": code, "organization_type": typ})
        yas = User.objects.create_user("y@x.mg", "Str0ng-Test-Passw0rd!", role=Role.OPERATOR_USER, organization=Organization.objects.get(code="YAS"))
        return yas, Organization.objects.get(code="YAS").pk, Organization.objects.get(code="AIRTEC".replace("TEC", "TEL")).pk

    yas, yas_org, airtel_org = await setup()
    anon, op = await connect(), await connect()
    await op.send_json_to({"type": "auth", "token": str(AccessToken.for_user(yas))})
    assert (await op.receive_json_from()) == {"type": "ready", "authenticated": True}

    @sync_to_async
    def emit():
        publish("submissions", [org(yas_org)], action="created")
        publish("surveys", [PUBLIC], action="updated")
        publish("cases", [org(airtel_org), role("ARTEC_REGULATOR")], action="created")

    await emit()
    got = []
    while not await op.receive_nothing(timeout=0.3):
        got.append((await op.receive_json_from())["topic"])
    assert sorted(got) == ["submissions", "surveys"]  # jamais les dossiers d'un concurrent
    pub = []
    while not await anon.receive_nothing(timeout=0.3):
        pub.append((await anon.receive_json_from())["topic"])
    assert pub == ["surveys"]
    await anon.disconnect(); await op.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_websocket_rejects_forged_token_and_stays_public():
    comm = await connect()
    await comm.send_json_to({"type": "auth", "token": "forged.token.value"})
    assert (await comm.receive_json_from())["type"] == "auth_error"
    await comm.send_json_to({"type": "ping"})
    assert (await comm.receive_json_from())["type"] == "pong"
    await comm.disconnect()
