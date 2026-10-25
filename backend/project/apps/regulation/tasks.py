from celery import shared_task

from .services import notify_deadlines


@shared_task(name="regulation.notify_deadlines")
def notify_deadlines_task():
    return notify_deadlines()


@shared_task(name="regulation.evaluate_obligations")
def evaluate_obligations_task():
    from .compliance import evaluate_all

    return evaluate_all()
