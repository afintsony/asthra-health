from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import can_access_astronaut, current_user
from app.core.rules import FEATURES, UNITS
from app.database.session import get_db
from app.models.entities import AstronautProfile, User, VitalReading
from app.schemas.schemas import ReadingIn
from app.services.pipeline import ingest

router = APIRouter(prefix="/api/health", tags=["health"])


def _row(r: VitalReading):
    return {"id": r.id, "timestamp": r.timestamp, "source": r.source, "sensor_connected": r.sensor_connected,
            "risk_state": r.risk_state, "units": UNITS, **{p: getattr(r, p) for p in FEATURES}}


@router.post("/readings", status_code=201)
def post_reading(body: ReadingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role == "MISSION_CONTROL":
        raise HTTPException(403, "Mission control is read-only")
    can_access_astronaut(user, body.astronaut_id)
    if not db.get(AstronautProfile, body.astronaut_id):
        raise HTTPException(404, "Astronaut not found")
    return ingest(db, body)


@router.get("/{astronaut_id}")
def latest(astronaut_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    can_access_astronaut(user, astronaut_id)
    r = db.execute(select(VitalReading).where(VitalReading.astronaut_id == astronaut_id)
                   .order_by(VitalReading.timestamp.desc()).limit(1)).scalar_one_or_none()
    return _row(r) if r else {"detail": "No readings yet", "empty": True}


@router.get("/{astronaut_id}/history")
def history(astronaut_id: str, start: datetime | None = None, end: datetime | None = None,
            source: str | None = None, limit: int = Query(500, le=5000), offset: int = 0,
            user: User = Depends(current_user), db: Session = Depends(get_db)):
    can_access_astronaut(user, astronaut_id)
    q = select(VitalReading).where(VitalReading.astronaut_id == astronaut_id)
    if start: q = q.where(VitalReading.timestamp >= start)
    if end: q = q.where(VitalReading.timestamp <= end)
    if source: q = q.where(VitalReading.source == source)
    rows = db.execute(q.order_by(VitalReading.timestamp.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [_row(r) for r in rows], "limit": limit, "offset": offset}
