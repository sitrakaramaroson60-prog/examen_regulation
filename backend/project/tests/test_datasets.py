import io

from apps.datasets.models import DatasetSubmission
from apps.notifications.models import Notification
from apps.qos.models import QoSMeasurement

from .conftest import QOS_HEADER, csv_file, qos_csv
from .test_permissions import mk_dataset, upload


def test_valid_import_report_and_checksum(api, yas):
    ds = mk_dataset(api(yas))
    r = upload(api(yas), ds)
    assert r.status_code == 201, r.data
    assert r.data["row_count"] == 5 and len(r.data["checksum"]) == 64
    assert r.data["report"]["status"] == "VALID"
    assert upload(api(yas), ds).data["version_number"] == 2


def test_invalid_extension_and_content(api, yas):
    ds = mk_dataset(api(yas))
    exe = io.BytesIO(b"MZ\x90\x00binary")
    exe.name = "virus.exe"
    assert api(yas).post(f"/api/v1/datasets/{ds}/versions/", {"file": exe}, format="multipart").status_code == 400
    fake = io.BytesIO(b"not a zip at all")
    fake.name = "fake.xlsx"
    assert api(yas).post(f"/api/v1/datasets/{ds}/versions/", {"file": fake}, format="multipart").status_code == 400
    empty = io.BytesIO(b"")
    empty.name = "e.csv"
    assert api(yas).post(f"/api/v1/datasets/{ds}/versions/", {"file": empty}, format="multipart").status_code == 400


def test_missing_required_column(api, yas):
    ds = mk_dataset(api(yas))
    r = upload(api(yas), ds, "region,city\nAnalamanga,Antananarivo\n")
    assert r.status_code == 201
    assert r.data["report"]["status"] == "INVALID" and "metric_value" in r.data["report"]["missing_columns"]
    assert api(yas).post(f"/api/v1/datasets/versions/{r.data['id']}/submit/").status_code == 400


def test_duplicates_missing_values_and_type_errors(api, yas):
    ds = mk_dataset(api(yas))
    row = "Analamanga,Antananarivo,DATA,4G,download_speed,12,Mbps,speedtest-v1,2026-09-01T10:00:00Z\n"
    r = upload(api(yas), ds, QOS_HEADER + row + row)
    rep = r.data["report"]
    assert rep["duplicate_rows"] == 1 and rep["status"] == "VALID_WITH_WARNINGS"
    r2 = upload(api(yas), ds, qos_csv(3, bad=True))
    assert r2.data["report"]["status"] == "INVALID" and r2.data["report"]["type_errors"]["metric_value"] == 1


def test_json_and_xlsx_import(api, yas):
    import pandas as pd

    ds = mk_dataset(api(yas), "Format mix")
    df = pd.read_csv(io.StringIO(qos_csv(3)))
    js = io.BytesIO(df.to_json(orient="records").encode())
    js.name = "d.json"
    assert api(yas).post(f"/api/v1/datasets/{ds}/versions/", {"file": js}, format="multipart").data["report"]["status"] == "VALID"
    xb = io.BytesIO()
    df.to_excel(xb, index=False)
    xb.seek(0)
    xb.name = "d.xlsx"
    assert api(yas).post(f"/api/v1/datasets/{ds}/versions/", {"file": xb}, format="multipart").data["report"]["status"] == "VALID"


def test_full_review_workflow_and_ingestion(api, yas, regulator):
    ds = mk_dataset(api(yas))
    v = upload(api(yas), ds).data["id"]
    sub = api(yas).post(f"/api/v1/datasets/versions/{v}/submit/").data
    assert sub["status"] == "SUBMITTED" and sub["reference"].startswith("DS-")
    assert api(yas).post(f"/api/v1/datasets/versions/{v}/submit/").status_code == 400  # pas de double soumission
    assert Notification.objects.filter(recipient=regulator, notification_type="DATASET_SUBMITTED").exists()
    reg = api(regulator)
    sid = sub["id"]
    assert reg.post(f"/api/v1/submissions/{sid}/accept/").status_code == 400  # il faut examiner d'abord
    assert reg.post(f"/api/v1/submissions/{sid}/start-review/").data["status"] == "UNDER_REVIEW"
    assert reg.post(f"/api/v1/submissions/{sid}/request-correction/", {}, format="json").status_code == 400  # motif obligatoire
    r = reg.post(f"/api/v1/submissions/{sid}/request-correction/", {"comment": "Unités manquantes"}, format="json")
    assert r.data["status"] == "CORRECTION_REQUIRED"
    assert Notification.objects.filter(recipient=yas, notification_type="CORRECTION_REQUESTED").exists()
    assert QoSMeasurement.objects.count() == 0  # rien n'est intégré avant acceptation


