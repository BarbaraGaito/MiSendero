"""Compare held-out 24h GFS+GOES alerts with independent daily SNMF reports.

This measures agreement with incidents listed in the official daily reports,
not precision against all physical fires. Missing reports and ambiguous nearby
statuses are excluded instead of treated as fire-free.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from environmental_sources import PUBLIC, ROOT, sha256


REPORT = ROOT / "docs/environmental-models-2026-10-22/fire-goes-gfs-24h-evaluation.json"
EVENTS = ROOT / "docs/environmental-models-2026-10-22/snmf-2026-jan-daily-occurrence-events.json"
GEOGRAPHY = PUBLIC / "geography.json"
OUT = ROOT / "docs/environmental-models-2026-10-22/goes-gfs-24h-snmf-daily-report-agreement-2026-jan.json"
RADIUS_KM = 10.0
ACTIVE_STATES = {"ACTIVO", "CONTENIDO", "CONTROLADO"}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(a)))


def main() -> None:
    evaluation = json.loads(REPORT.read_text(encoding="utf-8"))
    event_data = json.loads(EVENTS.read_text(encoding="utf-8"))
    geography = json.loads(GEOGRAPHY.read_text(encoding="utf-8"))
    centers = {row["name"]: (float(row["latitude"]), float(row["longitude"]))
        for row in geography["fire_regions"]}
    predictions = {(row["route_sector"], row["target_date"]): row
        for row in evaluation["test"]["route_sector_day_predictions"]}

    snapshots_by_date: dict[str, list[dict]] = {}
    for row in event_data["snapshots"]:
        if row["latitude"] is None or row["longitude"] is None:
            continue
        snapshots_by_date.setdefault(row["report_date"], []).append(row)

    counts = {"tp": 0, "fp_report_disagreement": 0, "fn": 0, "tn_reported_clear": 0,
        "ambiguous_excluded": 0, "alerts": 0, "positives": 0}
    rows = []
    for (region, target_date), pred in sorted(predictions.items()):
        if target_date not in snapshots_by_date:
            continue
        lat, lon = centers[region]
        nearby = [event for event in snapshots_by_date[target_date]
            if haversine_km(lat, lon, event["latitude"], event["longitude"]) <= RADIUS_KM]
        has_active = any(event["status"] in ACTIVE_STATES for event in nearby)
        has_unknown = any(event["status"] == "UNKNOWN" for event in nearby)
        if has_active:
            label = 1
            counts["positives"] += 1
        elif has_unknown:
            label = None
            counts["ambiguous_excluded"] += 1
        else:
            label = 0
        alert = bool(pred["alert_at_0_5"])
        if label is not None:
            if alert:
                counts["alerts"] += 1
            if label and alert:
                counts["tp"] += 1
            elif label:
                counts["fn"] += 1
            elif alert:
                counts["fp_report_disagreement"] += 1
            else:
                counts["tn_reported_clear"] += 1
        rows.append({"route_sector": region, "date": target_date, "model_score": pred["score"],
            "model_alert_at_0_5": alert, "persistence_alert": pred["persistence"],
            "snmf_active_incident_within_10km": (bool(label) if label is not None else None),
            "nearby_snapshot_incidents": [{"name": event["incident_name"], "status": event["status"],
                "distance_km": round(haversine_km(lat, lon, event["latitude"], event["longitude"]), 3)}
                for event in nearby]})

    evaluated = sum(counts[key] for key in ("tp", "fp_report_disagreement", "fn", "tn_reported_clear"))
    report_precision = counts["tp"] / counts["alerts"] if counts["alerts"] else None
    report_recall = counts["tp"] / counts["positives"] if counts["positives"] else None
    persistence = {"tp": 0, "alert_without_reported_active_incident": 0,
        "missed_reported_active_incident": 0, "no_alert_and_no_reported_active_incident": 0}
    for row in rows:
        label = row["snmf_active_incident_within_10km"]
        if label is None:
            continue
        if row["persistence_alert"] and label:
            persistence["tp"] += 1
        elif row["persistence_alert"]:
            persistence["alert_without_reported_active_incident"] += 1
        elif label:
            persistence["missed_reported_active_incident"] += 1
        else:
            persistence["no_alert_and_no_reported_active_incident"] += 1
    results = {
        "experiment_id": "goes-gfs-24h-vs-independent-snmf-daily-report-snapshots-2026-01",
        "interpretation": "Descriptive agreement with the daily incident listings only. A sector-day without a nearby listed incident is not proof that no physical fire occurred; these are not validated physical-fire precision/recall metrics.",
        "protocol": {"period": "2026-01-01 through 2026-01-31", "alert_threshold": 0.5,
            "spatial_rule": "A daily listed incident within 10 km of the fixed route-sector center",
            "positive_rule": "At least one nearby snapshot incident with status ACTIVO, CONTENIDO, or CONTROLADO",
            "negative_proxy_rule": "An archived SNMF report exists for the date and no nearby active or UNKNOWN incident is listed",
            "missing_dates": "Excluded; not negative", "model_lead_hours": 24},
        "sources": {"model_evaluation_sha256": sha256(REPORT), "snmf_event_archive_sha256": sha256(EVENTS),
            "geography_sha256": sha256(GEOGRAPHY)},
        "report_dates_available": len(snapshots_by_date),
        "route_sector_days_with_report_and_model_coverage": len(rows),
        "route_sector_days_excluded_for_nearby_unknown_status": counts["ambiguous_excluded"],
        "route_sector_days_evaluated": evaluated,
        "confusion_vs_daily_report_proxy": {"true_positive_report_match": counts["tp"],
            "alert_without_reported_active_incident": counts["fp_report_disagreement"],
            "missed_reported_active_incident": counts["fn"],
            "no_alert_and_no_reported_active_incident": counts["tn_reported_clear"]},
        "alert_precision_vs_report_proxy": report_precision,
        "recall_vs_report_proxy": report_recall,
        "persistence_confusion_vs_daily_report_proxy": persistence,
        "limitations": [
            "The SNMF daily report archive is not an exhaustive fire/no-fire survey; proxy negatives mean only that no active incident was listed nearby.",
            "The 10 km radius is measured from route-sector centers, not trail polylines, and is exploratory rather than safety-validated.",
            "The score threshold 0.5 is diagnostic, uncalibrated, and not chosen against this independent source.",
            "Route-days repeat episodes and weather/satellite scans are correlated; descriptive counts are not independent event-level precision estimates.",
            "Incident report dates and statuses do not provide an exact ignition time; the 24 h model horizon is relative to the satellite target scan.",
        ],
        "deployment_approved": False,
        "route_sector_day_rows": rows,
    }
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in results.items() if key not in ("sources", "limitations", "route_sector_day_rows")},
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
