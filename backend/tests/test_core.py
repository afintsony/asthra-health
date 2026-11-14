import uuid
import numpy as np
import pandas as pd
from app.core.rules import FEATURES, evaluate_rules
from app.services.validation import validate_reading
from app.services.baseline import compute_baseline
from app.services.simulator import generate_vitals, generate_radiation, DEMO_ASTRONAUTS
from app.ml.anomaly import AnomalyDetector, analyze_reading
from app.services.risk import assess
from app.services.alerts_logic import build_alerts, filter_duplicates
from app.services.csv_import import parse, preview
from app.services.sync_logic import apply_sync
from app.services.radiation import cumulative, convert
from app.services.report_pdf import build_pdf, build_csv

BASE = DEMO_ASTRONAUTS[0]["base"]


def _hist():
    return generate_vitals(BASE, n=1440, seed=1)


def test_validation_flags_missing_and_implausible():
    clean, issues, q = validate_reading({"heart_rate": 70, "spo2": 140, "temperature_c": None})
    assert clean["spo2"] is None and clean["heart_rate"] == 70
    kinds = {(i["parameter"], i["issue"]) for i in issues}
    assert ("spo2", "implausible") in kinds and ("temperature_c", "missing") in kinds
    assert q < 0.5


def test_baseline_values():
    b = compute_baseline(_hist())
    hr = b["heart_rate"]
    assert hr["sufficient"] and 55 < hr["mean"] < 70 and hr["std"] > 0
    assert hr["min"] < hr["median"] < hr["max"]
    assert abs(hr["trend_per_day"]) < 2


def test_rules_red_and_amber():
    assert evaluate_rules({"spo2": 85})[0]["severity"] == "RED"
    assert evaluate_rules({"heart_rate": 125})[0]["severity"] == "AMBER"
    assert evaluate_rules({"heart_rate": 70, "spo2": 98}) == []


def test_model_train_persist_load(tmp_path=None):
    import tempfile, os
    det = AnomalyDetector().fit(_hist())
    path = os.path.join(tempfile.mkdtemp(), "m.joblib")
    det.save(path)
    det2 = AnomalyDetector.load(path)
    r = {p: BASE[p] for p in FEATURES}
    assert det.score(r)["score"] == det2.score(r)["score"]
    assert det2.meta["version"].startswith("iforest-")


def _injected():
    test = generate_vitals(BASE, n=500, seed=7)
    idx = list(range(50, 500, 25))
    for i in idx:
        test.loc[i, "heart_rate"] += 45
        test.loc[i, "spo2"] -= 6
    labels = np.zeros(500, dtype=bool); labels[idx] = True
    return test, labels, idx


def test_ml_alone_tradeoff_synthetic():
    # Isolation Forest recall depends on `contamination` (threshold). At 5% it catches
    # all injected synthetic anomalies, at the cost of ~5% flagged on normal training data.
    det = AnomalyDetector(contamination=0.05).fit(_hist())
    test, labels, _ = _injected()
    ev = det.evaluate(test, labels)
    assert ev["recall"] >= 0.9 and ev["precision"] > 0.3, ev


def test_combined_pipeline_detects_injected_synthetic():
    # Production path: ML + baseline z-score + rules together, default contamination.
    hist = _hist(); b = compute_baseline(hist)
    det = AnomalyDetector().fit(hist)
    test, labels, idx = _injected()
    hits = sum(analyze_reading(test.loc[i, FEATURES].to_dict(), b, det)["anomaly_detected"] for i in idx)
    assert hits == len(idx)
    fp = sum(analyze_reading(test.loc[i, FEATURES].to_dict(), b, det)["anomaly_detected"]
             for i in range(0, 500) if not labels[i])
    assert fp / (500 - len(idx)) < 0.05, fp


def test_normal_reading_is_green():
    hist = _hist()
    b = compute_baseline(hist)
    det = AnomalyDetector().fit(hist)
    reading = {p: BASE[p] for p in FEATURES}
    a = analyze_reading(reading, b, det, recent_df=hist.tail(12))
    r = assess(a)
    assert r["state"] == "GREEN" and not a["anomaly_detected"], a["detection_reason"]


