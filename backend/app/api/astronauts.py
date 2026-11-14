from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import audit, can_access_astronaut, current_user, require_roles
from app.database.session import get_db
from app.models.entities import AstronautProfile, Mission, User
from app.schemas.schemas import AstronautIn

router = APIRouter(prefix="/api/astronauts", tags=["astronauts"])


def _out(a: AstronautProfile):
    m = a.mission
    return {"id": a.id, "code": a.code, "display_name": a.display_name, "status": a.status,
            "is_synthetic": a.is_synthetic, "baseline_info": a.baseline_info,
            "mission_identifier": m.identifier if m else None,
            "mission_start": m.start_date if m else None, "mission_duration_days": m.duration_days if m else None}


def _mission(db, body: AstronautIn):
    if not body.mission_identifier:
        return None
    m = db.execute(select(Mission).where(Mission.identifier == body.mission_identifier)).scalar_one_or_none()
    if not m:
        if not (body.mission_start and body.mission_duration_days):
            raise HTTPException(422, "New mission requires mission_start and mission_duration_days")
        m = Mission(identifier=body.mission_identifier, start_date=body.mission_start,
                    duration_days=body.mission_duration_days)
        db.add(m); db.flush()
    return m


@router.get("")
def list_astronauts(limit: int = Query(50, le=200), offset: int = 0, status: str | None = None,
                    search: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(AstronautProfile)
    if user.role == "ASTRONAUT":
        q = q.where(AstronautProfile.id == user.astronaut_id)
    if status:
        q = q.where(AstronautProfile.status == status)
    if search:
        q = q.where(AstronautProfile.code.ilike(f"%{search}%") | AstronautProfile.display_name.ilike(f"%{search}%"))
    rows = db.execute(q.order_by(AstronautProfile.code).limit(limit).offset(offset)).scalars().all()
    return {"items": [_out(a) for a in rows], "limit": limit, "offset": offset}


@router.post("", status_code=201)
def create(body: AstronautIn, admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    if db.execute(select(AstronautProfile).where(AstronautProfile.code == body.code)).scalar_one_or_none():
        raise HTTPException(409, "Astronaut code already exists")
    m = _mission(db, body)
    a = AstronautProfile(code=body.code, display_name=body.display_name, mission_id=m.id if m else None,
                         baseline_info=body.baseline_info, status=body.status, is_synthetic=body.is_synthetic)
    db.add(a); db.commit()
    audit(db, admin.id, "astronaut_created", a.code)
    return _out(a)


@router.get("/{astronaut_id}")
def get_one(astronaut_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    can_access_astronaut(user, astronaut_id)
    a = db.get(AstronautProfile, astronaut_id)
    if not a:
        raise HTTPException(404, "Not found")
    return _out(a)


@router.put("/{astronaut_id}")
def update(astronaut_id: str, body: AstronautIn, admin: User = Depends(require_roles("ADMIN")),
           db: Session = Depends(get_db)):
    a = db.get(AstronautProfile, astronaut_id)
    if not a:
        raise HTTPException(404, "Not found")
    m = _mission(db, body)
    a.display_name, a.status, a.baseline_info = body.display_name, body.status, body.baseline_info
    a.is_synthetic = body.is_synthetic
    a.mission_id = m.id if m else a.mission_id
    db.commit()
    audit(db, admin.id, "astronaut_updated", a.code)
    return _out(a)
