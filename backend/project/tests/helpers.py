from datetime import datetime, timedelta, timezone as dt_tz

from apps.organizations.models import City, Organization, Region
from apps.qos.models import QoSMeasurement


def add_measurements(operator, metric, values, unit="Mbps", method="speedtest-v1", source="TECHNICAL", technology="4G", region="Analamanga", start=None, step_days=1, service="DATA"):
    org = Organization.objects.get(code=operator)
    reg = Region.objects.get(name=region)
    city = reg.cities.first()
    start = start or datetime(2026, 9, 1, 10, 0, tzinfo=dt_tz.utc)
    objs = [
        QoSMeasurement(operator=org, region=reg, city=city, service_type=service, technology=technology, metric_name=metric, metric_value=v, unit=unit,
                       measurement_method=method, source_type=source, measured_at=start + timedelta(days=i * step_days), validation_status="VALIDATED")
        for i, v in enumerate(values)
    ]
    QoSMeasurement.objects.bulk_create(objs)
    return objs
