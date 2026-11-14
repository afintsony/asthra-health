"""API tests. REQUIRE fastapi, httpx, sqlalchemy, argon2-cffi installed (not run in the authoring sandbox)."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_astrahealth.db")
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import hash_password
from app.database.session import Base, SessionLocal, engine
from app.models.entities import AstronautProfile, User


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with SessionLocal() as db:
        a = AstronautProfile(code="T-1", display_name="Test (fictional)"); b = AstronautProfile(code="T-2", display_name="Other")
        db.add_all([a, b]); db.flush()
        for n, r, aid in [("admin", "ADMIN", None), ("medic", "MEDICAL_OFFICER", None), ("ctrl", "MISSION_CONTROL", None),
                          ("astro", "ASTRONAUT", a.id)]:
            db.add(User(username=n, password_hash=hash_password("pw-pw-pw-pw-1"), role=r, astronaut_id=aid))
        db.commit()
        ids = (a.id, b.id)
    with TestClient(app) as c:
        c.ids = ids
        yield c


def tok(c, u):
    r = c.post("/api/auth/login", json={"username": u, "password": "pw-pw-pw-pw-1"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def reading(aid, **kw):
    return {"client_uuid": str(uuid.uuid4()), "astronaut_id": aid, "timestamp": "2026-01-01T00:00:00Z",
            "heart_rate": 62, "spo2": 98, "temperature_c": 36.7, "resp_rate": 14, "systolic": 118, "diastolic": 76,
            "source": "SYNTHETIC", **kw}


def test_login_bad_password(client):
    assert client.post("/api/auth/login", json={"username": "admin", "password": "x"}).status_code == 401


def test_requires_auth(client):
    assert client.get("/api/astronauts").status_code == 401


def test_roles(client):
    a, b = client.ids
    assert client.post("/api/astronauts", headers=tok(client, "medic"),
                       json={"code": "X-9", "display_name": "x"}).status_code == 403
    assert client.get(f"/api/health/{b}", headers=tok(client, "astro")).status_code == 403  # other astronaut
    assert client.post("/api/health/readings", headers=tok(client, "ctrl"), json=reading(a)).status_code == 403
    assert client.get(f"/api/wellness/{a}", headers=tok(client, "ctrl")).status_code == 403  # private


def test_reading_red_alert_and_dedupe(client):
    a, _ = client.ids
    h = tok(client, "medic")
    r = client.post("/api/health/readings", headers=h, json=reading(a, spo2=85))
    assert r.status_code == 201 and r.json()["risk"]["state"] == "RED"
    r2 = client.post("/api/health/readings", headers=h, json=reading(a, spo2=85))
    assert r2.json()["alerts_created"] == 0  # duplicate suppression
    alerts = client.get("/api/alerts", headers=h).json()["items"]
    assert len(alerts) >= 1
    aid = alerts[0]["id"]
    assert client.put(f"/api/alerts/{aid}/acknowledge", headers=h).json()["status"] == "ACKNOWLEDGED"
    assert client.put(f"/api/alerts/{aid}/resolve", headers=h).json()["status"] == "RESOLVED"


def test_sync_idempotent(client):
    a, _ = client.ids
    h = tok(client, "astro")
    item = reading(a)
    r1 = client.post("/api/sync", headers=h, json={"readings": [item]}).json()
    r2 = client.post("/api/sync", headers=h, json={"readings": [item]}).json()
    assert r1["accepted"] == 1 and r2["duplicates"] == 1


def test_wellness_and_radiation_and_pdf(client):
    a, _ = client.ids
    h = tok(client, "astro")
    assert client.post("/api/wellness", headers=h, json={"astronaut_id": a, "timestamp": "2026-01-01T00:00:00Z", "mood": 4}).status_code == 201
    assert client.post("/api/radiation", headers=h, json={"astronaut_id": a, "timestamp": "2026-01-01T00:00:00Z",
                                                          "dose": 300, "unit": "uGy/day", "source": "SYNTHETIC"}).status_code == 201
    pdf = client.get(f"/api/reports/{a}/export?format=pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
