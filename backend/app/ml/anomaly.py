"""Anomaly detection: Isolation Forest + statistical + moving-average trend.

Anomaly scores are NOT probabilities of disease. They indicate how unusual a
reading is relative to the training data / the individual's baseline.
"""
import hashlib
import json
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.core.rules import FEATURES, DEFAULT_RISK_CONFIG, evaluate_rules
from app.services.baseline import z_score
from app.services.validation import validate_reading

SCORE_DISCLAIMER = ("Anomaly score measures statistical unusualness versus training data; "
                    "it is not a probability of disease.")


class AnomalyDetector:
    def __init__(self, contamination=0.02, n_estimators=200, random_state=42):
        self.params = {"contamination": contamination, "n_estimators": n_estimators,
                       "random_state": random_state}
        self.model = None
        self.scaler = None
        self.medians = None
        self.meta = {}

    # ---- training -------------------------------------------------------
    def _prep(self, df: pd.DataFrame, fit=False):
        X = df[FEATURES].apply(pd.to_numeric, errors="coerce")
        if fit:
            self.medians = X.median().fillna(0.0).to_dict()
        X = X.fillna(self.medians)  # missing-value handling: train-median imputation
        return X

    def fit(self, df: pd.DataFrame, data_source="SYNTHETIC"):
        X = self._prep(df.dropna(subset=FEATURES, how="all"), fit=True)
        self.scaler = StandardScaler().fit(X)
        self.model = IsolationForest(**self.params).fit(self.scaler.transform(X))
        trained_at = datetime.now(timezone.utc).isoformat()
        digest = hashlib.sha1(json.dumps([self.params, len(X), trained_at]).encode()).hexdigest()[:8]
        flagged = float((self.model.predict(self.scaler.transform(X)) == -1).mean())
        self.meta = {"version": f"iforest-{digest}", "trained_at": trained_at,
                     "n_samples": int(len(X)), "features": FEATURES, "params": self.params,
                     "data_source": data_source, "train_flagged_fraction": flagged}
        return self

    # ---- inference ------------------------------------------------------
    def score(self, reading: dict) -> dict:
        row = pd.DataFrame([{p: reading.get(p) for p in FEATURES}])
        Xs = self.scaler.transform(self._prep(row))
        raw = float(-self.model.decision_function(Xs)[0])  # higher = more unusual
        return {"score": raw, "is_anomaly": bool(raw > 0), "model_version": self.meta["version"]}

    def evaluate(self, df: pd.DataFrame, labels) -> dict:
        """Performance against SYNTHETIC injected labels only (not clinical)."""
        Xs = self.scaler.transform(self._prep(df))
        pred = self.model.predict(Xs) == -1
        y = np.asarray(labels, dtype=bool)
        tp, fp, fn = int((pred & y).sum()), int((pred & ~y).sum()), int((~pred & y).sum())
        return {"precision": tp / (tp + fp) if tp + fp else 0.0,
                "recall": tp / (tp + fn) if tp + fn else 0.0, "tp": tp, "fp": fp, "fn": fn,
                "note": "Evaluated on synthetic injected anomalies; not clinical performance."}

    # ---- persistence ----------------------------------------------------
    def save(self, path):
        joblib.dump({"model": self.model, "scaler": self.scaler, "medians": self.medians,
                     "meta": self.meta, "params": self.params}, path)

    @classmethod
    def load(cls, path):
        d = joblib.load(path)
        obj = cls(**d["params"])
        obj.model, obj.scaler, obj.medians, obj.meta = d["model"], d["scaler"], d["medians"], d["meta"]
        return obj


def analyze_reading(reading, baseline, detector=None, recent_df=None, rules=None, config=None):
    """Full explainable analysis of one reading. Returns a dict (see keys below)."""
    cfg = {**DEFAULT_RISK_CONFIG, **(config or {})}
    clean, issues, quality = validate_reading(reading)
    valid = {p: v for p, v in clean.items() if v is not None}

    findings = evaluate_rules(valid, rules)  # configured rules (basis=configured_rule)

    baseline_dev = []
    for p, v in valid.items():
        b = baseline.get(p, {})
        if b.get("sufficient"):
            z = z_score(v, b)
            baseline_dev.append({"parameter": p, "value": v, "baseline_mean": b["mean"],
                                 "z": round(z, 2), "basis": "individual_baseline",
                                 "flagged": abs(z) > cfg["z_threshold"]})
    for d in baseline_dev:
        if d["flagged"]:
            findings.append({"parameter": d["parameter"], "severity": "AMBER", "value": d["value"],
                             "basis": "individual_baseline",
                             "rule": f"{d['parameter']} is {d['z']:+.1f} std from this astronaut's own baseline "
                                     f"(mean {d['baseline_mean']:.1f})"})

    trend = []
    if recent_df is not None and len(recent_df) >= cfg["trend_window"]:
        for p in FEATURES:
            b = baseline.get(p, {})
            if not b.get("sufficient") or p not in recent_df:
                continue
            ma = pd.to_numeric(recent_df[p], errors="coerce").dropna().tail(cfg["trend_window"]).mean()
            if np.isnan(ma):
                continue
            drift = z_score(ma, b)
            if abs(drift) > cfg["trend_drift_z"]:
                trend.append({"parameter": p, "moving_average": float(ma), "drift_z": round(float(drift), 2),
                              "basis": "trend"})
                findings.append({"parameter": p, "severity": "AMBER", "value": float(ma), "basis": "trend",
                                 "rule": f"{p} {cfg['trend_window']}-reading moving average drifted "
                                         f"{drift:+.1f} std from baseline"})

    ml = None
    if detector is not None and len(valid) >= len(FEATURES) // 2:
        ml = detector.score(valid)
        if ml["is_anomaly"]:
            top = sorted(baseline_dev, key=lambda d: -abs(d["z"]))[:2]
            contrib = ", ".join(f"{d['parameter']} (z={d['z']:+.1f})" for d in top) or "multivariate pattern"
            findings.append({"parameter": "multivariate", "severity": "AMBER", "value": ml["score"],
                             "basis": "ml_model",
                             "rule": f"Isolation Forest flagged an unusual combination; largest deviations: {contrib}"})

    detected = bool(findings)
    return {
        "timestamp": reading.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        "anomaly_detected": detected,
        "measurements": valid,
        "baseline_comparison": baseline_dev,
        "findings": findings,
        "trend": trend,
        "ml": ml,
        "detection_reason": "; ".join(f["rule"] for f in findings) or "No deviation detected",
        "suggested_review_action": ("Review flagged parameters against the crew medical protocol."
                                    if detected else "Continue routine monitoring."),
        "data_quality": {"score": round(quality, 2), "issues": issues},
        "disclaimer": SCORE_DISCLAIMER + " Configured thresholds are prototype values, not clinical limits.",
    }
