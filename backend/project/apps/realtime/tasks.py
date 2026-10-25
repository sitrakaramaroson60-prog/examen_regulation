from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import RealtimeEvent


@shared_task(name="realtime.purge_events")
def purge_events(hours=24):
    deleted, _ = RealtimeEvent.objects.filter(created_at__lt=timezone.now() - timedelta(hours=hours)).delete()
    return deleted
