"""Train + persist the anomaly model on SYNTHETIC data, and (if DB deps are installed) seed demo data.

Usage (from backend/):  python scripts_train_and_seed.py [--no-db]
"""
import os, sys, uuid
sys.path.insert(0, ".")
import pandas as pd
from app.core.rules import FEATURES
from app.ml.anomaly import AnomalyDetector
from app.services.simulator import DEMO_ASTRONAUTS, generate_vitals, generate_radiation

MODEL_DIR = os.getenv("MODEL_DIR", "../models")
os.makedirs(MODEL_DIR, exist_ok=True)

frames = [generate_vitals(a["base"], n=1440, seed=i) for i, a in enumerate(DEMO_ASTRONAUTS)]
det = AnomalyDetector().fit(pd.concat(frames, ignore_index=True), data_source="SYNTHETIC")
det.save(os.path.join(MODEL_DIR, "anomaly_detector.joblib"))
print("Saved model", det.meta["version"], "trained on", det.meta["n_samples"], "SYNTHETIC rows")
for i, f in enumerate(frames):
    f.to_csv(f"../data/synthetic/{DEMO_ASTRONAUTS[i]['code']}_vitals.csv", index=False)
if "--no-db" in sys.argv:
    sys.exit(0)

from app.core.security import hash_password
from app.database.session import Base, SessionLocal, engine
from app.models.entities import *  # noqa
Base.metadata.create_all(engine)
with SessionLocal() as db:
    m = Mission(identifier="DEMO-M1", start_date=pd.Timestamp("2026-01-01", tz="UTC").to_pydatetime(), duration_days=180)
    db.add(m); db.flush()
    users = [("admin", "ADMIN", None), ("medic", "MEDICAL_OFFICER", None), ("control", "MISSION_CONTROL", None)]
    for i, a in enumerate(DEMO_ASTRONAUTS):
        p = AstronautProfile(code=a["code"], display_name=a["display_name"], mission_id=m.id, is_synthetic=True)
        db.add(p); db.flush()
        db.add(SensorDevice(astronaut_id=p.id, name=f"SIM-{a['code']}", adapter="SIMULATED", status="CONNECTED"))
        if i == 0:
            users.append(("astro1", "ASTRONAUT", p.id))
        rad = generate_radiation(seed=i, events=[{"day": 12, "extra": 400}])
        for r in rad.itertuples():
            db.add(RadiationRecord(astronaut_id=p.id, timestamp=r.timestamp.to_pydatetime(), dose=float(r.dose),
                                   unit=r.unit, source="SYNTHETIC", exposure_event=bool(r.exposure_event)))
        for r in frames[i].iloc[::12].itertuples():  # hourly readings
            db.add(VitalReading(id=str(uuid.uuid4()), astronaut_id=p.id, timestamp=r.timestamp.to_pydatetime(),
                                source="SYNTHETIC", sensor_connected=bool(r.sensor_connected),
                                **{k: (None if pd.isna(getattr(r, k)) else float(getattr(r, k))) for k in FEATURES}))
    pw = os.getenv("DEMO_PASSWORD") or "ChangeMe-Demo-2026!"
    for name, role, aid in users:
        db.add(User(username=name, password_hash=hash_password(pw), role=role, astronaut_id=aid))
    db.commit()
print("Seeded demo data. Demo users: admin, medic, control, astro1 (password from DEMO_PASSWORD or the default in this script).")
