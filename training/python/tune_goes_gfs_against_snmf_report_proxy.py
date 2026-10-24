"""Select a 24h fire-alert threshold on Dec-2025 SNMF proxy, test in Jan-2026.

The target is an active incident listed in a daily SNMF report within 10 km of
a route-sector center. Absence from the report is only a proxy negative, not
proof that there was no physical fire.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from environmental_sources import PUBLIC, ROOT, sha256


BASE = ROOT / "docs/environmental-models-2026-10-22"
GEOGRAPHY = PUBLIC / "geography.json"
VALIDATION_PREDICTIONS = BASE / "fire-goes-gfs-24h-evaluation.json"
SNMF_2025 = BASE / "snmf-2025-daily-occurrence-events.json"
SNMF_2026 = BASE / "snmf-2026-jan-daily-occurrence-events.json"
MANIFEST_2025 = PUBLIC / "private/snmf-daily-occurrence-2025/source-manifest.json"
MANIFEST_2026 = PUBLIC / "private/snmf-daily-occurrence-2026-jan/source-manifest.json"
OUT = BASE / "fire-goes-gfs-snmf-proxy-threshold-evaluation.json"
RADIUS_KM = 10.0
PRECISION_FLOOR = 0.90
MIN_ALERTS = 5
ACTIVE_STATES = {"ACTIVO", "CONTENIDO", "CONTROLADO"}


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = np.radians([lat1, lat2])
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return float(6371.0088 * 2 * np.arcsin(min(1.0, np.sqrt(a))))


def report_labels(events_path: Path, manifest_path: Path, predictions: list[dict], centers: dict[str, tuple[float, float]]) -> tuple[list[dict], dict]:
    events = json.loads(events_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target_dates = {row["target_date"] for row in predictions}
    period_start, period_end = min(target_dates), max(target_dates)
    period_reports = [row for row in manifest["reports"] if period_start <= row["date"] <= period_end]
    downloaded = {row["date"] for row in period_reports if row["status"] in {"downloaded", "cached"}}
    snapshots_by_date: dict[str, list[dict]] = {}
    for row in events["snapshots"]:
        snapshots_by_date.setdefault(row["report_date"], []).append(row)
    results = []
    period_snapshot_dates = {day for day in snapshots_by_date if period_start <= day <= period_end}
    unlocated_dates = sorted(day for day in period_snapshot_dates
        if any(row["latitude"] is None or row["longitude"] is None for row in snapshots_by_date[day]))
    diagnostics = {"downloaded_report_dates": len(downloaded), "parsed_report_dates_with_rows": len(period_snapshot_dates),
        "report_dates_with_unlocated_incident_rows": len(unlocated_dates),
        "report_dates_excluded_due_to_unlocated_incidents": unlocated_dates,
        "missing_reports": len(period_reports) - len(downloaded),
        "zero_parsed_or_unavailable_dates": sorted(downloaded - period_snapshot_dates),
        "period": [period_start, period_end]}
    for target in predictions:
        day, region = target["target_date"], target["route_sector"]
        if day not in downloaded or day not in snapshots_by_date:
            continue
        records = snapshots_by_date[day]
        if any(row["latitude"] is None or row["longitude"] is None for row in records):
            continue
        lat, lon = centers[region]
        nearby = [row for row in records if distance_km(lat, lon, float(row["latitude"]), float(row["longitude"])) <= RADIUS_KM]
        if any(row["status"] == "UNKNOWN" for row in nearby):
            continue
        label = int(any(row["status"] in ACTIVE_STATES for row in nearby))
        results.append(target | {"snmf_active_incident_proxy": label,
            "nearby_reported_incidents": [{"name": row["incident_name"], "status": row["status"],
                "distance_km": round(distance_km(lat, lon, float(row["latitude"]), float(row["longitude"])), 3)}
                for row in nearby]})
    return results, diagnostics


def metrics(rows: list[dict], threshold: float, field: str = "score") -> dict:
    actual = np.asarray([row["snmf_active_incident_proxy"] for row in rows], dtype=np.uint8)
    predicted = np.asarray([float(row[field]) >= threshold for row in rows], dtype=np.uint8)
    tp = int(np.sum((actual == 1) & (predicted == 1)))
    fp = int(np.sum((actual == 0) & (predicted == 1)))
    fn = int(np.sum((actual == 1) & (predicted == 0)))
    tn = int(np.sum((actual == 0) & (predicted == 0)))
    alerts = tp + fp
    positives = tp + fn
    return {"threshold": threshold, "route_sector_days": len(rows), "proxy_positive_route_sector_days": positives,
        "alerts": alerts, "true_report_matches": tp, "alerts_without_listed_active_incident": fp,
        "missed_reported_active_incidents": fn, "no_alert_no_listed_active_incident": tn,
        "precision_vs_report_proxy": tp / alerts if alerts else None,
        "recall_vs_report_proxy": tp / positives if positives else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, default=VALIDATION_PREDICTIONS)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    evaluation_path = args.evaluation if args.evaluation.is_absolute() else ROOT / args.evaluation
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    geography = json.loads(GEOGRAPHY.read_text(encoding="utf-8"))
    centers = {row["name"]: (float(row["latitude"]), float(row["longitude"]))
        for row in geography["fire_regions"]}
    valid_predictions = evaluation["validation"]["route_sector_day_predictions"]
    test_predictions = evaluation["test"]["route_sector_day_predictions"]
    # Keep the datasets paired explicitly so their report manifests and dates cannot be mixed.
    validation_rows, validation_coverage = report_labels(SNMF_2025, MANIFEST_2025, valid_predictions, centers)
    test_rows, test_coverage = report_labels(SNMF_2026, MANIFEST_2026, test_predictions, centers)

    candidates = []
    diagnostic_candidates = []
    for threshold in sorted({float(row["score"]) for row in validation_rows}):
        result = metrics(validation_rows, threshold)
        if result["alerts"] >= MIN_ALERTS:
            diagnostic_candidates.append((result["precision_vs_report_proxy"], result["recall_vs_report_proxy"], -result["alerts"], threshold, result))
            if result["precision_vs_report_proxy"] >= PRECISION_FLOOR:
                candidates.append((result["recall_vs_report_proxy"], result["precision_vs_report_proxy"], result["alerts"], threshold, result))
    selected = max(candidates, key=lambda row: row[:4]) if candidates else None
    best_diagnostic = max(diagnostic_candidates, key=lambda row: row[:4]) if diagnostic_candidates else None
    results = {
        "experiment_id": f"goes-gfs-24h-snmf-report-proxy-validation-{min(row['target_date'] for row in valid_predictions)}-{max(row['target_date'] for row in valid_predictions)}-test-{min(row['target_date'] for row in test_predictions)}-{max(row['target_date'] for row in test_predictions)}",
        "interpretation": "The positive and negative labels are agreement with official daily report listings; a negative proxy is not proof that no physical fire occurred.",
        "protocol": {"validation_period": f"{min(row['target_date'] for row in valid_predictions)} through {max(row['target_date'] for row in valid_predictions)}",
            "test_period": f"{min(row['target_date'] for row in test_predictions)} through {max(row['target_date'] for row in test_predictions)}",
            "spatial_radius_km": RADIUS_KM, "validation_precision_floor": PRECISION_FLOOR,
            "validation_minimum_alerts": MIN_ALERTS, "selection_rule": "Maximize validation proxy recall among thresholds meeting the proxy precision floor and minimum alert count; then prefer precision, alert count, threshold.",
            "test_threshold_selected_using_validation_only": True},
        "sources": {"evaluation_sha256": sha256(evaluation_path), "geography_sha256": sha256(GEOGRAPHY),
            "snmf_2025_sha256": sha256(SNMF_2025), "snmf_2026_sha256": sha256(SNMF_2026),
            "manifest_2025_sha256": sha256(MANIFEST_2025), "manifest_2026_sha256": sha256(MANIFEST_2026)},
        "validation_report_coverage": validation_coverage,
        "test_report_coverage": test_coverage,
        "validation_route_days_with_proxy_label": len(validation_rows),
        "validation_metrics_at_0_5_diagnostic": metrics(validation_rows, 0.5),
        "best_validation_proxy_precision_with_minimum_alerts": None if best_diagnostic is None else best_diagnostic[4],
        "selected_threshold": None if selected is None else selected[3],
        "validation_at_selected_threshold": None if selected is None else selected[4],
        "test_route_days_with_proxy_label": len(test_rows),
        "test_metrics_at_0_5_diagnostic": metrics(test_rows, 0.5),
        "test_at_validation_selected_threshold": None if selected is None else metrics(test_rows, selected[3]),
        "deployment_approved": False,
        "limitations": [
            "SNMF reports are not an exhaustive surveyed fire/no-fire registry; reported-clear negatives are proxy labels only.",
            "The archive has missing/unparsed reports and records with missing coordinates; dates with unlocated incidents were excluded from threshold evaluation.",
            "Route-days and adjacent-day fires are correlated; route-day metrics are descriptive and do not represent independent fire-event precision.",
            "The 10 km rule uses route-sector centers rather than trail geometries and is not a safety-validated radius.",
            "The predictor targets a GOES fire detection 24h later, not ignition or a safety outcome; SNMF dates are day-level only.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in results.items() if key not in ("sources", "limitations")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
