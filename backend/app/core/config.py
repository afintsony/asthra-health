import os
from functools import lru_cache


class Settings:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./astrahealth.db")
        # Render/Heroku style URLs
        if self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql+psycopg2://", 1)
        self.jwt_secret = os.getenv("JWT_SECRET_KEY", "")
        self.access_minutes = int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))
        self.refresh_days = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))
        self.cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
        self.nasa_api_key = os.getenv("NASA_API_KEY", "")
        self.model_dir = os.getenv("MODEL_DIR", "../models")
        self.env = os.getenv("APP_ENV", "development")
        if not self.jwt_secret:
            if self.env == "production":
                raise RuntimeError("JWT_SECRET_KEY must be set in production")
            self.jwt_secret = "dev-only-insecure-secret-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