def test_accept_ingests_validated_measurements(api, yas, regulator):
    ds = mk_dataset(api(yas))
    v = upload(api(yas), ds).data["id"]
    sid = api(yas).post(f"/api/v1/datasets/versions/{v}/submit/").data["id"]
    reg = api(regulator)
    reg.post(f"/api/v1/submissions/{sid}/start-review/")
    r = reg.post(f"/api/v1/submissions/{sid}/accept/", {"comment": "Conforme"}, format="json")
    assert r.data["status"] == "ACCEPTED" and [e["to_status"] for e in r.data["events"]][-1] == "ACCEPTED"
    assert QoSMeasurement.objects.filter(validation_status="VALIDATED", operator__code="YAS").count() == 5
    assert reg.get("/api/v1/qos/measurements/").data["count"] == 5
    assert reg.get("/api/v1/qos/measurements/summary/").data[0]["count"] == 5


def test_reject_requires_comment_and_is_final(api, yas, regulator):
    ds = mk_dataset(api(yas))
    v = upload(api(yas), ds).data["id"]
    sid = api(yas).post(f"/api/v1/datasets/versions/{v}/submit/").data["id"]
    reg = api(regulator)
    assert reg.post(f"/api/v1/submissions/{sid}/reject/", {}, format="json").status_code == 400
    assert reg.post(f"/api/v1/submissions/{sid}/reject/", {"comment": "Données incohérentes"}, format="json").data["status"] == "REJECTED"
    assert reg.post(f"/api/v1/submissions/{sid}/accept/").status_code == 400


def test_unsubmitted_dataset_invisible_to_regulator(api, yas, regulator):
    ds = mk_dataset(api(yas))
    upload(api(yas), ds)
    assert api(regulator).get("/api/v1/datasets/").data["count"] == 0
    assert api(regulator).get(f"/api/v1/datasets/{ds}/").status_code == 404


def test_unit_validation_in_qos(api, yas, regulator):
    ds = mk_dataset(api(yas))
    bad_unit = QOS_HEADER + "Analamanga,Antananarivo,DATA,4G,latency,12,Mbps,ping,2026-09-01T10:00:00Z\n"
    v = upload(api(yas), ds, bad_unit).data["id"]
    sid = api(yas).post(f"/api/v1/datasets/versions/{v}/submit/").data["id"]
    api(regulator).post(f"/api/v1/submissions/{sid}/start-review/")
    api(regulator).post(f"/api/v1/submissions/{sid}/accept/")
    assert QoSMeasurement.objects.count() == 0  # unité incompatible : ligne écartée


def test_summary_never_mixes_methods(api, yas, regulator):
    ds = mk_dataset(api(yas))
    txt = QOS_HEADER + "Analamanga,Antananarivo,DATA,4G,download_speed,10,Mbps,speedtest-v1,2026-09-01T10:00:00Z\n" + "Analamanga,Antananarivo,DATA,4G,download_speed,50,Mbps,drive-test,2026-09-01T11:00:00Z\n"
    v = upload(api(yas), ds, txt).data["id"]
    sid = api(yas).post(f"/api/v1/datasets/versions/{v}/submit/").data["id"]
    api(regulator).post(f"/api/v1/submissions/{sid}/start-review/")
    api(regulator).post(f"/api/v1/submissions/{sid}/accept/")
    rows = api(regulator).get("/api/v1/qos/measurements/summary/").data
    assert {r["measurement_method"] for r in rows} == {"speedtest-v1", "drive-test"} and len(rows) == 2


def test_thresholds_need_documented_origin(api, regulator, yas):
    body = {"metric_name": "download_speed", "unit": "Mbps", "good_threshold": 10, "poor_threshold": 2, "valid_from": "2026-01-01", "origin": ""}
    assert api(regulator).post("/api/v1/qos/thresholds/", body, format="json").status_code == 400
    body["origin"] = "Décision interne n°12 (exemple de test)"
    assert api(regulator).post("/api/v1/qos/thresholds/", body, format="json").status_code == 201
    assert api(yas).post("/api/v1/qos/thresholds/", body, format="json").status_code == 403
    assert api(yas).get("/api/v1/qos/thresholds/").status_code == 200
