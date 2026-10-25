"""Tableau de bord de supervision de la QoS : indicateurs comparables entre opérateurs.

Principes : jamais de moyenne entre méthodes de mesure ou unités différentes ; les mesures techniques sont
séparées des déclarations, des sondages et du scraping ; l'écart déclaré/mesuré est affiché explicitement.
"""
from datetime import timedelta

from django.db.models import Avg, Count
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.organizations.models import Organization

from .models import QoSMeasurement
from .rules import INDICATORS
from .thresholds import classify, find_threshold

SOURCES = [s for s, _ in QoSMeasurement.SourceType.choices]


def _filtered(qs, p):
    if p.get("region"):
        qs = qs.filter(region_id=p["region"])
    if p.get("technology"):
        qs = qs.filter(technology=p["technology"])
    if p.get("service_type"):
        qs = qs.filter(service_type=p["service_type"])
    return qs


def build_dashboard(base_qs, params):
    now = timezone.now()
    date_to = params.get("date_to") or now
    date_from = params.get("date_from") or (date_to - timedelta(days=90))
    sources = [s for s in (params.get("sources") or ["TECHNICAL"]) if s in SOURCES] or ["TECHNICAL"]

    scope = _filtered(base_qs.filter(measured_at__gte=date_from, measured_at__lte=date_to), params)
    main = scope.filter(source_type__in=sources)
    operators = list(Organization.objects.filter(organization_type="OPERATOR", is_active=True).values_list("code", flat=True))
    visible_ops = [params["only_operator"]] if params.get("only_operator") else operators

    rows = (
        main.values("metric_name", "unit", "measurement_method", "operator__code")
        .annotate(avg=Avg("metric_value"), n=Count("id"))
    )
    trend_rows = (
        main.annotate(month=TruncMonth("measured_at"))
        .values("metric_name", "unit", "measurement_method", "operator__code", "month")
        .annotate(avg=Avg("metric_value"))
        .order_by("month")
    )
    tech, svc = params.get("technology") or "", params.get("service_type") or ""
    today = now.date()

    indicators = []
    for metric, meta in INDICATORS.items():
        groups = {}
        for r in rows:
            if r["metric_name"] != metric:
                continue
            g = groups.setdefault((r["unit"], r["measurement_method"]), {"unit": r["unit"], "method": r["measurement_method"], "operators": {}, "trend": {}})
            g["operators"][r["operator__code"]] = {"average": round(r["avg"], 3), "count": r["n"]}
        for r in trend_rows:
            if r["metric_name"] != metric:
                continue
            g = groups.get((r["unit"], r["measurement_method"]))
            if g:
                g["trend"].setdefault(r["month"].strftime("%Y-%m"), {})[r["operator__code"]] = round(r["avg"], 3)
        threshold = find_threshold(metric, tech, svc, today)
        out_groups = []
        for g in sorted(groups.values(), key=lambda x: -sum(o["count"] for o in x["operators"].values())):
            ops = [
                {"operator": code, **(g["operators"].get(code) or {"average": None, "count": 0}),
                 "status": classify(g["operators"].get(code, {}).get("average"), threshold)}
                for code in visible_ops
            ]
            out_groups.append({
                "unit": g["unit"], "method": g["method"], "operators": ops,
                "comparable": sum(1 for o in ops if o["count"]) >= 2,
                "trend": [{"month": m, **vals} for m, vals in sorted(g["trend"].items())],
            })
        indicators.append({
            "metric": metric, "label": meta["label"], "default_unit": meta["unit"], "higher_is_better": meta["higher_is_better"],
            "threshold": None if threshold is None else {"good": threshold.good_threshold, "poor": threshold.poor_threshold, "origin": threshold.origin},
            "groups": out_groups,
        })

    coverage = []
    cov_rows = scope.values("operator__code", "source_type").annotate(n=Count("id"))
    for code in visible_ops:
        entry = {"operator": code, **{s: 0 for s in SOURCES}}
        for r in cov_rows:
            if r["operator__code"] == code:
                entry[r["source_type"]] = r["n"]
        coverage.append(entry)

    # contrôle croisé : déclaré vs mesuré (même opérateur, indicateur, unité, méthode)
    def means(src):
        return {(r["operator__code"], r["metric_name"], r["unit"], r["measurement_method"]): r["avg"]
                for r in scope.filter(source_type=src).values("operator__code", "metric_name", "unit", "measurement_method").annotate(avg=Avg("metric_value"))}
    declared, measured = means("DECLARED"), means("TECHNICAL")
    cross = []
    for key, dv in declared.items():
        mv = measured.get(key)
        if mv is None:
            continue
        gap = dv - mv
        cross.append({"operator": key[0], "metric": key[1], "unit": key[2], "method": key[3], "declared": round(dv, 3), "measured": round(mv, 3),
                      "gap": round(gap, 3), "gap_pct": round(gap / mv * 100, 1) if mv else None})

    perception = [
        {"operator": r["operator__code"], "average": round(r["avg"], 2), "responses": r["n"]}
        for r in scope.filter(source_type="SURVEY", metric_name="satisfaction").values("operator__code").annotate(avg=Avg("metric_value"), n=Count("id"))
    ]
    notes = []
    if not main.exists():
        notes.append("Aucune mesure validée pour cette sélection (période, source, région ou technologie).")
    if not any(i["threshold"] for i in indicators):
        notes.append("Aucun seuil de référence n'est configuré : les statuts GOOD/MEDIUM/POOR ne peuvent pas être calculés.")
    return {
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "sources": sources, "operators": visible_ops, "indicators": indicators,
        "coverage": coverage, "declared_vs_measured": cross, "perception": perception, "notes": notes,
    }
