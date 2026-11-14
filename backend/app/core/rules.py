"""Configured safety rules and plausibility limits.

IMPORTANT: These values are PROTOTYPE CONFIGURATION for demonstration only.
They are NOT medically validated clinical thresholds. They are meant to be
reviewed and overridden by a medical officer via configuration.
"""
from copy import deepcopy

FEATURES = ["heart_rate", "spo2", "temperature_c", "resp_rate", "systolic", "diastolic"]

UNITS = {
    "heart_rate": "bpm", "spo2": "%", "temperature_c": "°C",
    "resp_rate": "breaths/min", "systolic": "mmHg", "diastolic": "mmHg",
}

# Physically plausible measurement range: outside => invalid sensor value.
PLAUSIBLE = {
    "heart_rate": (20, 250), "spo2": (50, 100), "temperature_c": (30, 45),
    "resp_rate": (3, 60), "systolic": (50, 260), "diastolic": (30, 160),
}

# (low, high) bounds. Outside "amber" => AMBER, outside "red" => RED.
DEFAULT_RULES = {
    "heart_rate":    {"amber": (50, 120),  "red": (40, 140)},
    "spo2":          {"amber": (94, 100),  "red": (90, 100)},
    "temperature_c": {"amber": (35.5, 38.0), "red": (35.0, 39.0)},
    "resp_rate":     {"amber": (10, 24),   "red": (8, 30)},
    "systolic":      {"amber": (90, 150),  "red": (80, 180)},
    "diastolic":     {"amber": (50, 95),   "red": (40, 120)},
}

DEFAULT_RISK_CONFIG = {
    "z_threshold": 3.0,            # individual-baseline deviation (std units)
    "trend_drift_z": 2.0,          # moving-average drift vs baseline (std units)
    "trend_window": 12,            # readings in the moving average
    "consecutive_amber_to_red": 5, # repeated abnormal readings escalate
    "min_data_quality": 0.67,      # fraction of expected parameters valid
    "alert_cooldown_minutes": 30,
}


def get_rules(overrides=None):
    rules = deepcopy(DEFAULT_RULES)
    for k, v in (overrides or {}).items():
        if k in rules:
            rules[k].update(v)
    return rules


def evaluate_rules(reading: dict, rules=None):
    """Return list of rule hits for valid numeric values in `reading`."""
    rules = rules or DEFAULT_RULES
    hits = []
    for p, r in rules.items():
        v = reading.get(p)
        if v is None:
            continue
        for sev in ("red", "amber"):
            lo, hi = r[sev]
            if v < lo or v > hi:
                hits.append({
                    "parameter": p, "severity": sev.upper(), "value": v,
                    "unit": UNITS[p], "basis": "configured_rule",
                    "rule": f"{p} outside configured {sev} range [{lo}, {hi}] {UNITS[p]}",
                })
                break
    return hits
