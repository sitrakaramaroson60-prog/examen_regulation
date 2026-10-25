import hashlib
import json
from datetime import timedelta
from html.parser import HTMLParser

from django.db import transaction
from django.utils import timezone

from apps.audit.services import log as audit_log
from apps.notifications.models import Notification
from apps.notifications.services import notify, users_of

from . import safe_http
from .models import ScrapedRecord, ScrapingExecution, ScrapingJob

FREQ = {"HOURLY": timedelta(hours=1), "DAILY": timedelta(days=1), "WEEKLY": timedelta(weeks=1)}


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.headings, self.text, self._tag, self.description = "", [], [], None, ""

    def handle_starttag(self, tag, attrs):
        self._tag = tag
        if tag == "meta" and dict(attrs).get("name", "").lower() == "description":
            self.description = dict(attrs).get("content", "")[:500]

    def handle_endtag(self, tag):
        self._tag = None

    def handle_data(self, data):
        d = data.strip()
        if not d or self._tag in ("script", "style"):
            return
        if self._tag == "title":
            self.title += d
        elif self._tag in ("h1", "h2", "h3") and len(self.headings) < 30:
            self.headings.append(d[:200])
        elif len(" ".join(self.text)) < 3000:
            self.text.append(d)


def extract(content_type, data):
    text = data.decode("utf-8", "replace")
    if content_type == "text/html":
        p = _Extractor()
        p.feed(text)
        return {"title": p.title[:250], "description": p.description, "headings": p.headings, "text_excerpt": " ".join(p.text)[:2000]}
    if content_type == "application/json":
        try:
            return {"json": json.loads(text)}
        except ValueError:
            return {"text_excerpt": text[:2000], "warning": "JSON invalide"}
    return {"text_excerpt": "\n".join(text.splitlines()[:100])[:5000]}


def run_job(job_id, fetcher=None):
    job = ScrapingJob.objects.select_related("organization").get(pk=job_id)
    fetcher = fetcher or safe_http.fetch
    execution = ScrapingExecution.objects.create(job=job)
    job.status = ScrapingJob.Status.RUNNING
    job.save(update_fields=["status"])
    log = [{"at": timezone.now().isoformat(), "event": "start", "url": job.url}]
    try:
        final_url, code, ctype, data = fetcher(job.url)
        record = ScrapedRecord.objects.create(
            job=job, execution=execution, organization=job.organization, source_url=job.url, final_url=final_url, http_status=code,
            content_type=ctype, content_hash=hashlib.sha256(data).hexdigest(), data=extract(ctype, data),
        )
        execution.status, execution.items_collected = ScrapingExecution.Status.SUCCESS, 1
        job.items_collected += 1
        job.last_result = f"Succès : 1 élément (HTTP {code})"
        log.append({"at": timezone.now().isoformat(), "event": "stored", "record": record.pk, "http_status": code})
    except safe_http.ScrapingBlocked as exc:
        execution.status, execution.errors = ScrapingExecution.Status.BLOCKED, 1
        job.error_count += 1
        job.last_result = f"Bloquée : {exc}"
        log.append({"at": timezone.now().isoformat(), "event": "blocked", "reason": str(exc)})
    except Exception as exc:  # noqa: BLE001
        execution.status, execution.errors = ScrapingExecution.Status.FAILED, 1
        job.error_count += 1
        job.last_result = f"Échec : {type(exc).__name__}"
        log.append({"at": timezone.now().isoformat(), "event": "error", "type": type(exc).__name__})
    execution.finished_at = timezone.now()
    execution.log = log
    execution.save()
    job.last_run_at = execution.finished_at
    job.status = ScrapingJob.Status.PAUSED if job.status == ScrapingJob.Status.PAUSED else ScrapingJob.Status.ACTIVE
    job.status = ScrapingJob.Status.ACTIVE
    job.save()
    if execution.status != ScrapingExecution.Status.SUCCESS:
        notify(users_of(job.organization), "Échec d'une tâche de scraping", f"La tâche « {job.name} » a échoué.", Notification.Type.SCRAPING_FAILED, job)
    audit_log(None, "scraping.executed", "ScrapingJob", job.pk, {"status": execution.status, "organization": job.organization.code})
    return execution


def due_jobs(now=None):
    now = now or timezone.now()
    due = []
    for job in ScrapingJob.objects.filter(status=ScrapingJob.Status.ACTIVE).exclude(frequency="MANUAL"):
        if job.last_run_at is None or now - job.last_run_at >= FREQ[job.frequency]:
            due.append(job)
    return due


@transaction.atomic
def set_record_validation(record, user, status, request=None):
    record.validation_status = status
    record.validated_by = user
    record.validated_at = timezone.now()
    record.save(update_fields=["validation_status", "validated_by", "validated_at"])
    audit_log(user, f"scraped_record.{status.lower()}", "ScrapedRecord", record.pk, request=request)
    return record