def test_gradual_drift_gives_amber_with_explanation():
    base_df = _hist()
    b = compute_baseline(base_df)
    det = AnomalyDetector().fit(base_df)
    drift = generate_vitals(BASE, n=300, seed=3, drift={"parameter": "heart_rate", "start_index": 0, "magnitude": 40})
    reading = drift.iloc[-1][FEATURES].to_dict()
    a = analyze_reading(reading, b, det, recent_df=drift.tail(12))
    r = assess(a)
    assert r["state"] in ("AMBER", "RED")
    assert any(f["parameter"] == "heart_rate" for f in a["findings"])
    assert "baseline" in a["detection_reason"] or "moving average" in a["detection_reason"]


def test_high_priority_rule_gives_red():
    hist = _hist(); b = compute_baseline(hist)
    reading = {**{p: BASE[p] for p in FEATURES}, "spo2": 86}
    a = analyze_reading(reading, b, None)
    r = assess(a)
    assert r["state"] == "RED" and "spo2" in r["reasons"][0]


def test_missing_data_not_green():
    hist = _hist(); b = compute_baseline(hist)
    a = analyze_reading({"sensor_connected": False}, b, None)
    r = assess(a)
    assert r["state"] is None and r["data_quality_warning"]
    partial = analyze_reading({"heart_rate": 62, "spo2": 98}, b, None)
    rp = assess(partial)
    assert rp["data_quality_warning"]


def test_repeated_amber_escalates():
    hist = _hist(); b = compute_baseline(hist)
    a = analyze_reading({**{p: BASE[p] for p in FEATURES}, "heart_rate": 122}, b, None)
    assert assess(a)["state"] == "AMBER"
    assert assess(a, recent_states=["AMBER"] * 4)["state"] == "RED"


def test_alert_dedupe():
    hist = _hist(); b = compute_baseline(hist)
    a = analyze_reading({**{p: BASE[p] for p in FEATURES}, "spo2": 86}, b, None)
    alerts = build_alerts("AST-001", a, assess(a))
    assert alerts
    first = filter_duplicates(alerts, [])
    again = filter_duplicates(alerts, first)
    assert len(first) > 0 and again == []


def test_csv_import():
    csv = b"time,hr,o2\n2026-01-01T00:00:00Z,70,98\nbad,70,98\n2026-01-01T00:05:00Z,400,98\n2026-01-01T00:10:00Z,,\n"
    res = parse(csv, {"timestamp": "time", "heart_rate": "hr", "spo2": "o2"})
    assert res["summary"]["imported"] == 2  # row 3 keeps valid spo2; row 5 has none -> rejected
    assert any(e["line"] == 3 for e in res["errors"])
    assert any(e["line"] == 4 for e in res["errors"])
    assert preview(csv)["total_rows"] == 4


def test_sync_idempotent():
    u = str(uuid.uuid4())
    res, acc = apply_sync([{"client_uuid": u}, {"client_uuid": "nope"}], set())
    assert [r["status"] for r in res] == ["accepted", "rejected"]
    res2, acc2 = apply_sync([{"client_uuid": u}], {u})
    assert res2[0]["status"] == "duplicate" and acc2 == []


def test_radiation_units():
    df = cumulative(generate_radiation(days=5, seed=1))
    assert df["cumulative_dose"].is_monotonic_increasing and (df["unit"] == "uGy/day").all()
    assert convert(2, "mGy", "uGy")[0] == 2000
    try:
        convert(1, "Gy", "Sv"); assert False
    except ValueError:
        pass


def test_pdf_and_csv_export():
    rep = {"astronaut_code": "AST-001", "mission": "DEMO-M1", "period": "2026-01-01 to 2026-01-30",
           "vitals_summary": {"heart_rate": {"mean": 62, "min": 50, "max": 90, "unit": "bpm"}},
           "wellness": {"mood": 4}, "radiation": [{"timestamp": "2026-01-01", "dose": 300, "unit": "uGy/day", "source": "SYNTHETIC"}],
           "anomalies": [], "alerts": [], "data_quality_notes": [], "synthetic": True}
    pdf = build_pdf(rep)
    assert pdf[:4] == b"%PDF" and len(pdf) > 1500
    c = build_csv([{"timestamp": "t", "parameter": "heart_rate", "value": 60, "unit": "bpm", "source": "SYNTHETIC"}])
    assert c.splitlines()[0] == "timestamp,parameter,value,unit,source"
