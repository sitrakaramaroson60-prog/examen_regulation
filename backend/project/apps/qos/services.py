import pandas as pd
from django.db import transaction
from django.db.models import Avg, Count

from apps.organizations.models import City, Region

from .models import QoSMeasurement
from .rules import normalize, validate_metric


@transaction.atomic
def ingest_from_version(version, validated=True):
    """Insère les lignes d'une version de type QOS_MEASUREMENT acceptée. Les lignes incohérentes sont écartées et comptées."""
    dataset = version.dataset
    if dataset.data_type != "QOS_MEASUREMENT" or version.measurements.exists():
        return {"inserted": 0, "skipped": 0}
    from apps.datasets.services import load_dataframe

    df = load_dataframe(version)
    regions = {r.name.lower(): r for r in Region.objects.all()}
    cities = {(c.region_id, c.name.lower()): c for c in City.objects.all()}
    objs, skipped = [], 0
    df["metric_value"] = pd.to_numeric(df["metric_value"], errors="coerce")
    df["measured_at"] = pd.to_datetime(df["measured_at"], errors="coerce", utc=True, format="mixed")
    for row in df.to_dict("records"):
        region = regions.get(str(row.get("region", "")).strip().lower())
        city = cities.get((region.pk, str(row.get("city", "")).strip().lower())) if region else None
        value, ts = row.get("metric_value"), row.get("measured_at")
        if region is None or city is None or pd.isna(value) or pd.isna(ts):
            skipped += 1
            continue
        if validate_metric(str(row["metric_name"]).strip(), float(value), str(row["unit"]).strip()):
            skipped += 1
            continue
        norm_value, norm_unit = normalize(str(row["metric_name"]).strip(), float(value), str(row["unit"]).strip())
        objs.append(
            QoSMeasurement(
                operator=dataset.owner_organization, region=region, city=city, service_type=str(row["service_type"]).strip(),
                technology=str(row["technology"]).strip(), metric_name=str(row["metric_name"]).strip(), metric_value=norm_value,
                unit=norm_unit, measurement_method=str(row["measurement_method"]).strip(),
                source_type=dataset.source_type, measured_at=ts.to_pydatetime(), dataset_version=version,
                validation_status=QoSMeasurement.ValidationStatus.VALIDATED if validated else QoSMeasurement.ValidationStatus.PENDING,
            )
        )
    QoSMeasurement.objects.bulk_create(objs, batch_size=2000)
    announce_measurements(dataset.owner_organization_id)
    return {"inserted": len(objs), "skipped": skipped}


def summarize(queryset):
    """Agrégation par (opérateur, indicateur, unité, méthode, technologie, source).

    La méthode de mesure et la source font partie de la clé de regroupement : des mesures issues de
    protocoles ou de sources différentes ne sont jamais fusionnées dans une même moyenne.
    """
    rows = (
        queryset.values("operator__code", "metric_name", "unit", "measurement_method", "technology", "source_type")
        .annotate(average=Avg("metric_value"), n=Count("id"))
        .order_by("metric_name", "operator__code")
    )
    return [
        {
            "operator": r["operator__code"], "metric_name": r["metric_name"], "unit": r["unit"], "measurement_method": r["measurement_method"],
            "technology": r["technology"], "source_type": r["source_type"], "average": round(r["average"], 3), "count": r["n"],
        }
        for r in rows
    ]


def announce_measurements(operator_id):
    """Nouvelles mesures : l'ARTEC Régulation, l'opérateur concerné et — si le baromètre est publié — le public."""
    from apps.realtime.bus import PUBLIC, org, publish, role

    from .models import PublicBarometerSetting

    audiences = [role("ARTEC_REGULATOR"), org(operator_id)]
    if PublicBarometerSetting.current().enabled:
        audiences.append(PUBLIC)
    publish("qos", audiences, action="created")
