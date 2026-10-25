"""Publication des événements : écrit le journal puis pousse sur les WebSockets (si une couche de canaux est disponible).

Les publications d'une même transaction sont regroupées (un événement par thème et par public) et envoyées après le commit.
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from .models import RealtimeEvent

log = logging.getLogger(__name__)
PUBLIC = "public"


def org(org_id):
    return f"org:{org_id}"


def role(name):
    return f"role:{name}"


def user(user_id):
    return f"user:{user_id}"


def group_name(audience):
    """Les noms de groupes de canaux n'acceptent ni « : » ni espaces."""
    return "rt." + audience.replace(":", ".")


def audiences_for(u):
    """Publics auxquels appartient un utilisateur (ou le public anonyme)."""
    out = [PUBLIC]
    if u is not None and getattr(u, "is_authenticated", False):
        out += [user(u.pk), role(u.role)]
        if u.organization_id:
            out.append(org(u.organization_id))
    return out


class _Batch:
    """Événements d'une transaction. Si la transaction est annulée, le lot est abandonné avec elle."""

    def __init__(self):
        self.items = {}

    def add(self, topic, audiences, action, ref_type, ref_id):
        for a in audiences:
            previous = self.items.get((topic, a))
            # plusieurs enregistrements d'une même transaction : « created » l'emporte sur « updated »
            self.items[(topic, a)] = ("created" if previous and previous[0] == "created" else action, ref_type, ref_id)

    def flush(self):
        items, self.items = self.items, {}
        _send(items)


def _is_registered(conn, batch):
    return any(entry[1] == batch.flush for entry in conn.run_on_commit)


def publish(topic, audiences, ref=None, action="changed"):
    audiences = {a for a in audiences if a}
    if not audiences:
        return
    ref_type, ref_id = ("", "") if ref is None else (ref.__class__.__name__, str(getattr(ref, "pk", ref)))
    conn = transaction.get_connection()
    batch = getattr(conn, "_rt_batch", None)
    if batch is not None and conn.in_atomic_block and _is_registered(conn, batch):
        batch.add(topic, audiences, action, ref_type, ref_id)
        return
    batch = conn._rt_batch = _Batch()
    batch.add(topic, audiences, action, ref_type, ref_id)  # d'abord le contenu : en autocommit, le rappel s'exécute tout de suite
    transaction.on_commit(batch.flush)


def _send(pending):
    if not pending:
        return
    try:
        events = RealtimeEvent.objects.bulk_create(
            [RealtimeEvent(topic=t, audience=a, action=v[0], ref_type=v[1], ref_id=v[2]) for (t, a), v in pending.items()]
        )
    except Exception:  # noqa: BLE001 — le temps réel ne doit jamais faire échouer l'action métier
        log.exception("Journal temps réel indisponible")
        return
    layer = get_channel_layer()
    if layer is None:
        return
    for ev in events:
        try:
            async_to_sync(layer.group_send)(group_name(ev.audience), {"type": "realtime.event", "event": serialize(ev)})
        except Exception:  # noqa: BLE001 — le polling de secours rattrapera l'événement
            log.warning("Diffusion WebSocket impossible (couche de canaux indisponible)")
            break


def serialize(ev):
    return {"id": ev.pk, "topic": ev.topic, "action": ev.action, "audience": ev.audience, "ref_type": ev.ref_type, "ref_id": ev.ref_id}
