from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

Source = Literal["SENSOR", "SYNTHETIC", "CSV_IMPORT", "MANUAL"]


class LoginIn(BaseModel):
    username: str
    password: str


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=128)
    role: Literal["ASTRONAUT", "MEDICAL_OFFICER", "MISSION_CONTROL", "ADMIN"]
    astronaut_id: Optional[str] = None


class RefreshIn(BaseModel):
    refresh_token: str


class AstronautIn(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    display_name: str
    mission_identifier: Optional[str] = None
    mission_start: Optional[datetime] = None
    mission_duration_days: Optional[int] = Field(default=None, gt=0)
    baseline_info: dict = {}
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"
    is_synthetic: bool = True


class ReadingIn(BaseModel):
    client_uuid: str
    astronaut_id: str
    timestamp: datetime
    heart_rate: Optional[float] = None
    spo2: Optional[float] = None
    temperature_c: Optional[float] = None
    resp_rate: Optional[float] = None
    systolic: Optional[float] = None
    diastolic: Optional[float] = None
    source: Source
    sensor_connected: bool = True


class WellnessIn(BaseModel):
    astronaut_id: str
    timestamp: datetime
    mood: Optional[int] = Field(default=None, ge=1, le=5)
    stress: Optional[int] = Field(default=None, ge=1, le=5)
    fatigue: Optional[int] = Field(default=None, ge=1, le=5)
    sleep_hours: Optional[float] = Field(default=None, ge=0, le=24)
    sleep_quality: Optional[int] = Field(default=None, ge=1, le=5)
    activity_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    notes: Optional[str] = Field(default=None, max_length=1000)


class RadiationIn(BaseModel):
    astronaut_id: str
    timestamp: datetime
    dose: float = Field(ge=0)
    unit: str = Field(min_length=1, max_length=16)
    source: str
    exposure_event: bool = False


class DeviceIn(BaseModel):
    astronaut_id: str
    name: str
    adapter: Literal["SIMULATED", "CSV", "BLE"] = "SIMULATED"


class DeviceStatusIn(BaseModel):
    status: Literal["CONNECTED", "DISCONNECTED", "ERROR"]


class SyncIn(BaseModel):
    readings: list[ReadingIn] = []
