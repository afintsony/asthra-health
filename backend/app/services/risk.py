"""Risk assessment: combines rules, baseline deviation, ML, trend, data quality."""
from app.core.rules import DEFAULT_RISK_CONFIG

ACTIONS = {
    "GREEN": "Normal monitoring status. Continue routine monitoring.",
    "AMBER": "Review recommended: medical officer should review flagged parameters.",
    "RED": "High-priority review required: contact the medical officer promptly per crew protocol.",
}


def assess(analysis: dict, recent_states=None, env=None, config=None) -> dict:
    cfg = {**DEFAULT_RISK_CONFIG, **(config or {})}
    findings = analysis["findings"]
    dq = analysis["data_quality"]
    dq_warning = dq["score"] < cfg["min_data_quality"] or any(
        i["issue"] in ("disconnected", "implausible") for i in dq["issues"])

    reasons = []
    if not analysis["measurements"]:
        # No valid data at all: do NOT report GREEN.
        return {"state": None, "data_quality_warning": True,
                "reasons": ["No valid measurements; status cannot be assessed."],
                "suggested_action": "Check sensor connection and data source.",
                "disclaimer": "Decision support only; not a medical diagnosis."}

    state = "GREEN"
    if any(f["severity"] == "RED" for f in findings):
        state = "RED"
        reasons += [f["rule"] for f in findings if f["severity"] == "RED"]
    elif findings:
        state = "AMBER"
        reasons += [f["rule"] for f in findings]

    # Repeated abnormal readings escalate AMBER -> RED (configurable).
    recent = list(recent_states or [])
    if state == "AMBER":
        n = 0
        for s in reversed(recent):
            if s in ("AMBER", "RED"):
                n += 1
            else:
                break
        if n + 1 >= cfg["consecutive_amber_to_red"]:
            state = "RED"
            reasons.append(f"{n + 1} consecutive abnormal assessments (escalation threshold "
                           f"{cfg['consecutive_amber_to_red']})")

    context = []
    if env and env.get("radiation_event"):
        context.append("Recent radiation exposure event recorded (context only; no inferred cause).")

    return {"state": state, "data_quality_warning": dq_warning, "reasons": reasons or ["No deviations."],
            "context": context, "suggested_action": ACTIONS[state],
            "disclaimer": "Decision support only; not a medical diagnosis."}
