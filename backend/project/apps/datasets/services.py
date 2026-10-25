"""Import, validation et revue des datasets. Les fichiers importés ne sont jamais exécutés : lecture pandas uniquement."""
import io
import json
import os

import pandas as pd
from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import log as audit_log
from apps.common.files import sha256_of
from apps.notifications.models import Notification
from apps.notifications.services import notify, users_of

from .models import Dataset, DatasetSubmission, DatasetValidationReport, DatasetVersion, SubmissionEvent
from .schemas import ALLOWED_EXTENSIONS, DUPLICATE_KEYS, SCHEMAS

MAX_ROWS = 500_000


def _sniff(f, ext):
    """Contrôle du contenu réel (pas seulement de l'extension)."""
    f.seek(0)
    head = f.read(2048)
    f.seek(0)
    if ext == "xlsx":
        if not head.startswith(b"PK\x03\x04"):
            raise ValidationError({"file": "Le fichier n'est pas un classeur XLSX valide."})
    else:
        if b"\x00" in head:
            raise ValidationError({"file": "Contenu binaire inattendu pour un fichier texte."})
        try:
            head.decode("utf-8")
        except UnicodeDecodeError:
            try:
                head.decode("latin-1")
            except UnicodeDecodeError:
                raise ValidationError({"file": "Encodage non reconnu."})
        if ext == "json" and not head.lstrip()[:1] in (b"[", b"{"):
            raise ValidationError({"file": "Le fichier n'est pas un JSON valide."})


def validate_upload(f):
    ext = os.path.splitext(f.name)[1].lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError({"file": f"Extension non autorisée. Formats acceptés : {', '.join(sorted(ALLOWED_EXTENSIONS))}."})
    if f.size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise ValidationError({"file": f"Fichier trop volumineux (max {settings.MAX_UPLOAD_SIZE_MB} Mo)."})
    if f.size == 0:
        raise ValidationError({"file": "Fichier vide."})
    _sniff(f, ext)
    return ext


def read_dataframe(path_or_file, ext):
    try:
        if ext == "csv":
            try:
                df = pd.read_csv(path_or_file, dtype=str, keep_default_na=False, na_values=[""], nrows=MAX_ROWS + 1, encoding="utf-8")
            except UnicodeDecodeError:
                if hasattr(path_or_file, "seek"):
                    path_or_file.seek(0)
                df = pd.read_csv(path_or_file, dtype=str, keep_default_na=False, na_values=[""], nrows=MAX_ROWS + 1, encoding="latin-1")
        elif ext == "xlsx":
            df = pd.read_excel(path_or_file, dtype=str, engine="openpyxl", nrows=MAX_ROWS + 1)
        else:
            raw = path_or_file.read() if hasattr(path_or_file, "read") else open(path_or_file, "rb").read()
            data = json.loads(raw)
            if isinstance(data, dict):
                data = data.get("records") or data.get("data") or [data]
            df = pd.json_normalize(data).astype(object).where(lambda d: d.notna(), None)
            df = df.map(lambda v: None if v is None else str(v))
    except Exception as exc:  # noqa: BLE001
        raise ValidationError({"file": f"Fichier illisible : {type(exc).__name__}."})
    if len(df) > MAX_ROWS:
        raise ValidationError({"file": f"Trop de lignes (max {MAX_ROWS})."})
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _check_type(series, logical):
    s = series.dropna()
    if logical == "float":
        converted = pd.to_numeric(s, errors="coerce")
        return int(converted.isna().sum())
    if logical == "datetime":
        converted = pd.to_datetime(s, errors="coerce", utc=True, format="mixed")
        return int(converted.isna().sum())
    return 0


def build_report(df, data_type):
    schema = SCHEMAS.get(data_type, {})
    messages, type_errors, missing_values = [], {}, {}
    missing_cols = [c for c, (_, required) in schema.items() if required and c not in df.columns]
    if missing_cols:
        messages.append(f"Colonnes obligatoires absentes : {', '.join(missing_cols)}.")
    for col, (logical, required) in schema.items():
        if col in df.columns:
            bad = _check_type(df[col], logical)
            if bad:
                type_errors[col] = bad
                messages.append(f"{bad} valeur(s) invalide(s) dans « {col} » (type attendu : {logical}).")
            if required:
                n_missing = int(df[col].isna().sum())
                if n_missing:
                    missing_values[col] = n_missing
    for col in df.columns:
        n = int(df[col].isna().sum())
        if n and col not in missing_values:
            missing_values[col] = n
    keys = [c for c in DUPLICATE_KEYS.get(data_type, []) if c in df.columns]
    duplicates = int(df.duplicated(subset=keys).sum()) if keys else int(df.duplicated().sum())
    if duplicates:
        messages.append(f"{duplicates} ligne(s) en doublon.")
    rows = len(df)
    if rows == 0:
        messages.append("Le fichier ne contient aucune ligne.")
    cells = max(rows * max(len(df.columns), 1), 1)
    quality = 1 - (sum(missing_values.values()) + sum(type_errors.values()) + duplicates) / cells
    quality = round(max(0.0, min(1.0, quality)) * 100, 1)
    if missing_cols or rows == 0 or any(c in type_errors or c in missing_values for c, (_, req) in schema.items() if req):
        status = DatasetValidationReport.Status.INVALID
    elif duplicates or missing_values:
        status = DatasetValidationReport.Status.VALID_WITH_WARNINGS
    else:
        status = DatasetValidationReport.Status.VALID
    return {
        "status": status, "row_count": rows, "missing_columns": missing_cols, "type_errors": type_errors,
        "missing_values": missing_values, "duplicate_rows": duplicates, "quality_score": quality, "messages": messages,
    }


