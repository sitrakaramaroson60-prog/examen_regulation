import io

import numpy as np
import pandas as pd

from apps.predictions.models import PredictionModel, PredictionResult
from apps.regulation.models import RegulatoryDecision

from .conftest import csv_file
from .test_permissions import mk_dataset


def labeled_csv(n_per_class=40, campaigns=8, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    centers = {"GOOD": (40, 20, 0.5), "MEDIUM": (20, 50, 2.0), "POOR": (5, 120, 6.0)}
    i = 0
    for cls, (d, lat, loss) in centers.items():
        for _ in range(n_per_class):
            rows.append({"observation_id": f"o{i}", "download": rng.normal(d, 3), "latency": rng.normal(lat, 5), "loss": abs(rng.normal(loss, 0.3)),
                         "quality_class": cls, "campaign_id": f"c{i % campaigns}"})
            i += 1
    return pd.DataFrame(rows).to_csv(index=False)


def mk_training(api, regulator, text, name="train"):
    ds = mk_dataset(api(regulator), name, "LABELED_TRAINING")
    r = api(regulator).post(f"/api/v1/datasets/{ds}/versions/", {"file": csv_file(text)}, format="multipart")
    assert r.status_code == 201 and r.data["report"]["status"] != "INVALID", r.data
    return r.data["id"]


def mk_input(api, regulator, name="inputs"):
    df = pd.read_csv(io.StringIO(labeled_csv(10, 5, seed=3))).drop(columns=["quality_class", "campaign_id"])
    ds = mk_dataset(api(regulator), name, "OTHER")
    return api(regulator).post(f"/api/v1/datasets/{ds}/versions/", {"file": csv_file(df.to_csv(index=False))}, format="multipart").data["id"]


def train(api, regulator, v, name="softmax"):
    return api(regulator).post("/api/v1/predictions/models/train/", {"name": name, "training_dataset_version": v}, format="json")


def test_insufficient_data_gives_explicit_not_ready(api, regulator):
    v = mk_training(api, regulator, labeled_csv(5, 8))
    r = train(api, regulator, v)
    assert r.status_code == 201 and r.data["status"] == "NOT_READY" and "insuffisant" in r.data["status_reason"].lower()


def test_too_few_campaigns_not_ready(api, regulator):
    r = train(api, regulator, mk_training(api, regulator, labeled_csv(40, 2)))
    assert r.data["status"] == "NOT_READY" and "campagnes" in r.data["status_reason"]


def test_training_metrics_and_no_leakage(api, regulator):
    r = train(api, regulator, mk_training(api, regulator, labeled_csv()))
    assert r.data["status"] == "READY", r.data
    m = r.data["metrics"]
    for key in ("accuracy", "precision", "recall", "f1", "confusion_matrix", "calibration", "macro_f1"):
        assert key in m
    assert np.array(m["confusion_matrix"]["matrix"]).shape == (3, 3)
    assert "expected_calibration_error" in m["calibration"]
    assert m["n_train"] + m["n_test"] == 120 and "GroupShuffleSplit" in m["split"]
    assert set(r.data["feature_schema"]) == {"download", "latency", "loss"}


def test_model_versioning_and_comparison(api, regulator):
    v = mk_training(api, regulator, labeled_csv())
    a, b = train(api, regulator, v).data, train(api, regulator, v).data
    assert (a["version"], b["version"]) == (1, 2)
    cmp = api(regulator).get(f"/api/v1/predictions/models/compare/?a={a['id']}&b={b['id']}")
    assert cmp.status_code == 200 and "delta_b_minus_a" in cmp.data


def test_refuses_run_with_unready_model(api, regulator):
    m = train(api, regulator, mk_training(api, regulator, labeled_csv(5, 8))).data
    inp = mk_input(api, regulator)
    r = api(regulator).post("/api/v1/predictions/runs/", {"model_version": m["id"], "input_dataset_version": inp}, format="json")
    assert r.status_code == 400


def test_run_stores_probabilities_and_traceability(api, regulator):
    m = train(api, regulator, mk_training(api, regulator, labeled_csv())).data
    inp = mk_input(api, regulator)
    r = api(regulator).post("/api/v1/predictions/runs/", {"model_version": m["id"], "input_dataset_version": inp}, format="json")
    assert r.status_code == 201 and r.data["status"] == "COMPLETED", r.data
    assert r.data["summary"]["model"]["version"] == 1 and r.data["summary"]["input_dataset_version"] == inp
    assert "certitudes" in r.data["summary"]["disclaimer"]
    results = PredictionResult.objects.filter(prediction_run_id=r.data["id"])
    assert results.count() == 30
    for res in results:
        assert abs(res.probability_good + res.probability_medium + res.probability_poor - 1) < 1e-6
        assert res.confidence == max(res.probability_good, res.probability_medium, res.probability_poor)
    page = api(regulator).get(f"/api/v1/predictions/runs/{r.data['id']}/results/")
    assert page.data["count"] == 30
    exp = api(regulator).get(f"/api/v1/predictions/runs/{r.data['id']}/export/")
    assert exp.status_code == 200 and b"probability_good" in exp.content


def test_reproducible_results(api, regulator):
    m = train(api, regulator, mk_training(api, regulator, labeled_csv())).data
    inp = mk_input(api, regulator)
    ids = [api(regulator).post("/api/v1/predictions/runs/", {"model_version": m["id"], "input_dataset_version": inp}, format="json").data["id"] for _ in range(2)]
    a, b = [list(PredictionResult.objects.filter(prediction_run_id=i).order_by("observation_reference").values_list("observation_reference", "predicted_class", "probability_good", "probability_poor")) for i in ids]
    assert a == b and len(a) == 30


def test_input_with_missing_feature_fails_cleanly(api, regulator):
    m = train(api, regulator, mk_training(api, regulator, labeled_csv())).data
    ds = mk_dataset(api(regulator), "bad-input", "OTHER")
    v = api(regulator).post(f"/api/v1/datasets/{ds}/versions/", {"file": csv_file("download,latency\n10,20\n")}, format="multipart").data["id"]
    r = api(regulator).post("/api/v1/predictions/runs/", {"model_version": m["id"], "input_dataset_version": v}, format="json")
    assert r.data["status"] == "FAILED" and "loss" in r.data["summary"]["error"]


def test_operator_dataset_not_accepted_cannot_be_analyzed(api, regulator, yas):
    m = train(api, regulator, mk_training(api, regulator, labeled_csv())).data
    ds = mk_dataset(api(yas), "yas-data", "OTHER")
    v = api(yas).post(f"/api/v1/datasets/{ds}/versions/", {"file": csv_file("download,latency,loss\n1,2,3\n")}, format="multipart").data["id"]
    r = api(regulator).post("/api/v1/predictions/runs/", {"model_version": m["id"], "input_dataset_version": v}, format="json")
    assert r.status_code == 400


def test_prediction_never_triggers_sanction(api, regulator, yas):
    m = train(api, regulator, mk_training(api, regulator, labeled_csv())).data
    api(regulator).post("/api/v1/predictions/runs/", {"model_version": m["id"], "input_dataset_version": mk_input(api, regulator)}, format="json")
    assert RegulatoryDecision.objects.count() == 0
    assert PredictionModel.objects.filter(status="READY").count() == 1


def test_operator_cannot_use_predictions(api, yas):
    assert api(yas).get("/api/v1/predictions/models/").status_code == 403
    assert api(yas).get("/api/v1/predictions/runs/").status_code == 403
