#!/usr/bin/env python3
"""Verify standard FIRMS date availability for the October 2026 test window."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE = ROOT / (
    "training/data/environmental/private/firms-route-detections-standard-availability-2026-10-23-auditable/"
    "firms-viirs-route-detections-2026-10-22-2026-10-23.json"
)
DEFAULT_OUTPUT = ROOT / "docs/environmental-models-2026-10-22/fire-firms-standard-availability-2026-10-23.json"
TARGET_START = date(2026, 10, 22)
TARGET_END = date(2026, 10, 23)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_path(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if ROOT.resolve() not in path.parents:
        raise ValueError(f"Source path escapes repository root: {relative}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    archive_bytes = args.archive.read_bytes()
    archive = json.loads(archive_bytes)
    raw_path = source_path(archive["availability_response_file"])
    raw = raw_path.read_bytes()
    raw_hash = sha256(raw)
    if raw_hash != archive["availability_response_sha256"]:
        raise ValueError("FIRMS availability CSV hash does not match the acquisition manifest")

    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    required = {"data_id", "min_date", "max_date"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError("Unexpected NASA FIRMS availability response columns")
    expected = archive["sensors"]
    ranges = {
        row["data_id"]: [row["min_date"], row["max_date"]]
        for row in reader if row.get("data_id") in expected
    }
    if set(ranges) != set(expected):
        raise ValueError("Availability CSV is missing one or more requested standard sensors")
    if ranges != archive["sensor_date_availability"]:
        raise ValueError("Parsed availability ranges differ from the acquisition archive")
    requests = archive["requests"]
    if len(requests) != 24 or any(row.get("status") != "outside_available_date_range" for row in requests):
        raise ValueError("Expected 24 route/sensor requests, all outside standard-product availability")
    latest_end = max(date.fromisoformat(period[1]) for period in ranges.values())
    gap_days = (TARGET_END - latest_end).days
    result: dict[str, Any] = {
        "experiment_id": "nasa-firms-standard-product-availability-lag-audit",
        "status": "standard_products_not_yet_available_for_target_window",
        "target_window_utc_dates": [TARGET_START.isoformat(), TARGET_END.isoformat()],
        "query_started_at_utc": archive["query_started_at_utc"],
        "query_completed_at_utc": archive["completed_at_utc"],
        "sensors": ranges,
        "summary": {
            "latest_standard_date_available_any_sensor": latest_end.isoformat(),
            "days_behind_target_end_date": gap_days,
            "route_sensor_requests": len(requests),
            "outside_available_date_range": sum(row["status"] == "outside_available_date_range" for row in requests),
            "detection_queries_made": sum(row["status"] == "ok" for row in requests),
            "negative_labels_created": 0,
            "synthetic_observations": 0,
            "deployment_approved": False,
        },
        "source": {
            "availability_response_file": archive["availability_response_file"],
            "availability_response_sha256": raw_hash,
            "availability_response_bytes": len(raw),
            "route_query_archive_sha256": sha256(archive_bytes),
        },
        "interpretation": "NASA FIRMS standard VIIRS products were available only through 2026-06-30 at query time. No standard active-fire detections for 2026-10-22/23 could be requested; NRT is provisional and remains the only FIRMS source checked for this window.",
        "limitations": [
            "An unavailable date range is a source-availability limit, not a no-fire label.",
            "FIRMS standard detections are positive evidence only; empty or unavailable records cannot verify fire absence without valid sensor-coverage masks.",
            "The standard archive should be checked again after its processing lag; NASA says NRT is typically replaced after 2-3 months and can take up to 5 months.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    report = [
        "# NASA FIRMS standard-product availability for the prospective window",
        "",
        f"At `{result['query_completed_at_utc']}`, the availability CSV was hash-verified. VIIRS standard products for S-NPP, NOAA-20, and NOAA-21 were available only through `{latest_end.isoformat()}`; the target dates were 2026-10-22 and 2026-10-23 ({gap_days} days after the latest standard date). All 24 route/sensor checks were outside the available range, so no standard detection queries could be made.",
        "",
        "This is an archive-availability finding, not a no-fire result. Recheck the dates after NASA processing advances; until then, NRT detections are provisional positive-only evidence and cannot supply negative labels.",
        "",
        f"The verified availability response has SHA-256 `{raw_hash}`. The source CSV and query archive are in the ignored research-data directory.",
    ]
    args.output.with_suffix(".md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.relative_to(ROOT)), **result["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
