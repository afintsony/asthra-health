"""PDF + CSV report generation (reportlab)."""
import csv
import io
from datetime import datetime, timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def _table(rows):
    t = Table(rows, hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B1D3A")),
                           ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    return t


def build_pdf(report: dict) -> bytes:
    """report keys: astronaut_code, mission, period, vitals_summary{param:{mean,min,max,unit}},
    wellness{...}, radiation[{timestamp,dose,unit,source}], anomalies[], alerts[], data_quality_notes[],
    synthetic(bool)"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="ASTRAHEALTH Report")
    st = getSampleStyleSheet()
    el = [Paragraph("ASTRAHEALTH — BITCOSMOS", st["Title"]),
          Paragraph("Monitoring Life Beyond Earth.", st["Italic"]), Spacer(1, 10),
          Paragraph(f"Astronaut: {report['astronaut_code']} | Mission: {report['mission']}", st["Normal"]),
          Paragraph(f"Reporting period: {report['period']} | Generated: "
                    f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", st["Normal"]),
          Spacer(1, 10), Paragraph("Vital-sign summary", st["Heading2"])]
    rows = [["Parameter", "Mean", "Min", "Max", "Unit"]] + [
        [p, f"{v['mean']:.1f}", f"{v['min']:.1f}", f"{v['max']:.1f}", v["unit"]]
        for p, v in report.get("vitals_summary", {}).items()]
    el.append(_table(rows))
    el += [Paragraph("Wellness summary", st["Heading2"]),
           Paragraph(", ".join(f"{k}: {v}" for k, v in report.get("wellness", {}).items()) or "No records", st["Normal"]),
           Paragraph("Radiation records (original units preserved)", st["Heading2"])]
    rr = [["Timestamp", "Dose", "Unit", "Source"]] + [
        [str(r["timestamp"])[:19], f"{r['dose']:.1f}", r["unit"], r["source"]] for r in report.get("radiation", [])[:40]]
    el.append(_table(rr))
    el.append(Paragraph("Detected anomalies", st["Heading2"]))
    el += [Paragraph(f"• {a}", st["Normal"]) for a in report.get("anomalies", [])] or [Paragraph("None", st["Normal"])]
    el.append(Paragraph("Alert history", st["Heading2"]))
    el += [Paragraph(f"• {a}", st["Normal"]) for a in report.get("alerts", [])] or [Paragraph("None", st["Normal"])]
    el.append(Paragraph("Data quality notes", st["Heading2"]))
    el += [Paragraph(f"• {a}", st["Normal"]) for a in report.get("data_quality_notes", [])] or [Paragraph("None", st["Normal"])]
    if report.get("synthetic"):
        el.append(Paragraph("<b>DISCLOSURE: This report contains SYNTHETIC demonstration data, not real astronaut measurements.</b>", st["Normal"]))
    el.append(Spacer(1, 8))
    el.append(Paragraph("Research prototype / decision support only. Not clinically validated or medically certified.", st["Italic"]))
    doc.build(el)
    return buf.getvalue()


def build_csv(readings: list) -> str:
    """Rows: timestamp, parameter, value, unit, source."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["timestamp", "parameter", "value", "unit", "source"])
    for r in readings:
        w.writerow([r["timestamp"], r["parameter"], r["value"], r["unit"], r["source"]])
    return out.getvalue()
