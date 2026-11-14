"""Wellness, radiation, alerts, devices, sync."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import audit, can_access_astronaut, current_user, require_roles
from app.database.session import get_db
from app.models.entities import (Alert, AstronautProfile, DataSyncRecord, RadiationRecord, SensorDevice, User,
                                 VitalReading, WellnessRecord)
from app.schemas.schemas import DeviceIn, DeviceStatusIn, RadiationIn, SyncIn, WellnessIn
from app.services.pipeline import ingest
from app.services.radiation import cumulative

import pandas as pd

wellness = APIRouter(prefix="/api/wellness", tags=["wellness"])
radiation = APIRouter(prefix="/api/radiation", tags=["radiation"])
alerts = APIRouter(prefix="/api/alerts", tags=["alerts"])
devices = APIRouter(prefix="/api/devices", tags=["devices"])
sync = APIRouter(prefix="/api/sync", tags=["sync"])


# ---------------- wellness (private: astronaut + medical officer + admin) ----------------
@wellness.post("", status_code=201)
def add_wellness(body: WellnessIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    can_access_astronaut(user, body.astronaut_id, private=True)
    rec = WellnessRecord(**body.model_dump())
    db.add(rec); db.commit()
    return {"id": rec.id}


@wellness.get("/{astronaut_id}")
def get_wellness(astronaut_id: str, limit: int = Query(200, le=1000), offset: int = 0,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    can_access_astronaut(user, astronaut_id, private=True)
    rows = db.execute(select(WellnessRecord).where(WellnessRecord.astronaut_id == astronaut_id)
                      .order_by(WellnessRecord.timestamp.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in rows],
            "note": "Self-reported wellness indicators; not a psychiatric assessment."}


# ---------------- radiation ----------------
@radiation.post("", status_code=201)
def add_radiation(body: RadiationIn, user: User = Depends(require_roles("ASTRONAUT", "MEDICAL_OFFICER", "ADMIN")),
                  db: Session = Depends(get_db)):
    can_access_astronaut(user, body.astronaut_id)
    rec = RadiationRecord(**body.model_dump())
    db.add(rec); db.commit()
    return {"id": rec.id}


@radiation.get("/{astronaut_id}")
def get_radiation(astronaut_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    can_access_astronaut(user, astronaut_id)
    rows = db.execute(select(RadiationRecord).where(RadiationRecord.astronaut_id == astronaut_id)
                      .order_by(RadiationRecord.timestamp)).scalars().all()
    if not rows:
        return {"items": [], "empty": True}
    df = cumulative(pd.DataFrame([{"timestamp": r.timestamp, "dose": r.dose, "unit": r.unit, "source": r.source,
                                   "exposure_event": r.exposure_event} for r in rows]))
    return {"items": df.to_dict("records"),
            "note": "Original units preserved; cumulative totals are per unit. No medical limit is applied."}


# ---------------- alerts ----------------
@alerts.get("")
def list_alerts(astronaut_id: str | None = None, status: str | None = None, severity: str | None = None,
                limit: int = Query(100, le=500), offset: int = 0,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Alert)
    if user.role == "ASTRONAUT":
        astronaut_id = user.astronaut_id
    if astronaut_id: q = q.where(Alert.astronaut_id == astronaut_id)
    if status: q = q.where(Alert.status == status)
    if severity: q = q.where(Alert.severity == severity)
    rows = db.execute(q.order_by(Alert.timestamp.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [{c.name: getattr(a, c.name) for c in a.__table__.columns} for a in rows]}


@alerts.post("", status_code=201)
def manual_alert(body: dict, user: User = Depends(require_roles("MEDICAL_OFFICER", "ADMIN")),
                 db: Session = Depends(get_db)):
    try:
        a = Alert(astronaut_id=body["astronaut_id"], severity=body["severity"], category="MANUAL",
                  parameter=body.get("parameter", "manual"), explanation=body["explanation"],
                  suggested_action=body.get("suggested_action", "Review"),
                  dedupe_key=f"manual|{datetime.now(timezone.utc).isoformat()}")
    except KeyError as e:
        raise HTTPException(422, f"Missing field {e}")
    if a.severity not in ("AMBER", "RED"):
        raise HTTPException(422, "severity must be AMBER or RED")
    db.add(a); db.commit()
    return {"id": a.id}


def _get_alert(db, user, alert_id):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "Not found")
    can_access_astronaut(user, a.astronaut_id)
    return a


@alerts.put("/{alert_id}/acknowledge")
def ack(alert_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _get_alert(db, user, alert_id)
    if a.status == "OPEN":
        a.status, a.acknowledged_by, a.acknowledged_at = "ACKNOWLEDGED", user.username, datetime.now(timezone.utc)
        db.commit(); audit(db, user.id, "alert_ack", alert_id)
    return {"id": a.id, "status": a.status}


@alerts.put("/{alert_id}/resolve")
def resolve(alert_id: str, user: User = Depends(require_roles("MEDICAL_OFFICER", "ADMIN")),
            db: Session = Depends(get_db)):
    a = _get_alert(db, user, alert_id)
    a.status, a.resolved_at = "RESOLVED", datetime.now(timezone.utc)
    db.commit(); audit(db, user.id, "alert_resolve", alert_id)
    return {"id": a.id, "status": a.status}


# ---------------- devices ----------------
@devices.get("")
def list_devices(user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(SensorDevice)
    if user.role == "ASTRONAUT":
        q = q.where(SensorDevice.astronaut_id == user.astronaut_id)
    return {"items": [{c.name: getattr(d, c.name) for c in d.__table__.columns}
                      for d in db.execute(q).scalars()]}


@devices.post("", status_code=201)
def add_device(body: DeviceIn, admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    d = SensorDevice(**body.model_dump())
    db.add(d); db.commit()
    return {"id": d.id}


@devices.put("/{device_id}/status")
def set_status(device_id: str, body: DeviceStatusIn, user: User = Depends(require_roles("MEDICAL_OFFICER", "ADMIN")),
               db: Session = Depends(get_db)):
    d = db.get(SensorDevice, device_id)
    if not d:
        raise HTTPException(404, "Not found")
    d.status = body.status; db.commit()
    return {"id": d.id, "status": d.status}


# ---------------- sync ----------------
@sync.post("")
def do_sync(body: SyncIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Idempotent: each reading carries a client UUID. Rejected items stay queued on the client."""
    if user.role == "MISSION_CONTROL":
        raise HTTPException(403, "Mission control is read-only")
    results, acc, dup, rej = [], 0, 0, 0
    for r in body.readings:
        try:
            can_access_astronaut(user, r.astronaut_id)
            if not db.get(AstronautProfile, r.astronaut_id):
                raise HTTPException(404, "Astronaut not found")
            out = ingest(db, r)
            results.append({"client_uuid": r.client_uuid, "status": out["status"]})
            acc += out["status"] == "accepted"; dup += out["status"] == "duplicate"
        except HTTPException as e:
            rej += 1
            results.append({"client_uuid": r.client_uuid, "status": "rejected", "reason": e.detail})
    db.add(DataSyncRecord(user_id=user.id, accepted=acc, duplicates=dup, rejected=rej)); db.commit()
    return {"accepted": acc, "duplicates": dup, "rejected": rej, "results": results,
            "synced_at": datetime.now(timezone.utc)}


@sync.get("/status")
def sync_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    last = db.execute(select(DataSyncRecord).where(DataSyncRecord.user_id == user.id)
                      .order_by(DataSyncRecord.synced_at.desc()).limit(1)).scalar_one_or_none()
    return {"last_synced_at": last.synced_at if last else None,
            "last_result": {"accepted": last.accepted, "duplicates": last.duplicates,
                            "rejected": last.rejected} if last else None, "server_time": datetime.now(timezone.utc)}
