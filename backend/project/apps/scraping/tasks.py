from celery import shared_task

from . import services


@shared_task(name="scraping.run_job", bind=True, max_retries=0)
def run_job_task(self, job_id):
    return services.run_job(job_id).pk


@shared_task(name="scraping.dispatch_due_jobs")
def dispatch_due_jobs():
    jobs = services.due_jobs()
    for job in jobs:
        run_job_task.delay(job.pk)
    return len(jobs)
