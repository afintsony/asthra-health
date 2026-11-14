from app.core.rules import FEATURES, PLAUSIBLE


def validate_reading(reading: dict):
    """Validate a vital-sign reading.

    Returns (clean, issues, quality). `clean` has None for missing/invalid
    values; `quality` is the fraction of expected parameters that are present
    and plausible. Missing/invalid data is NEVER treated as a normal value.
    """
    clean, issues = {}, []
    valid = 0
    for p in FEATURES:
        v = reading.get(p)
        if v is None or (isinstance(v, float) and v != v):
            clean[p] = None
            issues.append({"parameter": p, "issue": "missing"})
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            clean[p] = None
            issues.append({"parameter": p, "issue": "not_numeric"})
            continue
        lo, hi = PLAUSIBLE[p]
        if v < lo or v > hi:
            clean[p] = None
            issues.append({"parameter": p, "issue": "implausible", "value": v, "range": [lo, hi]})
            continue
        clean[p] = v
        valid += 1
    if reading.get("sensor_connected") is False:
        issues.append({"parameter": "sensor", "issue": "disconnected"})
    return clean, issues, valid / len(FEATURES)
