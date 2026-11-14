from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import can_access_astronaut, current_user
from app.core.rules import FEATURES, UNITS
from app.database.session import get_db
from app.models.entities import Alert, AstronautProfile, RadiationRecord, User, VitalReading, WellnessRecord
from app.services.report_pdf import build_csv, build_pdf

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _collect(db, astronaut_id, days):
    a = db.get(AstronautProfile, astronaut_id)
    if not a:
        raise HTTPException(404, "Not found")
    start = datetime.now(timezone.utc) - timedelta(days=days)
    vit = db.execute(select(VitalReading).where(VitalReading.astronaut_id == astronaut_id)).scalars().all()
    vit = [v for v in vit if (v.timestamp if v.timestamp.tzinfo else v.timestamp.replace(tzinfo=timezone.utc)) >= start] or vit
    return a, vit


@router.get("/{astronaut_id}")
def report_json(astronaut_id: str, days: int = Query(30, ge=1, le=365), user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    can_access_astronaut(user, astronaut_id)
    a, vit = _collect(db, astronaut_id, days)
    summary = {}
    for p in FEATURES:
        vals = [getattr(v, p) for v in vit if getattr(v, p) is not None]
        if vals:
            summary[p] = {"mean": sum(vals) / len(vals), "min": min(vals), "max": max(vals), "unit": UNITS[p], "n": len(vals)}
    alerts = db.execute(select(Alert).where(Alert.astronaut_id == astronaut_id)
                        .order_by(Alert.timestamp.desc()).limit(100)).scalars().all()
    return {"astronaut_code": a.code, "synthetic": a.is_synthetic, "vitals_summary": summary,
            "alerts": [f"{x.timestamp:%Y-%m-%d %H:%M} {x.severity} {x.parameter}: {x.explanation} [{x.status}]" for x in alerts],
            "readings": len(vit)}


@router.get("/{astronaut_id}/export")
def export(astronaut_id: str, format: str = Query("pdf", pattern="^(pdf|csv)$"), days: int = Query(30, ge=1, le=365),
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    can_access_astronaut(user, astronaut_id)
    a, vit = _collect(db, astronaut_id, days)
    if format == "csv":
        rows = [{"timestamp": v.timestamp.isoformat(), "parameter": p, "value": getattr(v, p), "unit": UNITS[p],
                 "source": v.source} for v in vit for p in FEATURES if getattr(v, p) is not None]
        return Response(build_csv(rows), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{a.code}_vitals.csv"'})
    summary = report_json(astronaut_id, days, user, db)
    rad = db.execute(select(RadiationRecord).where(RadiationRecord.astronaut_id == astronaut_id)
                     .order_by(RadiationRecord.timestamp)).scalars().all()
    wel = db.execute(select(WellnessRecord).where(WellnessRecord.astronaut_id == astronaut_id)).scalars().all()
    wellness = {}
    if user.role != "MISSION_CONTROL" and wel:  # wellness data is private
        for k in ("mood", "stress", "fatigue", "sleep_hours", "sleep_quality"):
            vals = [getattr(w, k) for w in wel if getattr(w, k) is not None]
            if vals:
                wellness[f"avg_{k}"] = round(sum(vals) / len(vals), 2)
    notes = []
    if any(v.source != "SENSOR" for v in vit):
        notes.append("Includes non-sensor data sources: " + ", ".join(sorted({v.source for v in vit})))
    notes += [f"{sum(1 for v in vit if not v.sensor_connected)} readings recorded with sensor disconnected"]
    anomalies = [f"{v.timestamp:%Y-%m-%d %H:%M} {v.risk_state}: {(v.analysis or {}).get('detection_reason')}"
                 for v in vit if v.risk_state in ("AMBER", "RED")][:40]
    pdf = build_pdf({"astronaut_code": a.code, "mission": a.mission.identifier if a.mission else "-",
                     "period": f"last {days} days", "vitals_summary": summary["vitals_summary"], "wellness": wellness,
                     "radiation": [{"timestamp": r.timestamp, "dose": r.dose, "unit": r.unit, "source": r.source} for r in rad],
                     "anomalies": anomalies, "alerts": summary["alerts"][:40], "data_quality_notes": notes,
                     "synthetic": a.is_synthetic or any(v.source == "SYNTHETIC" for v in vit)})
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{a.code}_report.pdf"'})
