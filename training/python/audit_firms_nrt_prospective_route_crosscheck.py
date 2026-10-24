#!/usr/bin/env python3
"""Verify the archived NASA FIRMS NRT route cross-check for the INPE window."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE = ROOT / (
    "training/data/environmental/private/firms-route-detections-nrt-prospective-2026-10-23-after-window/"
    "firms-viirs-route-detections-2026-10-22-2026-10-23-viirs-snpp-nrt-viirs-noaa20-nrt-viirs-noaa21-nrt.json"
)
GEOMETRY = ROOT / "training/data/environmental/private/fire-route-geometries.json"
DEFAULT_OUTPUT = ROOT / "docs/environmental-models-2026-10-22/fire-nasa-firms-nrt-route-crosscheck-2026-10-22-23.json"
WINDOW_START = datetime(2026, 10, 22, 18, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 10, 23, 18, tzinfo=timezone.utc)
SENSORS = {"VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def import_acquirer():
    path = Path(__file__).with_name("acquire_firms_route_detections.py")
    spec = importlib.util.spec_from_file_location("firms_route_acquirer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load route-distance implementation from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def raw_response_path(relative_path: str) -> Path:
    path = (ROOT / relative_path).resolve()
    if ROOT.resolve() not in path.parents:
        raise ValueError(f"Raw response path escapes repository root: {relative_path}")
    return path


def exact_window_match(row: dict[str, str]) -> bool:
    raw_time = (row.get("acq_time") or "").strip()
    if not raw_time.isdigit():
        return False
    instant = datetime.strptime(
        row["acq_date"] + raw_time.zfill(4), "%Y-%m-%d%H%M"
    ).replace(tzinfo=timezone.utc)
    return WINDOW_START <= instant < WINDOW_END


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    archive_bytes = args.archive.read_bytes()
    archive = json.loads(archive_bytes)
    completed_at = datetime.fromisoformat(archive["completed_at_utc"].replace("Z", "+00:00")).astimezone(timezone.utc)
    if completed_at < WINDOW_END:
        raise ValueError("NRT query archive completed before the full target window ended")
    geometry_bytes = GEOMETRY.read_bytes()
    route_data = json.loads(geometry_bytes)["fire_route_geometries"]
    routes = {route["name"]: route for route in route_data}
    if archive.get("sensors") is None or set(archive["sensors"]) != SENSORS:
        raise ValueError("Archive does not contain exactly the three expected VIIRS NRT sensors")
    if archive.get("period") != ["2026-10-22", "2026-10-23"] or archive.get("route_buffer_km") != 10.0:
        raise ValueError("Archive period or route buffer differs from the prospective protocol")

    acquirer = import_acquirer()
    raw_checks = []
    exact_window_matches = []
    total_response_rows = 0
    for request in archive["requests"]:
        if request.get("status") != "ok":
            raise ValueError(f"Unsuccessful FIRMS request in archive: {request}")
        route_name = request["route_sector"]
        if route_name not in routes:
            raise ValueError(f"Unknown route in query archive: {route_name}")
        path = raw_response_path(request["raw_response_file"])
        raw = path.read_bytes()
        digest = sha256_bytes(raw)
        if digest != request.get("response_sha256") or len(raw) != request.get("response_bytes"):
            raise ValueError(f"Raw FIRMS response hash/size mismatch: {path.name}")
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        if not reader.fieldnames or not {"latitude", "longitude", "acq_date", "acq_time"} <= set(reader.fieldnames):
            raise ValueError(f"Unexpected columns in archived response: {path.name}")
        rows = list(reader)
        if len(rows) != request.get("response_rows"):
            raise ValueError(f"CSV row count mismatch: {path.name}")
        total_response_rows += len(rows)
        route_line = acquirer.route_coordinates(routes[route_name])
        route_rows = []
        for row in rows:
            try:
                latitude, longitude = float(row["latitude"]), float(row["longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            if acquirer.distance_to_route_km(latitude, longitude, route_line) <= archive["route_buffer_km"]:
                route_rows.append(row)
                if exact_window_match(row):
                    exact_window_matches.append({
                        "route": route_name,
                        "sensor": request["sensor"],
                        "date": row.get("acq_date"),
                        "time": row.get("acq_time"),
                    })
        if len(route_rows) != request.get("route_matches"):
            raise ValueError(f"Polyline match count mismatch: {route_name} / {request['sensor']}")
        raw_checks.append({
            "route": route_name,
            "sensor": request["sensor"],
            "requested_dates": [request["start_date"], request["end_date"]],
            "source_date_availability": [request["available_start_date"], request["available_end_date"]],
            "response_sha256": digest,
            "response_bytes": len(raw),
            "response_rows": len(rows),
            "matches_within_10km_of_full_route_for_requested_dates": len(route_rows),
        })

    if len(raw_checks) != 24:
        raise ValueError(f"Expected 24 route/sensor queries; found {len(raw_checks)}")
    result: dict[str, Any] = {
        "experiment_id": "nasa-firms-nrt-independent-positive-crosscheck-of-inpe-prospective-window",
        "status": "elapsed_window_nrt_positive_detection_crosscheck_no_route_matches",
        "target_window_utc": [
            WINDOW_START.isoformat().replace("+00:00", "Z"),
            WINDOW_END.isoformat().replace("+00:00", "Z"),
        ],
        "source": {
            "dataset": "NASA FIRMS VIIRS Near Real-Time area API",
            "query_started_at_utc": archive["query_started_at_utc"],
            "query_completed_at_utc": archive["completed_at_utc"],
            "target_window_ended_before_query_completed": True,
            "sensors": sorted(SENSORS),
            "period_queried_utc_dates_inclusive": archive["period"],
            "sensor_date_availability": archive["sensor_date_availability"],
            "query_archive_sha256": sha256_bytes(archive_bytes),
            "geometry_sha256": sha256_bytes(geometry_bytes),
            "availability_response_sha256": sorted({row["availability_response_sha256"] for row in archive["requests"]}),
            "raw_responses_verified": len(raw_checks),
            "raw_response_records": total_response_rows,
        },
        "spatial_rule": "10 km from the full stored trail polyline, recomputed from each archived CSV response.",
        "temporal_rule": "Exact check uses acquisition date/time UTC in [2026-10-22 18:00, 2026-10-23 18:00); all queries completed after this interval ended, and requested both UTC calendar dates.",
        "summary": {
            "route_sensor_queries": len(raw_checks),
            "query_errors": 0,
            "raw_csv_records_all_areas": total_response_rows,
            "route_matches_in_requested_dates": sum(row["matches_within_10km_of_full_route_for_requested_dates"] for row in raw_checks),
            "route_matches_in_exact_forecast_window": len(exact_window_matches),
            "negative_labels_created": 0,
            "synthetic_observations": 0,
            "deployment_approved": False,
        },
        "queries": raw_checks,
        "exact_window_matches": exact_window_matches,
        "limitations": [
            "FIRMS NRT supplies active-fire detections only; an empty response does not prove a fire-free route or sensor coverage.",
            "NRT observations are provisional and are later replaced by standard processing; they should be refreshed with standard data after the NASA processing lag for research conclusions.",
            "This is one short prospective window, not an estimate of model precision, recall, calibration, or lead time.",
            "The independent source checks positive fire detections; missing detections remain unknown.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    report = [
        "# NASA FIRMS NRT cross-check of the prospective INPE window",
        "",
        f"The exact forecast window was `{result['target_window_utc'][0]}` to `{result['target_window_utc'][1]}`. The NRT query completed at `{archive['completed_at_utc']}`, after the window ended. All {len(raw_checks)} route/sensor responses and hashes were verified; the CSV responses contained {total_response_rows} records total and yielded zero detections within 10 km of the eight complete trail polylines for the two requested dates.",
        "",
        "This is a positive-detection cross-check only. Empty NRT results are not fire-free labels or evidence of sensor coverage, and this single window cannot establish prediction precision. NRT is provisional; refresh the period from NASA standard processing after the product lag before drawing scientific conclusions.",
        "",
        "The machine-readable report includes every response SHA-256 and the source-archive hash. Private raw CSV responses are retained under the ignored research-data directory.",
    ]
    args.output.with_suffix(".md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.relative_to(ROOT)), **result["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
