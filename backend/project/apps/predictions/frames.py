"""Construction des jeux de données de prédiction à partir des mesures QoS validées.

Anticipation : les variables décrivent la période t ; l'étiquette (GOOD/MEDIUM/POOR) est la classe de la
période t+1, déterminée par les seuils configurés. Aucune étiquette n'est inventée : sans seuil ou sans
historique suffisant, la construction échoue avec un message explicite.
"""
from datetime import timedelta

import pandas as pd
from rest_framework.exceptions import ValidationError

from apps.qos.models import QoSMeasurement
from apps.qos.rules import INDICATORS, TECHNICAL_METRICS
from apps.qos.thresholds import classify, find_threshold, worst

RISK_TYPES = {
    "GENERAL_QUALITY": {"label": "Qualité globale", "targets": None, "note": "Pire classe parmi les indicateurs disposant d'un seuil."},
    "THROUGHPUT_DEGRADATION": {"label": "Dégradation du débit", "targets": ["download_speed"], "note": ""},
    "AVAILABILITY_DROP": {"label": "Baisse de disponibilité", "targets": ["availability"], "note": ""},
    "CONGESTION": {"label": "Risque de congestion", "targets": ["latency", "packet_loss", "jitter"],
                   "note": "Indicateur indirect : la congestion n'est pas mesurée directement, elle est approchée par latence, gigue et perte de paquets."},
    "THRESHOLD_BREACH": {"label": "Non-respect d'un seuil réglementaire", "targets": None, "note": "Pire classe parmi tous les indicateurs disposant d'un seuil."},
}
RISK_CLASS_LABELS = {"GOOD": "Risque faible", "MEDIUM": "Risque modéré", "POOR": "Risque élevé"}
GRANULARITIES = {"week": ("%G-W%V", 7), "month": ("%Y-%m", 31)}
KEY = ["operator", "region", "technology"]


def feature_label(name):
    if name.endswith("_delta"):
        return f"{INDICATORS.get(name[:-6], {}).get('label', name[:-6])} (évolution)"
    return INDICATORS.get(name, {}).get("label", {"n_measurements": "Nombre de mesures"}.get(name, name))


def _period_table(sources, granularity):
    qs = QoSMeasurement.objects.filter(validation_status="VALIDATED", source_type__in=sources, metric_name__in=TECHNICAL_METRICS)
    rows = list(qs.values("operator__code", "region__name", "technology", "metric_name", "metric_value", "measured_at"))
    if not rows:
        raise ValidationError("Aucune mesure QoS validée pour les sources demandées : importez et faites accepter des datasets d'abord.")
    df = pd.DataFrame(rows).rename(columns={"operator__code": "operator", "region__name": "region"})
    df["measured_at"] = pd.to_datetime(df["measured_at"], utc=True)
    fmt = GRANULARITIES[granularity][0]
    df["period"] = df["measured_at"].dt.strftime(fmt)
    df["period_start"] = df["measured_at"].dt.tz_localize(None).dt.to_period("W" if granularity == "week" else "M").dt.start_time
    piv = df.pivot_table(index=KEY + ["period", "period_start"], columns="metric_name", values="metric_value", aggfunc="mean")
    piv["n_measurements"] = df.groupby(KEY + ["period", "period_start"]).size()
    piv = piv.reset_index().sort_values(KEY + ["period_start"])
    metrics = [m for m in TECHNICAL_METRICS if m in piv.columns and piv[m].notna().mean() >= 0.5]
    if not metrics:
        raise ValidationError("Les indicateurs sont trop peu renseignés pour construire des variables.")
    for m in metrics:
        piv[f"{m}_delta"] = piv.groupby(KEY)[m].diff()
    period_order = {p: i for i, p in enumerate(sorted(piv["period_start"].unique()))}
    piv["period_index"] = piv["period_start"].map(period_order)
    return piv, metrics


def _class_of_period(row, targets, granularity):
    end = (row["period_start"] + timedelta(days=GRANULARITIES[granularity][1])).date()
    classes = []
    for m in (targets if targets else TECHNICAL_METRICS):
        val = row.get(m)
        if val is None or pd.isna(val):
            continue
        classes.append(classify(val, find_threshold(m, row["technology"], "", end)))
    return worst(classes)


def build_training_frame(risk_type="GENERAL_QUALITY", granularity="month", sources=("TECHNICAL",)):
    if risk_type not in RISK_TYPES:
        raise ValidationError({"risk_type": f"Valeurs admises : {', '.join(RISK_TYPES)}."})
    if granularity not in GRANULARITIES:
        raise ValidationError({"granularity": "Valeurs admises : week, month."})
    piv, metrics = _period_table(list(sources), granularity)
    targets = RISK_TYPES[risk_type]["targets"]
    piv["_class"] = piv.apply(lambda r: _class_of_period(r, targets, granularity), axis=1)
    if piv["_class"].isna().all():
        raise ValidationError("Aucun seuil QoS applicable : configurez les seuils (origine documentée) avant de construire un jeu étiqueté.")
    nxt = piv.groupby(KEY)[["_class", "period_index"]].shift(-1)
    piv["quality_class"] = nxt["_class"]
    piv["_next_index"] = nxt["period_index"]
    out = piv[(piv["_next_index"] - piv["period_index"] == 1) & piv["quality_class"].notna()].copy()
    if out.empty:
        raise ValidationError("Historique insuffisant : il faut au moins deux périodes consécutives par opérateur, région et technologie.")
    feats = metrics + [f"{m}_delta" for m in metrics] + ["n_measurements"]
    out["observation_id"] = out[KEY].astype(str).agg("|".join, axis=1) + "|" + out["period"]
    out["campaign_id"] = out["period"]
    cols = ["observation_id", "operator", "region", "technology", "period", "period_index"] + feats + ["quality_class", "campaign_id"]
    return out[cols].round(4), {"risk_type": risk_type, "granularity": granularity, "sources": list(sources), "features": feats}


def build_inference_frame(granularity="month", sources=("TECHNICAL",)):
    """Dernière période disponible de chaque (opérateur, région, technologie) : variables seulement, sans étiquette."""
    piv, metrics = _period_table(list(sources), granularity)
    last = piv.sort_values("period_start").groupby(KEY).tail(1).copy()
    feats = metrics + [f"{m}_delta" for m in metrics] + ["n_measurements"]
    last["observation_id"] = last[KEY].astype(str).agg("|".join, axis=1) + "|" + last["period"]
    return last[["observation_id", "operator", "region", "technology", "period"] + feats].round(4), feats
