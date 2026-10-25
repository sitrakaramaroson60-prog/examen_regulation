from .models import Notification


def notify(recipients, title, message="", notification_type=Notification.Type.OTHER, resource=None):
    """Crée une notification par destinataire. Le message ne doit contenir aucune donnée confidentielle d'un autre organisme."""
    rtype, rid = ("", "")
    if resource is not None:
        rtype, rid = resource.__class__.__name__, str(resource.pk)
    objs = [
        Notification(
            recipient=r, title=title[:200], message=message, notification_type=notification_type,
            related_resource_type=rtype, related_resource_id=rid,
        )
        for r in recipients
        if r is not None
    ]
    created = Notification.objects.bulk_create(objs)
    from apps.realtime.bus import publish, user

    publish("notifications", [user(o.recipient_id) for o in objs], action="created")
    return created


def users_of(organization=None, roles=()):
    from apps.accounts.models import User

    qs = User.objects.filter(is_active=True)
    if organization is not None:
        qs = qs.filter(organization=organization)
    if roles:
        qs = qs.filter(role__in=roles)
    return list(qs)
