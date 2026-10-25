"""Catalogue des indicateurs de qualité de service et règles de validation."""

# Sens : higher_is_better=True => plus la valeur est élevée, meilleure est la qualité.
INDICATORS = {
    "availability": {"label": "Disponibilité du réseau", "unit": "%", "higher_is_better": True},
    "download_speed": {"label": "Débit descendant", "unit": "Mbps", "higher_is_better": True},
    "upload_speed": {"label": "Débit montant", "unit": "Mbps", "higher_is_better": True},
    "latency": {"label": "Latence", "unit": "ms", "higher_is_better": False},
    "jitter": {"label": "Gigue", "unit": "ms", "higher_is_better": False},
    "packet_loss": {"label": "Taux de perte de paquets", "unit": "%", "higher_is_better": False},
    "call_success_rate": {"label": "Taux de réussite des appels", "unit": "%", "higher_is_better": True},
    "connection_success_rate": {"label": "Taux de réussite des connexions", "unit": "%", "higher_is_better": True},
    "call_failure_rate": {"label": "Taux d'échec des appels", "unit": "%", "higher_is_better": False},
    "drop_rate": {"label": "Taux de coupure des appels", "unit": "%", "higher_is_better": False},
    "satisfaction": {"label": "Satisfaction déclarée (sondages)", "unit": "score", "higher_is_better": True},
}

_EXTRA_UNITS = {"download_speed": {"kbps"}, "upload_speed": {"kbps"}}
METRICS = {k: {v["unit"]} | _EXTRA_UNITS.get(k, set()) for k, v in INDICATORS.items()}
PERCENT_METRICS = {k for k, v in INDICATORS.items() if v["unit"] == "%"}
NON_NEGATIVE = set(METRICS) - {"satisfaction"}
TECHNICAL_METRICS = [k for k in INDICATORS if k != "satisfaction"]


def validate_metric(name, value, unit):
    """Retourne None si valide, sinon un message d'erreur."""
    if name not in METRICS:
        return f"Indicateur inconnu : {name}."
    if unit not in METRICS[name]:
        return f"Unité « {unit} » non admise pour {name} (attendu : {', '.join(sorted(METRICS[name]))})."
    if name in NON_NEGATIVE and value < 0:
        return "Valeur négative impossible."
    if name in PERCENT_METRICS and value > 100:
        return "Pourcentage supérieur à 100."
    if name == "satisfaction" and not 1 <= value <= 5:
        return "Score de satisfaction hors de l'échelle 1–5."
    return None


def normalize(name, value, unit):
    """Convertit vers l'unité canonique (kbps -> Mbps) afin de ne jamais moyenner des unités différentes."""
    if unit == "kbps" and name in ("download_speed", "upload_speed"):
        return value / 1000.0, "Mbps"
    return value, unit
