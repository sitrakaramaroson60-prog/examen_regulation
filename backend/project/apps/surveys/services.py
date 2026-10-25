import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import log as audit_log
from apps.notifications.models import Notification
from apps.notifications.services import notify, users_of

from .models import Survey, SurveyAnswer, SurveyQuestion, SurveyResponse

TOKEN_SALT = "survey-participation"


# ---------- cycle de vie ----------
def is_open(survey, now=None):
    now = now or timezone.now()
    if survey.status != Survey.Status.PUBLISHED:
        return False
    if survey.starts_at and survey.starts_at > now:
        return False
    if survey.ends_at and survey.ends_at < now:
        return False
    return True


@transaction.atomic
def publish_survey(survey, actor, request=None):
    if survey.status not in (Survey.Status.DRAFT, Survey.Status.PENDING_APPROVAL):
        raise ValidationError("Seul un sondage en brouillon peut être publié.")
    if not survey.questions.exists():
        raise ValidationError("Un sondage doit contenir au moins une question.")
    if survey.organization.code != "ARTEC" and settings.SURVEY_OPERATOR_APPROVAL_REQUIRED:
        survey.status = Survey.Status.PENDING_APPROVAL
        survey.save(update_fields=["status", "updated_at"])
        notify(users_of(roles=("ARTEC_PUBLISHER", "ARTEC_REGULATOR")), "Sondage à valider", f"Un sondage de {survey.organization.code} attend votre validation.", Notification.Type.SURVEY_APPROVAL, survey)
        audit_log(actor, "survey.submitted_for_approval", "Survey", survey.pk, request=request)
        return survey
    survey.status = Survey.Status.PUBLISHED
    survey.published_at = timezone.now()
    survey.save(update_fields=["status", "published_at", "updated_at"])
    audit_log(actor, "survey.published", "Survey", survey.pk, request=request)
    return survey


@transaction.atomic
def approve_survey(survey, actor, request=None):
    if survey.status != Survey.Status.PENDING_APPROVAL:
        raise ValidationError("Ce sondage n'est pas en attente de validation.")
    survey.status = Survey.Status.PUBLISHED
    survey.published_at = timezone.now()
    survey.save(update_fields=["status", "published_at", "updated_at"])
    audit_log(actor, "survey.approved", "Survey", survey.pk, request=request)
    return survey


@transaction.atomic
def reject_survey(survey, actor, reason, request=None):
    if survey.status != Survey.Status.PENDING_APPROVAL:
        raise ValidationError("Ce sondage n'est pas en attente de validation.")
    survey.status = Survey.Status.DRAFT
    survey.rejection_reason = reason[:300]
    survey.save(update_fields=["status", "rejection_reason", "updated_at"])
    audit_log(actor, "survey.rejected", "Survey", survey.pk, {"reason": reason}, request=request)
    return survey


@transaction.atomic
def close_survey(survey, actor, request=None):
    if survey.status != Survey.Status.PUBLISHED:
        raise ValidationError("Seul un sondage publié peut être clos.")
    survey.status = Survey.Status.CLOSED
    survey.save(update_fields=["status", "updated_at"])
    audit_log(actor, "survey.closed", "Survey", survey.pk, request=request)
    return survey


# ---------- participation ----------
def issue_token(survey):
    return signing.dumps({"s": survey.pk, "t": timezone.now().timestamp()}, salt=TOKEN_SALT)


def check_token(survey, token):
    if not token:
        raise ValidationError({"participation_token": "Jeton de participation requis."})
    try:
        data = signing.loads(token, salt=TOKEN_SALT, max_age=settings.SURVEY_TOKEN_MAX_SECONDS)
    except signing.BadSignature:
        raise ValidationError({"participation_token": "Jeton invalide ou expiré."})
    if data.get("s") != survey.pk:
        raise ValidationError({"participation_token": "Jeton invalide pour ce sondage."})
    if timezone.now().timestamp() - data["t"] < settings.SURVEY_TOKEN_MIN_SECONDS:
        raise ValidationError({"participation_token": "Soumission trop rapide, veuillez réessayer."})


