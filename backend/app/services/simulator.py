"""Synthetic sensor simulator. All output is labelled source='SYNTHETIC'."""
import numpy as np
import pandas as pd
from app.core.rules import FEATURES

# Fictional demonstration identities only.
DEMO_ASTRONAUTS = [
    {"code": "AST-001", "display_name": "Cmdr. Nova Reyes (fictional)", "mission": "DEMO-M1",
     "base": {"heart_rate": 62, "spo2": 98, "temperature_c": 36.7, "resp_rate": 14, "systolic": 118, "diastolic": 76}},
    {"code": "AST-002", "display_name": "Dr. Kai Okafor (fictional)", "mission": "DEMO-M1",
     "base": {"heart_rate": 68, "spo2": 97, "temperature_c": 36.6, "resp_rate": 15, "systolic": 122, "diastolic": 79}},
    {"code": "AST-003", "display_name": "Eng. Mira Lindqvist (fictional)", "mission": "DEMO-M1",
     "base": {"heart_rate": 58, "spo2": 98, "temperature_c": 36.8, "resp_rate": 13, "systolic": 112, "diastolic": 72}},
]
NOISE = {"heart_rate": 2.5, "spo2": 0.4, "temperature_c": 0.12, "resp_rate": 0.8, "systolic": 3.0, "diastolic": 2.2}


def generate_vitals(base: dict, start="2026-01-01T00:00:00Z", n=1440, interval_min=5, seed=0,
                    drift=None, spikes=None, missing_prob=0.0, disconnects=None) -> pd.DataFrame:
    """Generate synthetic vitals.

    drift:  {"parameter": str, "start_index": int, "magnitude": float}  gradual linear change
    spikes: list of {"parameter": str, "index": int, "value": float}    sudden test abnormalities
    disconnects: list of (start_index, end_index) where sensor_connected=False and values are NaN
    """
    rng = np.random.default_rng(seed)
    ts = pd.date_range(start, periods=n, freq=f"{interval_min}min", tz="UTC")
    day_phase = 2 * np.pi * (ts.hour + ts.minute / 60) / 24
    df = pd.DataFrame({"timestamp": ts})
    for p in FEATURES:
        circ = {"heart_rate": 3.0, "temperature_c": 0.15}.get(p, 0.0) * np.sin(day_phase - np.pi / 2)
        df[p] = base[p] + circ + rng.normal(0, NOISE[p], n)
    df["spo2"] = df["spo2"].clip(upper=100)
    if drift:
        i0 = drift["start_index"]
        ramp = np.clip(np.arange(n) - i0, 0, None) / max(n - i0, 1)
        df[drift["parameter"]] += ramp * drift["magnitude"]
    for sp in spikes or []:
        df.loc[sp["index"], sp["parameter"]] = sp["value"]
    df["sensor_connected"] = True
    for a, b in disconnects or []:
        df.loc[a:b, FEATURES] = np.nan
        df.loc[a:b, "sensor_connected"] = False
    if missing_prob:
        mask = rng.random((n, len(FEATURES))) < missing_prob
        df[FEATURES] = df[FEATURES].mask(mask)
    df["source"] = "SYNTHETIC"
    return df


def generate_radiation(start="2026-01-01T00:00:00Z", days=30, seed=0, events=None) -> pd.DataFrame:
    """Synthetic daily dose records in the ORIGINAL unit (uGy/day). Clearly labelled synthetic."""
    rng = np.random.default_rng(seed)
    ts = pd.date_range(start, periods=days, freq="D", tz="UTC")
    dose = rng.normal(300, 25, days).clip(min=0)
    for e in events or []:
        dose[e["day"]] += e["extra"]
    return pd.DataFrame({"timestamp": ts, "dose": dose, "unit": "uGy/day", "source": "SYNTHETIC",
                         "exposure_event": [any(e["day"] == i for e in (events or [])) for i in range(days)]})
