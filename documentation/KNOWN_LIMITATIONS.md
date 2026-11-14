# Known limitations
- API layer not executed yet; expect small integration fixes on first run.
- No Alembic migrations; `create_all` at startup is for development only. Generate with `alembic init` + `alembic revision --autogenerate` before production.
- In-memory rate limiter is per-process; use a shared store when running multiple instances.
- Detector is trained globally on synthetic data; per-astronaut models/baselines are future work.
- Frontend / PWA / offline queue / demo UI / NASA OSDR integration not implemented.
- Free hosting tiers (Render/Vercel) sleep when idle and Render free Postgres expires; do not rely on them for persistence.
