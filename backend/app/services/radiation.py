"""Radiation record helpers. Units are preserved; no unit conversion is performed
silently, and no universal medical limit is applied."""
import pandas as pd


def cumulative(records: pd.DataFrame) -> pd.DataFrame:
    """Cumulative dose per unit. Records with different units are never summed together."""
    df = records.sort_values("timestamp").copy()
    df["cumulative_dose"] = df.groupby("unit")["dose"].cumsum()
    return df


# Documented conversions (only exact, unit-system conversions).
CONVERSIONS = {("mGy", "uGy"): 1000.0, ("uGy", "mGy"): 0.001, ("mSv", "uSv"): 1000.0, ("uSv", "mSv"): 0.001}


def convert(value: float, from_unit: str, to_unit: str):
    """Returns (converted, note). Gy and Sv are NOT interchangeable and raise ValueError."""
    if from_unit == to_unit:
        return value, "no conversion"
    f = CONVERSIONS.get((from_unit, to_unit))
    if f is None:
        raise ValueError(f"No documented conversion {from_unit}->{to_unit} (Gy and Sv are not interchangeable)")
    return value * f, f"{from_unit}->{to_unit} x{f}"
