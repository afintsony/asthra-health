"""Ingestion pipeline: validate -> store -> baseline -> analysis -> risk -> alerts."""
import os
from datetime import datetime, timezone
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.rules import FEATURES
from app.ml.anomaly import AnomalyDetector, analyze_reading
from app.models.entities import Alert, AstronautProfile, SensorDevice, VitalReading
from app.services.alerts_logic import build_alerts, filter_duplicates
from app.services.baseline import compute_baseline
from app.services.risk import assess

_detector = {"obj": None, "loaded": False}


def get_detector():
    if not _detector["loaded"]:
        path = os.path.join(get_settings().model_dir, "anomaly_detector.joblib")
        _detector["obj"] = AnomalyDetector.load(path) if os.path.exists(path) else None
        _detector["loaded"] = True
    return _detector["obj"]


def history_df(db: Session, astronaut_id: str, limit=3000) -> pd.DataFrame:
    rows = db.execute(select(VitalReading).where(VitalReading.astronaut_id == astronaut_id)
                      .order_by(VitalReading.timestamp.desc()).limit(limit)).scalars().all()
    df = pd.DataFrame([{"timestamp": r.timestamp, **{p: getattr(r, p) for p in FEATURES}} for r in reversed(rows)])
    return df if len(df) else pd.DataFrame(columns=["timestamp", *FEATURES])


def ingest(db: Session, r) -> dict:
    """Idempotent on client UUID. Never labels data with a different source than supplied."""
    if db.get(VitalReading, r.client_uuid):
        return {"status": "duplicate", "client_uuid": r.client_uuid}
    astro = db.get(AstronautProfile, r.astronaut_id)
    reading = {p: getattr(r, p) for p in FEATURES}
    reading.update(timestamp=r.timestamp.isoformat(), sensor_connected=r.sensor_connected)

    hist = history_df(db, r.astronaut_id)
    baseline = compute_baseline(hist)  # computed BEFORE adding this reading
    analysis = analyze_reading(reading, baseline, get_detector(), recent_df=hist.tail(12))
    prev = db.execute(select(VitalReading.risk_state).where(VitalReading.astronaut_id == r.astronaut_id)
                      .order_by(VitalReading.timestamp.desc()).limit(10)).scalars().all()
    risk = assess(analysis, recent_states=list(reversed(prev)))

    ts = r.timestamp if r.timestamp.tzinfo else r.timestamp.replace(tzinfo=timezone.utc)
    db.add(VitalReading(id=r.client_uuid, astronaut_id=r.astronaut_id, timestamp=ts, source=r.source,
                        sensor_connected=r.sensor_connected, risk_state=risk["state"], analysis=analysis,
                        **{p: analysis["measurements"].get(p) for p in FEATURES}))
    open_alerts = [{"dedupe_key": a.dedupe_key, "timestamp": a.timestamp, "resolved": a.status == "RESOLVED"}
                   for a in db.execute(select(Alert).where(Alert.astronaut_id == r.astronaut_id,
                                                           Alert.status != "RESOLVED")).scalars()]
    new_alerts = filter_duplicates(build_alerts(r.astronaut_id, analysis, risk), open_alerts,
                                   now=ts)
    for a in new_alerts:
        db.add(Alert(astronaut_id=r.astronaut_id, severity=a["severity"], category=a["category"],
                     parameter=a["parameter"], explanation=a["explanation"],
                     suggested_action=a["suggested_action"], dedupe_key=a["dedupe_key"], timestamp=ts,
                     is_synthetic=(r.source == "SYNTHETIC")))
    for dev in db.execute(select(SensorDevice).where(SensorDevice.astronaut_id == r.astronaut_id)).scalars():
        if r.sensor_connected:
            dev.last_measurement_at = ts
    db.commit()
    return {"status": "accepted", "client_uuid": r.client_uuid, "risk": risk, "analysis": analysis,
            "alerts_created": len(new_alerts)}