@transaction.atomic
def create_version(dataset, uploaded_file, user, request=None):
    ext = validate_upload(uploaded_file)
    df = read_dataframe(uploaded_file, ext)
    uploaded_file.seek(0)
    checksum = sha256_of(uploaded_file)
    last = Dataset.objects.select_for_update().get(pk=dataset.pk).versions.aggregate(m=Max("version_number"))["m"] or 0
    version = DatasetVersion(
        dataset=dataset, version_number=last + 1, original_name=os.path.basename(uploaded_file.name)[:255], file_format=ext,
        checksum=checksum, schema_definition={c: str(t) for c, t in df.dtypes.items()}, row_count=len(df), uploaded_by=user,
    )
    version.file.save(f"v{last + 1}.{ext}", uploaded_file, save=False)
    version.save()
    DatasetValidationReport.objects.create(dataset_version=version, **build_report(df, dataset.data_type))
    audit_log(user, "dataset.imported", "DatasetVersion", version.pk, {"dataset": dataset.pk, "rows": len(df), "checksum": checksum}, request=request)
    return version


def revalidate(version):
    ext = version.file_format
    with version.file.open("rb") as fh:
        df = read_dataframe(fh, ext)
    data = build_report(df, version.dataset.data_type)
    report, _ = DatasetValidationReport.objects.update_or_create(dataset_version=version, defaults=data)
    return report


def load_dataframe(version):
    with version.file.open("rb") as fh:
        return read_dataframe(fh, version.file_format)


def _event(submission, actor, new_status, comment=""):
    SubmissionEvent.objects.create(submission=submission, actor=actor, from_status=submission.status, to_status=new_status, comment=comment)


@transaction.atomic
def submit_version(version, user, request=None):
    report = version.report
    if report.status == DatasetValidationReport.Status.INVALID:
        raise ValidationError("Le rapport de validation est invalide : corrigez le fichier avant soumission.")
    if version.dataset.owner_organization.code == "ARTEC":
        raise ValidationError("Les datasets de l'ARTEC ne sont pas soumis à examen.")
    if version.submissions.filter(status__in=[DatasetSubmission.Status.SUBMITTED, DatasetSubmission.Status.UNDER_REVIEW, DatasetSubmission.Status.ACCEPTED]).exists():
        raise ValidationError("Cette version est déjà soumise ou acceptée.")
    sub = DatasetSubmission.objects.create(dataset_version=version, submitted_by=user)
    SubmissionEvent.objects.create(submission=sub, actor=user, from_status="", to_status=sub.status)
    notify(users_of(roles=("ARTEC_REGULATOR",)), "Nouvelle soumission de dataset", f"Soumission {sub.reference} reçue de {version.dataset.owner_organization.code}.", Notification.Type.DATASET_SUBMITTED, sub)
    audit_log(user, "dataset.submitted", "DatasetSubmission", sub.pk, {"version": version.pk}, request=request)
    return sub


TRANSITIONS = {
    "start-review": ({"SUBMITTED"}, "UNDER_REVIEW"),
    "request-correction": ({"SUBMITTED", "UNDER_REVIEW"}, "CORRECTION_REQUIRED"),
    "accept": ({"UNDER_REVIEW"}, "ACCEPTED"),
    "reject": ({"SUBMITTED", "UNDER_REVIEW"}, "REJECTED"),
}
NEEDS_COMMENT = {"request-correction", "reject"}
NOTIFY = {
    "request-correction": (Notification.Type.CORRECTION_REQUESTED, "Correction demandée"),
    "accept": (Notification.Type.DATASET_ACCEPTED, "Dataset accepté"),
    "reject": (Notification.Type.DATASET_REJECTED, "Dataset rejeté"),
}


@transaction.atomic
def review(submission, action_name, reviewer, comment="", request=None):
    allowed_from, target = TRANSITIONS[action_name]
    submission = DatasetSubmission.objects.select_for_update().get(pk=submission.pk)
    if submission.status not in allowed_from:
        raise ValidationError(f"Transition impossible depuis l'état « {submission.status} ».")
    comment = (comment or "").strip()
    if action_name in NEEDS_COMMENT and not comment:
        raise ValidationError({"comment": "Un motif est obligatoire."})
    _event(submission, reviewer, target, comment)
    submission.status = target
    submission.reviewed_by = reviewer
    submission.review_comment = comment or submission.review_comment
    submission.reviewed_at = timezone.now()
    submission.save()
    if target == "ACCEPTED":
        from apps.qos.services import ingest_from_version

        ingest_from_version(submission.dataset_version, validated=True)
    if action_name in NOTIFY:
        ntype, title = NOTIFY[action_name]
        org = submission.dataset_version.dataset.owner_organization
        notify(users_of(org, roles=("OPERATOR_USER",)), title, f"Soumission {submission.reference} : {title.lower()}." + (f" Motif : {comment}" if comment else ""), ntype, submission)
    audit_log(reviewer, f"submission.{action_name}", "DatasetSubmission", submission.pk, {"comment": comment}, request=request)
    return submission


def is_usable_for_analysis(version):
    """Une version est exploitable si acceptée par l'ARTEC (opérateur) ou valide et propre à l'ARTEC."""
    if version.dataset.owner_organization.code == "ARTEC":
        return version.report.status != DatasetValidationReport.Status.INVALID
    return version.submissions.filter(status=DatasetSubmission.Status.ACCEPTED).exists()
