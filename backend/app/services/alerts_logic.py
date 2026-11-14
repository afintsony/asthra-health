"""Alert construction and duplicate suppression."""
from datetime import datetime, timedelta, timezone
from app.core.rules import DEFAULT_RISK_CONFIG

CATEGORY = {"configured_rule": "VITAL_RULE", "individual_baseline": "BASELINE_DEVIATION",
            "ml_model": "ANOMALY_MODEL", "trend": "TREND"}


def build_alerts(astronaut_id: str, analysis: dict, risk: dict) -> list:
    alerts = []
    ts = analysis["timestamp"]
    for f in analysis["findings"]:
        sev = f["severity"]
        alerts.append({
            "astronaut_id": astronaut_id, "severity": sev, "category": CATEGORY[f["basis"]],
            "parameter": f["parameter"], "explanation": f["rule"],
            "suggested_action": risk["suggested_action"], "timestamp": ts,
            "dedupe_key": f"{astronaut_id}|{f['parameter']}|{CATEGORY[f['basis']]}|{sev}",
        })
    if risk.get("data_quality_warning"):
        alerts.append({
            "astronaut_id": astronaut_id, "severity": "AMBER", "category": "DATA_QUALITY",
            "parameter": "data_quality", "timestamp": ts,
            "explanation": "Missing, implausible or disconnected-sensor data: " +
                           ", ".join(f"{i['parameter']}:{i['issue']}" for i in analysis["data_quality"]["issues"]),
            "suggested_action": "Check sensor connection; do not treat missing data as normal.",
            "dedupe_key": f"{astronaut_id}|data_quality|DATA_QUALITY|AMBER",
        })
    return alerts


def filter_duplicates(new_alerts: list, open_alerts: list, now=None, cooldown_minutes=None):
    """Drop alerts whose dedupe_key matches an unresolved alert within the cooldown.

    `open_alerts`: dicts with dedupe_key, timestamp (ISO str or datetime), resolved (bool).
    """
    cooldown = timedelta(minutes=cooldown_minutes or DEFAULT_RISK_CONFIG["alert_cooldown_minutes"])
    now = now or datetime.now(timezone.utc)
    last = {}
    for a in open_alerts:
        if a.get("resolved"):
            continue
        t = a["timestamp"]
        t = datetime.fromisoformat(t) if isinstance(t, str) else t
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        last[a["dedupe_key"]] = max(t, last.get(a["dedupe_key"], t))
    out, seen = [], set()
    for a in new_alerts:
        k = a["dedupe_key"]
        if k in seen or (k in last and now - last[k] < cooldown):
            continue
        seen.add(k)
        out.append(a)
    return out
