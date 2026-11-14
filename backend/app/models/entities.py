import uuid
from datetime import datetime, timezone
from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.session import Base


def utcnow():
    return datetime.now(timezone.utc)


def new_id():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    astronaut_id: Mapped[str | None] = mapped_column(ForeignKey("astronaut_profiles.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Mission(Base):
    __tablename__ = "missions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    identifier: Mapped[str] = mapped_column(String(64), unique=True)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_days: Mapped[int] = mapped_column(Integer)
    astronauts = relationship("AstronautProfile", back_populates="mission")


class AstronautProfile(Base):
    __tablename__ = "astronaut_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("missions.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")  # ACTIVE | INACTIVE
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    baseline_info: Mapped[dict] = mapped_column(JSON, default=dict)
    mission = relationship("Mission", back_populates="astronauts")
    vitals = relationship("VitalReading", cascade="all, delete-orphan")
    devices = relationship("SensorDevice", cascade="all, delete-orphan")


class VitalReading(Base):
    __tablename__ = "vital_readings"
    __table_args__ = (Index("ix_vitals_astro_time", "astronaut_id", "timestamp"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # client UUID => idempotent
    astronaut_id: Mapped[str] = mapped_column(ForeignKey("astronaut_profiles.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    heart_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    spo2: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    resp_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    systolic: Mapped[float | None] = mapped_column(Float, nullable=True)
    diastolic: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(16))  # SENSOR | SYNTHETIC | CSV_IMPORT | MANUAL
    sensor_connected: Mapped[bool] = mapped_column(Boolean, default=True)
    risk_state: Mapped[str | None] = mapped_column(String(8), nullable=True)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WellnessRecord(Base):
    __tablename__ = "wellness_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    astronaut_id: Mapped[str] = mapped_column(ForeignKey("astronaut_profiles.id", ondelete="CASCADE"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mood: Mapped[int | None] = mapped_column(Integer, nullable=True)      # 1-5 self-report
    stress: Mapped[int | None] = mapped_column(Integer, nullable=True)    # 1-5
    fatigue: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 1-5
    sleep_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    activity_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class RadiationRecord(Base):
    __tablename__ = "radiation_records"
    __table_args__ = (Index("ix_rad_astro_time", "astronaut_id", "timestamp"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    astronaut_id: Mapped[str] = mapped_column(ForeignKey("astronaut_profiles.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dose: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))        # original unit preserved
    source: Mapped[str] = mapped_column(String(32))      # SENSOR | SYNTHETIC | NASA_OSDR ...
    exposure_event: Mapped[bool] = mapped_column(Boolean, default=False)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    astronaut_id: Mapped[str] = mapped_column(ForeignKey("astronaut_profiles.id", ondelete="CASCADE"), index=True)
    severity: Mapped[str] = mapped_column(String(8))
    category: Mapped[str] = mapped_column(String(24))
    parameter: Mapped[str] = mapped_column(String(32))
    explanation: Mapped[str] = mapped_column(Text)
    suggested_action: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(String(160), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(14), default="OPEN")  # OPEN | ACKNOWLEDGED | RESOLVED
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class SensorDevice(Base):
    __tablename__ = "sensor_devices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    astronaut_id: Mapped[str] = mapped_column(ForeignKey("astronaut_profiles.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    adapter: Mapped[str] = mapped_column(String(32), default="SIMULATED")  # SIMULATED | CSV | BLE (future)
    status: Mapped[str] = mapped_column(String(16), default="DISCONNECTED")
    last_measurement_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HealthBaseline(Base):
    __tablename__ = "health_baselines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    astronaut_id: Mapped[str] = mapped_column(ForeignKey("astronaut_profiles.id", ondelete="CASCADE"), index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    values: Mapped[dict] = mapped_column(JSON)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version: Mapped[str] = mapped_column(String(32), unique=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data_source: Mapped[str] = mapped_column(String(32))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    path: Mapped[str] = mapped_column(String(255))


class DataSyncRecord(Base):
    __tablename__ = "data_sync_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    accepted: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)


class SystemLog(Base):
    __tablename__ = "system_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
