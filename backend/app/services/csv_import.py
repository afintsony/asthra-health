"""CSV import: preview, column mapping, validation, error log."""
import io
import pandas as pd
from app.core.rules import FEATURES
from app.services.validation import validate_reading


def preview(content: bytes, n=5):
    df = pd.read_csv(io.BytesIO(content))
    return {"columns": list(df.columns), "rows": df.head(n).to_dict("records"), "total_rows": len(df)}


def parse(content: bytes, mapping: dict, source="CSV_IMPORT"):
    """mapping: {"timestamp": "<csv col>", "heart_rate": "<csv col>", ...}.

    Returns {"valid": [...], "errors": [...], "missing_report": {...}}. Nothing is
    silently dropped: every rejected row appears in `errors`.
    """
    df = pd.read_csv(io.BytesIO(content))
    if "timestamp" not in mapping or mapping["timestamp"] not in df.columns:
        raise ValueError("A timestamp column mapping is required")
    valid, errors = [], []
    missing = {p: 0 for p in FEATURES}
    for i, row in df.iterrows():
        line = int(i) + 2  # header = line 1
        ts = pd.to_datetime(row[mapping["timestamp"]], utc=True, errors="coerce")
        if pd.isna(ts):
            errors.append({"line": line, "error": "unparseable timestamp"})
            continue
        raw = {p: row[mapping[p]] if p in mapping and mapping[p] in df.columns else None for p in FEATURES}
        clean, issues, quality = validate_reading(raw)
        for iss in issues:
            if iss["issue"] == "missing":
                missing[iss["parameter"]] += 1
        bad = [x for x in issues if x["issue"] in ("implausible", "not_numeric")]
        if bad:
            errors.append({"line": line, "error": "invalid values", "details": bad})
        if all(v is None for v in clean.values()):
            if not bad:
                errors.append({"line": line, "error": "no usable measurements"})
            continue
        valid.append({"timestamp": ts.isoformat(), **clean, "source": source, "quality": round(quality, 2)})
    return {"valid": valid, "errors": errors, "missing_report": missing,
            "summary": {"rows": len(df), "imported": len(valid), "rejected_or_flagged": len(errors)}}
