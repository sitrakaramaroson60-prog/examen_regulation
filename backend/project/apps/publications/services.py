from django.db import transaction
from django.utils import timezone

from apps.audit.services import log as audit_log

from .models import Publication


@transaction.atomic
def publish(publication, actor, request=None):
    publication.status = Publication.Status.PUBLISHED
    publication.published_at = timezone.now()
    publication.save(update_fields=["status", "published_at", "updated_at"])
    audit_log(actor, "publication.published", "Publication", publication.pk, {"organization": publication.organization.code, "audience": publication.audience}, request=request)
    return publication


@transaction.atomic
def schedule(publication, when, actor, request=None):
    publication.status = Publication.Status.SCHEDULED
    publication.published_at = when
    publication.save(update_fields=["status", "published_at", "updated_at"])
    audit_log(actor, "publication.scheduled", "Publication", publication.pk, {"at": when.isoformat()}, request=request)
    return publication


@transaction.atomic
def archive(publication, actor, request=None):
    publication.status = Publication.Status.ARCHIVED
    publication.save(update_fields=["status", "updated_at"])
    audit_log(actor, "publication.archived", "Publication", publication.pk, request=request)
    return publication


def publish_due():
    """Passe en PUBLISHED les publications planifiées dont l'échéance est atteinte."""
    return Publication.objects.filter(status=Publication.Status.SCHEDULED, published_at__lte=timezone.now()).update(status=Publication.Status.PUBLISHED)