def make_fingerprint(request, survey):
    """Empreinte anonyme et salée : ne permet pas de remonter à l'IP, sert uniquement à limiter les doublons."""
    ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", ""))
    ua = request.META.get("HTTP_USER_AGENT", "")[:200]
    key = f"{settings.SURVEY_FINGERPRINT_SALT}:{survey.pk}".encode()
    return hmac.new(key, f"{ip}|{ua}".encode(), hashlib.sha256).hexdigest()


def check_duplicates(survey, fingerprint):
    qs = SurveyResponse.objects.filter(survey=survey, fingerprint=fingerprint)
    if survey.duplicate_policy == Survey.DuplicatePolicy.ONE_TOTAL and qs.exists():
        raise ValidationError("Une réponse a déjà été enregistrée depuis ce navigateur pour ce sondage.")
    if survey.duplicate_policy == Survey.DuplicatePolicy.ONE_PER_DAY and qs.filter(submitted_at__gte=timezone.now() - timedelta(days=1)).exists():
        raise ValidationError("Une réponse a déjà été enregistrée aujourd'hui pour ce sondage.")


def _validate_answer(question, raw):
    Q = SurveyQuestion.Type
    t = question.question_type
    out = {"text_value": "", "number_value": None, "bool_value": None, "choices": []}
    if t in (Q.SHORT_TEXT, Q.LONG_TEXT):
        if not isinstance(raw, str):
            raise ValidationError("Texte attendu.")
        from django.utils.html import strip_tags

        text = strip_tags(raw).strip()
        limit = question.max_length or (255 if t == Q.SHORT_TEXT else 2000)
        if len(text) > limit:
            raise ValidationError(f"{limit} caractères maximum.")
        out["text_value"] = text
    elif t in (Q.NUMBER, Q.SATISFACTION):
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValidationError("Nombre attendu.")
        lo = question.min_value if question.min_value is not None else (1 if t == Q.SATISFACTION else None)
        hi = question.max_value if question.max_value is not None else (5 if t == Q.SATISFACTION else None)
        if lo is not None and raw < lo or hi is not None and raw > hi:
            raise ValidationError(f"Valeur hors limites ({lo} – {hi}).")
        out["number_value"] = float(raw)
    elif t == Q.YES_NO:
        if not isinstance(raw, bool):
            raise ValidationError("Booléen attendu.")
        out["bool_value"] = raw
    elif t in (Q.SINGLE_CHOICE, Q.MULTIPLE_CHOICE):
        ids = raw if isinstance(raw, list) else [raw]
        if not ids or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
            raise ValidationError("Identifiants de choix attendus.")
        if t == Q.SINGLE_CHOICE and len(ids) != 1:
            raise ValidationError("Un seul choix est attendu.")
        valid = {c.id: c for c in question.choices.all()}
        if len(set(ids)) != len(ids) or any(i not in valid for i in ids):
            raise ValidationError("Choix invalide pour cette question.")
        out["choices"] = [valid[i] for i in ids]
    return out


@transaction.atomic
def submit_response(survey, data, request):
    """Valide et enregistre une réponse publique. `data` est déjà validé pour la localisation."""
    if not is_open(survey):
        raise ValidationError("Ce sondage n'accepte plus de réponses.")
    if survey.require_participation_token:
        check_token(survey, data.get("participation_token"))
    fingerprint = make_fingerprint(request, survey)
    check_duplicates(survey, fingerprint)

    questions = {q.id: q for q in survey.questions.prefetch_related("choices")}
    answers_in = {}
    for item in data["answers"]:
        qid = item["question"]
        if qid not in questions:
            raise ValidationError({"answers": f"Question {qid} étrangère à ce sondage."})
        if qid in answers_in:
            raise ValidationError({"answers": f"Question {qid} répondue plusieurs fois."})
        answers_in[qid] = item.get("value")

    errors = {}
    parsed = {}
    for qid, q in questions.items():
        raw = answers_in.get(qid)
        if raw is None or raw == "" or raw == []:
            if q.is_required:
                errors[str(qid)] = "Réponse obligatoire."
            continue
        try:
            parsed[qid] = _validate_answer(q, raw)
        except ValidationError as exc:
            errors[str(qid)] = exc.detail[0] if isinstance(exc.detail, list) else exc.detail
    if errors:
        raise ValidationError({"answers": errors})

    response = SurveyResponse.objects.create(
        survey=survey, region=data["region"], city=data["city"], location_context=data["location_context"],
        operator=data.get("operator"), service_type=data.get("service_type", ""), fingerprint=fingerprint,
    )
    for qid, p in parsed.items():
        ans = SurveyAnswer.objects.create(response=response, question=questions[qid], text_value=p["text_value"], number_value=p["number_value"], bool_value=p["bool_value"])
        if p["choices"]:
            ans.choices.set(p["choices"])
    _feed_qos(survey, response, questions, parsed)
    return response


