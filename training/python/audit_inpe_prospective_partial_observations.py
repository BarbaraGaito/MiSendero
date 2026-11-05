#!/usr/bin/env python3
"""Audit currently available portions of prospective INPE windows.

This is a positive-detection screen, not a complete forecast evaluation. Missing
or immature daily files are excluded from mature coverage; immature files can
contribute positive detections only and are never used to label no-fire.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from audit_inpe_reference_detections_route_polylines import (
    GEOMETRY as ROUTE_GEOMETRY_PATH,
    distance_to_polyline_km,
    prepare_routes,
)


ROOT = Path(__file__).resolve().parents[2]
CAPTURE_DIR = ROOT / "training/data/environmental/inpe_fire_forecasts"
DAILY_DIR = ROOT / "training/data/environmental/private/inpe-ams-satellite-reference/daily"
OUTPUT_JSON = ROOT / "docs/environmental-models-2026-10-22/fire-inpe-prospective-partial-audit-2026-10-23.json"
OUTPUT_MD = OUTPUT_JSON.with_suffix(".md")
COMPLETE_AFTER_UTC_HOUR = 6
RADIUS_KM = 10


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def record_time_range(path: Path) -> tuple[str | None, str | None]:
    earliest = latest = None
    with path.open("r", encoding="latin1", newline="") as stream:
        rows = csv.DictReader(stream)
        if "data_hora_gmt" not in (rows.fieldnames or []):
            raise ValueError(f"Missing data_hora_gmt column in {path.name}")
        for row in rows:
            if row.get("pais", "").strip().casefold() != "argentina":
                continue
            value = datetime.strptime(row["data_hora_gmt"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            earliest = value if earliest is None or value < earliest else earliest
            latest = value if latest is None or value > latest else latest
    iso = lambda value: value.isoformat().replace("+00:00", "Z") if value else None
    return iso(earliest), iso(latest)


def available_daily_file(day: date) -> tuple[Path | None, dict[str, Any] | None]:
    stem = f"focos_diario_{day:%Y%m%d}"
    csv_path = DAILY_DIR / f"{stem}.csv"
    manifest_path = DAILY_DIR / f"{stem}.manifest.json"
    if not csv_path.is_file() or not manifest_path.is_file():
        return None, None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    last_modified = manifest.get("last_modified")
    if not last_modified:
        return None, None
    modified = parsedate_to_datetime(last_modified).astimezone(timezone.utc)
    minimum = datetime.combine(day + timedelta(days=1), time(COMPLETE_AFTER_UTC_HOUR), tzinfo=timezone.utc)
    expected_hash = manifest.get("sha256")
    actual_hash = sha256(csv_path)
    if expected_hash != actual_hash:
        raise ValueError(f"Hash mismatch for mature daily INPE CSV: {csv_path.name}")
    earliest, latest = record_time_range(csv_path)
    return csv_path, {
        "date_utc": day.isoformat(),
        "csv": csv_path.name,
        "sha256": actual_hash,
        "bytes": csv_path.stat().st_size,
        "last_modified": last_modified,
        "maturity_status": "mature_by_last_modified" if modified >= minimum else "not_mature",
        "earliest_argentina_record_utc": earliest,
        "latest_argentina_record_utc": latest,
    }


def read_window_detections(path: Path, start: datetime, end: datetime,
                           routes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    matches = {route["name"]: [] for route in routes}
    with path.open("r", encoding="latin1", newline="") as stream:
        rows = csv.DictReader(stream)
        expected = {"id", "lat", "lon", "data_hora_gmt", "satelite", "pais"}
        if not expected.issubset(rows.fieldnames or []):
            raise ValueError(f"Unexpected columns in {path.name}: {rows.fieldnames}")
        for row in rows:
            if row.get("pais", "").strip().casefold() != "argentina":
                continue
            observed = datetime.strptime(row["data_hora_gmt"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if not start <= observed < end:
                continue
            lat, lon = float(row["lat"]), float(row["lon"])
            for route in routes:
                south, north, west, east = route["bounds"]
                if not (south <= lat <= north and west <= lon <= east):
                    continue
                distance = distance_to_polyline_km(lat, lon, route["projection"])
                if distance <= RADIUS_KM:
                    matches[route["name"]].append({
                        "detection_id": row["id"],
                        "observed_at_utc": observed.isoformat().replace("+00:00", "Z"),
                        "sensor": row.get("satelite"),
                        "distance_km": round(distance, 3),
                    })
    return matches


def parse_as_of(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("--as-of must include a UTC offset or Z")
    return result.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", help="Evaluation cutoff, ISO timestamp with UTC offset; defaults to now.")
    parser.add_argument("--output", type=Path, default=OUTPUT_JSON)
    args = parser.parse_args()
    as_of = parse_as_of(args.as_of)
    unique: dict[tuple, tuple[dict[str, Any], str]] = {}
    for capture_path in sorted(CAPTURE_DIR.glob("capture_*.json")):
        capture = json.loads(capture_path.read_text(encoding="utf-8"))
        for forecast in capture.get("forecasts", []):
            valid_text = forecast.get("forecast_valid_utc")
            if not valid_text:
                continue
            identity = (forecast.get("horizon_file"), forecast.get("forecast_run_utc"),
                        valid_text, forecast.get("sha256"))
            unique.setdefault(identity, (forecast, capture_path.name))

    records = []
    used_sources: dict[str, dict[str, Any]] = {}
    route_geometry = json.loads(ROUTE_GEOMETRY_PATH.read_text(encoding="utf-8"))
    route_polylines = prepare_routes(route_geometry["fire_route_geometries"])
    for forecast, capture_name in unique.values():
        start = datetime.fromisoformat(forecast["forecast_valid_utc"].replace("Z", "+00:00")).astimezone(timezone.utc)
        end = min(start + timedelta(hours=24), as_of)
        matured_csv_segments = []
        available_intervals = []
        route_hits = {route["name"]: [] for route in route_polylines}
        mature_route_hits = {route["name"]: [] for route in route_polylines}
        if end > start:
            day = start.date()
            while day < end.date() or (day == end.date() and end.time() != time.min):
                csv_path, source = available_daily_file(day)
                segment_start = max(start, datetime.combine(day, time.min, tzinfo=timezone.utc))
                segment_end = min(end, datetime.combine(day + timedelta(days=1), time.min, tzinfo=timezone.utc))
                if csv_path is not None and source is not None and segment_end > segment_start:
                    used_sources[csv_path.name] = source
                    interval = {
                        "start_utc": segment_start.isoformat().replace("+00:00", "Z"),
                        "end_utc": segment_end.isoformat().replace("+00:00", "Z"),
                        "source_file": csv_path.name,
                        "maturity_status": source["maturity_status"],
                    }
                    available_intervals.append(interval)
                    if source["maturity_status"] == "mature_by_last_modified":
                        matured_csv_segments.append(interval)
                    day_hits = read_window_detections(csv_path, segment_start, segment_end, route_polylines)
                    for route_name, hits in day_hits.items():
                        tagged_hits = [{**hit, "source_maturity_status": source["maturity_status"]} for hit in hits]
                        route_hits[route_name].extend(tagged_hits)
                        if source["maturity_status"] == "mature_by_last_modified":
                            mature_route_hits[route_name].extend(tagged_hits)
                day += timedelta(days=1)
        matured_csv_hours = sum(
            (datetime.fromisoformat(item["end_utc"].replace("Z", "+00:00"))
             - datetime.fromisoformat(item["start_utc"].replace("Z", "+00:00"))).total_seconds() / 3600
            for item in matured_csv_segments
        )
        records.append({
            "source_capture": capture_name,
            "horizon": forecast.get("horizon_file"),
            "forecast_run_utc": forecast.get("forecast_run_utc"),
            "forecast_valid_utc": forecast["forecast_valid_utc"],
            "window_end_utc": (start + timedelta(hours=24)).isoformat().replace("+00:00", "Z"),
            "partial_as_of_utc": as_of.isoformat().replace("+00:00", "Z"),
            "hours_with_matured_daily_csv_segment": round(matured_csv_hours, 3),
            "available_csv_date_segments_for_positive_only_search": available_intervals,
            "matured_csv_date_segments": matured_csv_segments,
            "route_detections": [
                {"route": name, "count": len(hits), "mature_detection_count": len(mature_route_hits[name]), "detections": hits}
                for name, hits in route_hits.items()
            ],
            "status": "partial_positive_detection_screen_only" if available_intervals else "no_source_file_available_yet",
        })

    result = {
        "experiment_id": "inpe-prospective-partial-detection-screen",
        "as_of_utc": as_of.isoformat().replace("+00:00", "Z"),
        "status": "incomplete_windows_not_scored",
        "source": "INPE daily South America active-fire detection CSV; Argentina rows only",
        "spatial_rule": "within 10 km of the complete reviewed route polylines, using a local planar point-to-segment distance",
        "route_geometry_sha256": sha256(ROUTE_GEOMETRY_PATH),
        "temporal_rule": "Only mature daily CSVs and detections in [forecast validity, min(validity + 24 h, as-of)) are included.",
        "summary": {
            "unique_forecast_windows": len(records),
            "windows_with_any_available_source_file": sum(bool(row["available_csv_date_segments_for_positive_only_search"]) for row in records),
            "windows_with_any_matured_daily_csv_segment": sum(bool(row["hours_with_matured_daily_csv_segment"]) for row in records),
            "windows_with_24h_of_matured_daily_csv_segments": sum(row["hours_with_matured_daily_csv_segment"] >= 24 for row in records),
            "total_route_detection_records_in_available_files": sum(item["count"] for row in records for item in row["route_detections"]),
            "total_route_detection_records_in_matured_intervals": sum(item["mature_detection_count"] for row in records for item in row["route_detections"]),
            "synthetic_observations": 0,
            "deployment_approved": False,
        },
        "source_files": list(used_sources.values()),
        "forecasts": records,
        "limitations": [
            "Incomplete forecast windows are not assigned positive or negative outcomes and no precision metric is computed.",
            "No INPE detection in an observed interval does not establish fire absence; the satellite archive is positive-only for this purpose.",
            "The spatial unit is a 10 km buffer around full route polylines; the INPE risk index itself is still sampled at route-sector centers.",
            "An INPE active-fire point is a satellite detection, not a field-confirmed ignition or independent incident adjudication.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    total_hits = result["summary"]["total_route_detection_records_in_available_files"]
    report = [
        "# INPE prospective partial observation audit",
        "",
        f"Cutoff: `{result['as_of_utc']}`. Forecast windows: {len(records)}; windows with any available source file: {result['summary']['windows_with_any_available_source_file']}; windows with at least one matured CSV date segment: {result['summary']['windows_with_any_matured_daily_csv_segment']}; windows with 24 hours of matured CSV date segments: {result['summary']['windows_with_24h_of_matured_daily_csv_segments']}; detections within 10 km of full route polylines in available files: {total_hits}.",
        "",
        "This is a partial positive-detection screen against full trail lines. Incomplete windows are not scored, and a zero count is not a verified no-fire outcome. The forecast index was sampled at route-sector centers.",
        "",
        "Available CSVs were checked against their SHA-256 manifests. CSV date segments passing the following-day 06:00 UTC maturity rule are labeled mature; immature files contribute positive detections only. A CSV date segment is not a sensor-coverage mask, and no-detection results do not prove fire absence.",
    ]
    args.output.with_suffix(".md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), **result["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
