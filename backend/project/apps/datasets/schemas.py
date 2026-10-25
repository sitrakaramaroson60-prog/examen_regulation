"""Schémas attendus par type de données. Les colonnes obligatoires et leurs types sont validés à l'import."""

QOS_MEASUREMENT = "QOS_MEASUREMENT"
LABELED_TRAINING = "LABELED_TRAINING"
OTHER = "OTHER"

DATA_TYPES = [
    (QOS_MEASUREMENT, "Mesures QoS"),
    (LABELED_TRAINING, "Jeu étiqueté pour entraînement"),
    (OTHER, "Autre"),
]

# colonne -> (type logique, obligatoire)
SCHEMAS = {
    QOS_MEASUREMENT: {
        "region": ("str", True),
        "city": ("str", True),
        "service_type": ("str", True),
        "technology": ("str", True),
        "metric_name": ("str", True),
        "metric_value": ("float", True),
        "unit": ("str", True),
        "measurement_method": ("str", True),
        "measured_at": ("datetime", True),
    },
    LABELED_TRAINING: {
        "quality_class": ("str", True),  # GOOD / MEDIUM / POOR
        "campaign_id": ("str", True),  # sert à éviter les fuites train/test
    },
    OTHER: {},
}

# Colonnes dont l'unicité identifie une observation (détection des doublons)
DUPLICATE_KEYS = {
    QOS_MEASUREMENT: ["region", "city", "service_type", "technology", "metric_name", "measured_at", "measurement_method"],
}

ALLOWED_EXTENSIONS = {"csv", "xlsx", "json"}
