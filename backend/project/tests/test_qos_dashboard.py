from datetime import date

from apps.qos.models import QoSThreshold
from apps.qos.rules import normalize
from apps.qos.thresholds import classify, find_threshold

from .helpers import add_measurements

URL = "/api/v1/qos/measurements/dashboard/?date_from=2026-08-01&date_to=2026-12-31"


def mk_threshold(user, metric="download_speed", good=20, poor=5, better=True, unit="Mbps", tech=""):
    return QoSThreshold.objects.create(metric_name=metric, unit=unit, good_threshold=good, poor_threshold=poor, higher_is_better=better, technology=tech,
                                       valid_from=date(2026, 1, 1), origin="Décision de test", created_by=user)


def test_dashboard_compares_operators_with_threshold_status(api, regulator):
    add_measurements("YAS", "download_speed", [30, 32, 28])
    add_measurements("AIRTEL", "download_speed", [3, 4, 5])
    add_measurements("ORANGE", "download_speed", [10, 12])
    mk_threshold(regulator)
    d = api(regulator).get(URL).data
    dl = next(i for i in d["indicators"] if i["metric"] == "download_speed")
    assert d["operators"] == ["AIRTEL", "ORANGE", "YAS"] or set(d["operators"]) == {"YAS", "AIRTEL", "ORANGE"}
    g = dl["groups"][0]
    status = {o["operator"]: o["status"] for o in g["operators"]}
    assert status == {"YAS": "GOOD", "AIRTEL": "POOR", "ORANGE": "MEDIUM"} and g["comparable"] is True
    assert dl["threshold"]["origin"] == "Décision de test"
    assert g["trend"][0]["month"] == "2026-09"


def test_dashboard_without_threshold_says_not_configured(api, regulator):
    add_measurements("YAS", "latency", [40, 50], unit="ms")
    d = api(regulator).get(URL).data
    lat = next(i for i in d["indicators"] if i["metric"] == "latency")
    assert lat["threshold"] is None and all(o["status"] is None for o in lat["groups"][0]["operators"])
    assert any("seuil" in n.lower() for n in d["notes"])


def test_methods_and_units_are_never_mixed(api, regulator):
    add_measurements("YAS", "download_speed", [10, 10], method="speedtest-v1")
    add_measurements("YAS", "download_speed", [100, 100], method="drive-test")
    groups = next(i for i in api(regulator).get(URL).data["indicators"] if i["metric"] == "download_speed")["groups"]
    assert {g["method"] for g in groups} == {"speedtest-v1", "drive-test"}
    assert all(g["comparable"] is False for g in groups)  # un seul opérateur : pas de comparaison


def test_default_excludes_declared_and_survey_sources(api, regulator):
    add_measurements("YAS", "availability", [99.9, 99.8], unit="%", source="TECHNICAL")
    add_measurements("YAS", "availability", [100, 100], unit="%", source="DECLARED", method="declaration")
    d = api(regulator).get(URL).data
    av = next(i for i in d["indicators"] if i["metric"] == "availability")
    assert len(av["groups"]) == 1 and av["groups"][0]["method"] == "speedtest-v1"
    cov = next(c for c in d["coverage"] if c["operator"] == "YAS")
    assert cov["TECHNICAL"] == 2 and cov["DECLARED"] == 2


def test_declared_vs_measured_gap(api, regulator):
    add_measurements("YAS", "availability", [98, 98], unit="%", source="TECHNICAL", method="supervision")
    add_measurements("YAS", "availability", [100, 100], unit="%", source="DECLARED", method="supervision")
    cross = api(regulator).get(URL).data["declared_vs_measured"]
    assert cross[0]["declared"] == 100 and cross[0]["measured"] == 98 and cross[0]["gap"] == 2


def test_operator_sees_only_itself(api, yas, regulator):
    add_measurements("YAS", "latency", [30], unit="ms")
    add_measurements("AIRTEL", "latency", [60], unit="ms")
    d = api(yas).get(URL).data
    assert d["operators"] == ["YAS"]
    lat = next(i for i in d["indicators"] if i["metric"] == "latency")
    assert [o["operator"] for o in lat["groups"][0]["operators"]] == ["YAS"]
    assert all(c["operator"] == "YAS" for c in d["coverage"])


def test_dashboard_forbidden_for_publisher(api, publisher):
    assert api(publisher).get(URL).status_code == 403


def test_threshold_classification_and_specificity(regulator):
    t = mk_threshold(regulator, "latency", good=50, poor=150, better=False, unit="ms")
    assert [classify(v, t) for v in (30, 100, 200)] == ["GOOD", "MEDIUM", "POOR"]
    generic = mk_threshold(regulator, "download_speed", 20, 5)
    specific = mk_threshold(regulator, "download_speed", 50, 10, tech="5G")
    assert find_threshold("download_speed", "5G", "DATA", date(2026, 9, 1)) == specific
    assert find_threshold("download_speed", "4G", "DATA", date(2026, 9, 1)) == generic
    assert find_threshold("download_speed", "4G", "DATA", date(2025, 1, 1)) is None


def test_kbps_normalized():
    assert normalize("download_speed", 5000, "kbps") == (5.0, "Mbps")


def test_catalog_lists_required_indicators(api, regulator):
    keys = {m["metric"] for m in api(regulator).get("/api/v1/qos/measurements/metrics/").data}
    assert {"availability", "download_speed", "upload_speed", "latency", "jitter", "packet_loss", "call_success_rate", "connection_success_rate", "call_failure_rate", "drop_rate"} <= keys


def test_public_barometer_disabled_by_default(anon):
    d = anon.get("/api/v1/qos/public/").data
    assert d["enabled"] is False and d["indicators"] == [] and "ARTEC" in d["message"]
    assert set(d["participation"]) == {"open_surveys", "responses", "publications"}


def test_public_barometer_when_enabled_requires_minimum_volume(anon, settings, regulator):
    settings.QOS_PUBLIC_ENABLED = True
    settings.QOS_PUBLIC_MIN_MEASUREMENTS = 5
    from django.utils import timezone

    start = timezone.now() - timezone.timedelta(days=20)
    add_measurements("YAS", "download_speed", [30] * 6, start=start)
    add_measurements("AIRTEL", "download_speed", [10] * 2, start=start)   # sous le minimum : non publié
    add_measurements("ORANGE", "download_speed", [20] * 6, start=start, source="DECLARED", method="decl")  # déclaré : jamais publié
    d = anon.get("/api/v1/qos/public/").data
    ops = d["indicators"][0]["operators"]
    assert [o["operator"] for o in ops] == ["YAS"]
