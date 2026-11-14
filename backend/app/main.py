import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.api import ai, astronauts, auth, health, records, reports
from app.core.config import get_settings
from app.database.session import Base, SessionLocal, engine
from app.models import entities  # noqa: F401  (register models)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("astrahealth")
settings = get_settings()

app = FastAPI(title="ASTRAHEALTH API", version="0.1.0",
              description="BITCOSMOS — Monitoring Life Beyond Earth. Research prototype / decision support only; "
                          "not clinically validated or medically certified.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                         "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"})
    return resp


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)  # no internals leaked


@app.on_event("startup")
def startup():
    # Dev convenience. For production use migrations (see documentation/KNOWN_LIMITATIONS.md).
    Base.metadata.create_all(engine)


@app.get("/api/health-check", tags=["system"])
def health_check():
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok"}


for r in (auth.router, astronauts.router, health.router, ai.router, records.wellness, records.radiation,
          records.alerts, records.devices, records.sync, reports.router):
    app.include_router(r)
