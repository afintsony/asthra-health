"""Personalized baseline engine (mean, median, std, min/max, rolling, trend)."""
import pandas as pd
from scipy import stats
from app.core.rules import FEATURES


def compute_baseline(df: pd.DataFrame, window: int = 12, min_samples: int = 30) -> dict:
    """Per-parameter baseline from an individual's historical readings.

    Baselines describe THIS individual's history; they are not clinical norms.
    """
    out = {}
    ts = pd.to_datetime(df["timestamp"], utc=True) if "timestamp" in df else None
    for p in FEATURES:
        s = pd.to_numeric(df[p], errors="coerce").dropna() if p in df else pd.Series(dtype=float)
        n = int(len(s))
        if n == 0:
            out[p] = {"n": 0, "sufficient": False}
            continue
        entry = {
            "n": n, "sufficient": n >= min_samples,
            "mean": float(s.mean()), "median": float(s.median()),
            "std": float(s.std(ddof=1)) if n > 1 else 0.0,
            "min": float(s.min()), "max": float(s.max()),
            "rolling_mean_last": float(s.rolling(min(window, n)).mean().iloc[-1]),
        }
        if ts is not None and n >= 3:
            t_days = (ts.loc[s.index] - ts.loc[s.index].iloc[0]).dt.total_seconds() / 86400
            if t_days.nunique() > 1:
                entry["trend_per_day"] = float(stats.linregress(t_days.values, s.values).slope)
        out[p] = entry
    return out


def baseline_std(b: dict) -> float:
    """Std with a floor so near-constant history never divides by ~zero."""
    return max(b.get("std", 0.0), 0.02 * abs(b.get("mean", 0.0)), 1e-6)


def z_score(value: float, b: dict) -> float:
    return (value - b["mean"]) / baseline_std(b)
