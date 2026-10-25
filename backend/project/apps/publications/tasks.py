from celery import shared_task

from .services import publish_due


@shared_task(name="publications.publish_due")
def publish_due_task():
    return publish_due()