def _feed_qos(survey, response, questions, parsed):
    """Les réponses numériques liées à un indicateur alimentent les données QoS (source SURVEY, perception des usagers).
    Sans opérateur identifié (ni dans le sondage ni dans la réponse), rien n'est attribué."""
    from apps.qos.models import QoSMeasurement
    from apps.qos.rules import INDICATORS, normalize, validate_metric

    operator = response.operator or survey.target_operator
    if operator is None:
        return
    batch = []
    for qid, p in parsed.items():
        metric = questions[qid].qos_metric
        if not metric or p["number_value"] is None:
            continue
        unit = INDICATORS[metric]["unit"]
        value, unit = normalize(metric, p["number_value"], unit)
        if validate_metric(metric, value, unit):
            continue
        batch.append(QoSMeasurement(
            operator=operator, region=response.region, city=response.city, service_type=response.service_type or "SURVEY",
            technology="N/A", metric_name=metric, metric_value=value, unit=unit, measurement_method=f"sondage:{survey.pk}",
            source_type=QoSMeasurement.SourceType.SURVEY, measured_at=timezone.now(), validation_status=QoSMeasurement.ValidationStatus.VALIDATED,
        ))
    QoSMeasurement.objects.bulk_create(batch)
    if batch:
        from apps.qos.services import announce_measurements

        announce_measurements(operator.pk)


# ---------- résultats ----------
def aggregate_results(survey, public=False):
    """Résultats agrégés. En mode public : pas de texte libre, et suppression des groupes sous le seuil minimal."""
    total = survey.responses.count()
    min_n = settings.SURVEY_PUBLIC_MIN_RESPONDENTS if public else 0
    result = {"survey": survey.pk, "title": survey.title, "total_responses": total, "questions": [], "by_region": []}
    if public and total < min_n:
        result["suppressed"] = True
        result["message"] = f"Résultats disponibles à partir de {min_n} réponses."
        return result
    for q in survey.questions.prefetch_related("choices"):
        item = {"id": q.id, "text": q.text, "type": q.question_type}
        answers = SurveyAnswer.objects.filter(question=q)
        item["answered"] = answers.count()
        if q.question_type in ("SINGLE_CHOICE", "MULTIPLE_CHOICE"):
            counts = {c.id: 0 for c in q.choices.all()}
            for row in answers.values("choices").annotate(n=Count("id")):
                if row["choices"] in counts:
                    counts[row["choices"]] = row["n"]
            item["choices"] = [{"id": c.id, "label": c.label, "count": counts[c.id]} for c in q.choices.all()]
        elif q.question_type in ("NUMBER", "SATISFACTION"):
            item["average"] = answers.aggregate(a=Avg("number_value"))["a"]
        elif q.question_type == "YES_NO":
            item["yes"] = answers.filter(bool_value=True).count()
            item["no"] = answers.filter(bool_value=False).count()
        elif not public:
            item["texts"] = list(answers.exclude(text_value="").values_list("text_value", flat=True)[:200])
        result["questions"].append(item)
    for row in survey.responses.values("region__name").annotate(n=Count("id")).order_by("-n"):
        if row["n"] >= min_n:
            result["by_region"].append({"region": row["region__name"], "count": row["n"]})
    return result
