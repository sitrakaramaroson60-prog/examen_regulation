"""Baromètre public : moyennes agrégées par opérateur, uniquement si l'ARTEC l'a activé et avec un volume minimal de mesures."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Avg, Count
from django.utils import timezone

from apps.publications.models import Publication
from apps.surveys.models import Survey, SurveyResponse

from .models import PublicBarometerSetting, QoSMeasurement
from .rules import INDICATORS, TECHNICAL_METRICS
from .thresholds import classify, find_threshold


def public_summary():
    now = timezone.now()
    cfg = PublicBarometerSetting.current()
    out = {
        "enabled": cfg.enabled,
        "participation": {
            "open_surveys": Survey.objects.filter(status="PUBLISHED").count(),
            "responses": SurveyResponse.objects.filter(survey__results_public=True).count(),
            "publications": Publication.objects.filter(status="PUBLISHED", audience="PUBLIC", published_at__lte=now).count(),
        },
        "period_days": 90,
        "indicators": [],
    }
    if not cfg.enabled:
        out["message"] = "Le baromètre public de la qualité de service n'a pas encore été publié par l'ARTEC."
        return out
    qs = QoSMeasurement.objects.filter(validation_status="VALIDATED", source_type="TECHNICAL", metric_name__in=TECHNICAL_METRICS, measured_at__gte=now - timedelta(days=90))
    rows = qs.values("metric_name", "unit", "measurement_method", "operator__code").annotate(avg=Avg("metric_value"), n=Count("id"))
    by_metric = {}
    for r in rows:
        by_metric.setdefault(r["metric_name"], {}).setdefault((r["unit"], r["measurement_method"]), []).append(r)
    for metric in TECHNICAL_METRICS:
        groups = by_metric.get(metric)
        if not groups:
            continue
        (unit, method), items = max(groups.items(), key=lambda kv: sum(i["n"] for i in kv[1]))  # méthode la plus renseignée : jamais de mélange
        th = find_threshold(metric, "", "", now.date())
        ops = [{"operator": i["operator__code"], "average": round(i["avg"], 2), "status": classify(i["avg"], th)} for i in items if i["n"] >= cfg.min_measurements]
        if ops:
            out["indicators"].append({"metric": metric, "label": INDICATORS[metric]["label"], "unit": unit, "method": method, "higher_is_better": INDICATORS[metric]["higher_is_better"], "operators": ops})
    return out
