"""Évaluation d'une valeur par rapport aux seuils configurés (aucun seuil officiel n'est livré)."""
from django.db.models import Q

from .models import QoSThreshold

GOOD, MEDIUM, POOR = "GOOD", "MEDIUM", "POOR"
ORDER = {GOOD: 0, MEDIUM: 1, POOR: 2}


def find_threshold(metric, technology, service_type, on_date):
    qs = QoSThreshold.objects.filter(metric_name=metric, valid_from__lte=on_date).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=on_date))
    candidates = [t for t in qs if t.technology in ("", technology or "") and t.service_type in ("", service_type or "")]
    if not candidates:
        return None
    # le seuil le plus spécifique (technologie / service renseignés) puis le plus récent l'emporte
    return max(candidates, key=lambda t: (bool(t.technology) + bool(t.service_type), t.valid_from))


def classify(value, threshold):
    if threshold is None or value is None:
        return None
    if threshold.higher_is_better:
        return GOOD if value >= threshold.good_threshold else POOR if value < threshold.poor_threshold else MEDIUM
    return GOOD if value <= threshold.good_threshold else POOR if value > threshold.poor_threshold else MEDIUM


def worst(classes):
    classes = [c for c in classes if c]
    return max(classes, key=ORDER.get) if classes else None
