from celery import shared_task

from . import services


@shared_task(name="predictions.train_model")
def train_model_task(model_id):
    return services.train_model(model_id).pk


@shared_task(name="predictions.execute_run")
def execute_run_task(run_id):
    return services.execute_run(run_id).pk
