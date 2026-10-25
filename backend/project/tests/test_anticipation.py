import math
from datetime import date, datetime, timezone as tz

import pytest

from apps.predictions.models import PredictionResult
from apps.qos.models import QoSThreshold

from .helpers import add_measurements

START = datetime(2026, 1, 7, 10, 0, tzinfo=tz.utc)  # un mercredi
WEEKS = 20
OPS = ["YAS", "AIRTEL", "ORANGE"]
TECHS = ["4G", "3G"]


def seed_measurements():
    """Qualité cyclique par groupe (phases différentes) : toutes les classes apparaissent dans l'historique."""
    i = 0
    for oi, op in enumerate(OPS):
        for ti, tech in enumerate(TECHS):
            phase = (oi * 2 + ti) * 1.7
            q = [0.5 + 0.45 * math.sin(2 * math.pi * (t + phase) / 10) for t in range(WEEKS)]
            kw = dict(operator=op, technology=tech, start=START, step_days=7)
            add_measurements(metric="download_speed", values=[45 * v for v in q], unit="Mbps", **kw)
            add_measurements(metric="latency", values=[200 - 160 * v for v in q], unit="ms", **kw)
            add_measurements(metric="availability", values=[95 + 4.9 * v for v in q], unit="%", **kw)
            add_measurements(metric="packet_loss", values=[6 - 5.5 * v for v in q], unit="%", **kw)
            i += 1


def seed_thresholds(user):
    rows = [("download_speed", "Mbps", 25, 10, True), ("latency", "ms", 80, 150, False), ("availability", "%", 98, 96, True), ("packet_loss", "%", 2, 4, False)]
    for m, u, g, p, better in rows:
        QoSThreshold.objects.create(metric_name=m, unit=u, good_threshold=g, poor_threshold=p, higher_is_better=better, valid_from=date(2025, 1, 1),
                                    origin="Seuil de test (non officiel)", created_by=user)


def build(api, regulator, **extra):
    return api(regulator).post("/api/v1/predictions/training-sets/build/", {"granularity": "week", **extra}, format="json")


def test_build_without_measurements_is_explicit(api, regulator):
    r = build(api, regulator)
    assert r.status_code == 400 and "mesure" in str(r.data).lower()


def test_build_without_thresholds_is_explicit(api, regulator):
    seed_measurements()
    r = build(api, regulator)
    assert r.status_code == 400 and "seuil" in str(r.data).lower()


def test_full_anticipation_pipeline_with_explanations(api, regulator):
    seed_measurements()
    seed_thresholds(regulator)
    b = build(api, regulator, risk_type="GENERAL_QUALITY")
    assert b.status_code == 201, b.data
    assert b.data["rows"] > 100 and set(b.data["class_counts"]) == {"GOOD", "MEDIUM", "POOR"}
    m = api(regulator).post("/api/v1/predictions/models/train/", {"name": "risque-qos", "training_dataset_version": b.data["dataset_version"]}, format="json")
    assert m.status_code == 201 and m.data["status"] == "READY", m.data
    assert m.data["risk_type"] == "GENERAL_QUALITY"
    assert "temporel" in m.data["metrics"]["split"].lower()
    imp = m.data["metrics"]["feature_importance"]
    assert imp and abs(sum(x["weight"] for x in imp) - 1) < 0.01 and "label" in imp[0]
    f = api(regulator).post("/api/v1/predictions/forecast/", {"model_version": m.data["id"]}, format="json")
    assert f.status_code == 201 and f.data["status"] == "COMPLETED", f.data
    assert f.data["summary"]["n_predicted"] == len(OPS) * len(TECHS)  # une prévision par zone (opérateur × région × technologie)
    res = api(regulator).get(f"/api/v1/predictions/runs/{f.data['id']}/results/").data["results"]
    assert len(res) == 6
    for r in res:
        assert r["area"]["operator"] in OPS and r["area"]["technology"] in TECHS
        assert r["predicted_class"] in ("GOOD", "MEDIUM", "POOR") and r["risk_label"].startswith("Risque")
        assert 0 < r["confidence"] <= 1 and isinstance(r["needs_review"], bool)
        assert abs(r["probability_good"] + r["probability_medium"] + r["probability_poor"] - 1) < 1e-6
        assert len(r["top_factors"]) == 3 and {"label", "value", "contribution", "effect"} <= set(r["top_factors"][0])
    assert PredictionResult.objects.count() == 6


def test_forecast_reproducible(api, regulator):
    seed_measurements()
    seed_thresholds(regulator)
    ds = build(api, regulator).data["dataset_version"]
    m = api(regulator).post("/api/v1/predictions/models/train/", {"name": "m", "training_dataset_version": ds}, format="json").data
    ids = [api(regulator).post("/api/v1/predictions/forecast/", {"model_version": m["id"]}, format="json").data["id"] for _ in range(2)]
    a, b = [list(PredictionResult.objects.filter(prediction_run_id=i).order_by("observation_reference").values_list("observation_reference", "predicted_class", "probability_poor")) for i in ids]
    assert a == b


def test_risk_types_use_targeted_metrics(api, regulator):
    seed_measurements()
    seed_thresholds(regulator)
    types = {t["risk_type"] for t in api(regulator).get("/api/v1/predictions/risk-types/").data}
    assert {"CONGESTION", "THROUGHPUT_DEGRADATION", "AVAILABILITY_DROP", "THRESHOLD_BREACH"} <= types
    cong = api(regulator).get("/api/v1/predictions/risk-types/").data
    assert "indirect" in next(t for t in cong if t["risk_type"] == "CONGESTION")["note"].lower()
    for rt in ("THROUGHPUT_DEGRADATION", "AVAILABILITY_DROP", "CONGESTION"):
        r = build(api, regulator, risk_type=rt, name=f"set-{rt}")
        assert r.status_code == 201 and r.data["meta"]["risk_type"] == rt, r.data


def test_not_ready_with_short_history(api, regulator):
    add_measurements("YAS", "download_speed", [30, 12, 5], unit="Mbps", start=START, step_days=7)
    seed_thresholds(regulator)
    b = build(api, regulator)
    assert b.status_code == 201
    m = api(regulator).post("/api/v1/predictions/models/train/", {"name": "court", "training_dataset_version": b.data["dataset_version"]}, format="json").data
    assert m["status"] == "NOT_READY"
    f = api(regulator).post("/api/v1/predictions/forecast/", {"model_version": m["id"]}, format="json")
    assert f.status_code == 400


def test_publisher_and_operator_cannot_forecast(api, publisher, yas):
    for u in (publisher, yas):
        assert api(u).post("/api/v1/predictions/training-sets/build/", {}, format="json").status_code == 403
        assert api(u).post("/api/v1/predictions/forecast/", {"model_version": 1}, format="json").status_code == 403
