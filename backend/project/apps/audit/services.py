SENSITIVE = ("password", "token", "secret", "authorization", "refresh", "access", "key")


def _clean(value):
    if isinstance(value, dict):
        return {k: ("[masqué]" if any(s in str(k).lower() for s in SENSITIVE) else _clean(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def log(actor, action, resource_type="", resource_id="", metadata=None, request=None):
    """Enregistre une action sensible. Les secrets sont masqués ; l'adresse IP n'est pas conservée."""
    from .models import AuditLog

    authenticated = actor is not None and getattr(actor, "is_authenticated", False)
    return AuditLog.objects.create(
        actor=actor if authenticated else None,
        actor_email=actor.email if authenticated else "",
        actor_organization=getattr(actor, "organization", None) if authenticated else None,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        metadata=_clean(metadata or {}),
    )
