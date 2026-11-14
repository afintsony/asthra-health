from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import can_access_astronaut, current_user
from app.database.session import get_db
from app.ml.anomaly import analyze_reading
from app.models.entities import Alert, User, VitalReading
from app.schemas.schemas import ReadingIn
from app.services.baseline import compute_baseline
from app.services.pipeline import get_detector, history_df
from app.services.risk import assess

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/analyze")
def analyze(body: ReadingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Stateless analysis: nothing is stored and no alerts are created."""
    can_access_astronaut(user, body.astronaut_id)
    hist = history_df(db, body.astronaut_id)
    base = compute_baseline(hist)
    reading = {**body.model_dump(exclude={"client_uuid", "astronaut_id", "source"}),
               "timestamp": body.timestamp.isoformat()}
    a = analyze_reading(reading, base, get_detector(), recent_df=hist.tail(12))
    det = get_detector()
    return {"analysis": a, "risk": assess(a), "model_version": det.meta["version"] if det else None}


@router.get("/anomalies/{astronaut_id}")
def anomalies(astronaut_id: str, limit: int = 50, user: User = Depends(current_user), db: Session = Depends(get_db)):
    can_access_astronaut(user, astronaut_id)
    rows = db.execute(select(VitalReading).where(VitalReading.astronaut_id == astronaut_id,
                                                 VitalReading.risk_state.in_(["AMBER", "RED"]))
                      .order_by(VitalReading.timestamp.desc()).limit(min(limit, 500))).scalars().all()
    return {"items": [{"timestamp": r.timestamp, "risk_state": r.risk_state, "source": r.source,
                       "reason": (r.analysis or {}).get("detection_reason"),
                       "suggested_review_action": (r.analysis or {}).get("suggested_review_action")} for r in rows]}


@router.get("/baseline/{astronaut_id}")
def baseline(astronaut_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    can_access_astronaut(user, astronaut_id)
    return {"baseline": compute_baseline(history_df(db, astronaut_id)),
            "note": "Individual baseline from this astronaut's history; not a clinical reference range."}
