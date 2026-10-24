"""Acquire point-based, 24-hour-lead archived weather forecasts for Argentine fire sectors.

Research-only. Stores the raw API response and provenance in the ignored
private environmental cache; it never writes model/app artifacts.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from environmental_sources import PUBLIC, ROOT


ENDPOINT = "https://previous-runs-api.open-meteo.com/v1/forecast"
GEOGRAPHY = PUBLIC / "geography.json"
PRIVATE = PUBLIC / "private"
VARIABLES = (
    "temperature_2m_previous_day1",
    "relative_humidity_2m_previous_day1",
    "wind_speed_10m_previous_day1",
    "precipitation_previous_day1",
)
EXPERIMENT = "openmeteo-gfs-previous-runs-argentina-trails"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-01", help="First valid date, UTC")
    parser.add_argument("--end", default="2026-02-01", help="Exclusive last valid date, UTC")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--model", choices=("gfs_seamless", "jma_gsm"), default="gfs_seamless",
                        help="Archived global forecast model (default: gfs_seamless).")
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if start >= end:
        parser.error("--start must precede exclusive --end")

    geography = json.loads(GEOGRAPHY.read_text(encoding="utf-8"))
    regions = geography.get("fire_regions") or geography.get("regions")
    if not isinstance(regions, list) or not regions:
        raise ValueError("Expected Argentine fire-region coordinates in geography.json")
    regions = [r for r in regions if r.get("latitude") is not None and r.get("longitude") is not None]
    if not regions:
        raise ValueError("No regions have valid coordinates")

    params = {
        "latitude": ",".join(str(r["latitude"]) for r in regions),
        "longitude": ",".join(str(r["longitude"]) for r in regions),
        "hourly": ",".join(VARIABLES),
        "models": args.model,
        "start_date": start.isoformat(),
        "end_date": (end - timedelta(days=1)).isoformat(),
        "timezone": "UTC",
        "timeformat": "iso8601",
        "cell_selection": "land",
    }
    url = ENDPOINT + "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "MiSendero-research/1.0", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=args.timeout) as response:
            raw = response.read()
            status = response.status
    except (HTTPError, URLError, TimeoutError) as exc:
        raise SystemExit(f"Open-Meteo request failed; no dataset written: {exc}") from exc
    if status != 200:
        raise SystemExit(f"Open-Meteo returned HTTP {status}; no dataset written")

    parsed = json.loads(raw)
    locations = parsed if isinstance(parsed, list) else [parsed]
    if len(locations) != len(regions):
        raise ValueError(f"Expected {len(regions)} point responses, received {len(locations)}")
    summary = []
    for region, item in zip(regions, locations):
        hourly = item.get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            raise ValueError(f"No hourly timestamps returned for {region.get('name')}")
        missing = [name for name in VARIABLES if len(hourly.get(name, [])) != len(times)]
        if missing:
            raise ValueError(f"Missing or misaligned variables for {region.get('name')}: {missing}")
        summary.append({
            "region": region.get("name"),
            "requested_latitude": region["latitude"],
            "requested_longitude": region["longitude"],
            "returned_latitude": item.get("latitude"),
            "returned_longitude": item.get("longitude"),
            "grid_elevation_m": item.get("elevation"),
            "hours": len(times),
            "missing_by_variable": {
                name: sum(value is None for value in hourly[name]) for name in VARIABLES
            },
        })

    output_dir = PRIVATE
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"{start.isoformat()}-{end.isoformat()}"
    experiment = EXPERIMENT if args.model == "gfs_seamless" else f"{EXPERIMENT}-{args.model}"
    output_path = output_dir / f"{experiment}-{suffix}.json.gz"
    manifest_path = output_dir / f"{experiment}-{suffix}-manifest.json"
    if output_path.exists() or manifest_path.exists():
        raise SystemExit(f"Refusing to overwrite an existing acquisition: {output_path}")
    compressed = gzip.compress(raw, mtime=0)
    output_path.write_bytes(compressed)
    manifest = {
        "experiment_id": experiment,
        "source": f"Open-Meteo Previous Runs API, {args.model}",
        "source_url": ENDPOINT,
        "request_parameters": {key: value for key, value in params.items() if key not in ("latitude", "longitude")},
        "forecast_lead_hours": 24,
        "valid_period_utc": {"start_inclusive": start.isoformat(), "end_exclusive": end.isoformat()},
        "variables": list(VARIABLES),
        "requested_region_count": len(regions),
        "locations": summary,
        "raw_response_sha256": sha256(raw),
        "compressed_response_sha256": sha256(compressed),
        "compressed_response_bytes": len(compressed),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_terms_note": "Research acquisition. Check current Open-Meteo/API and upstream model licences before redistribution or commercial use; cite Open-Meteo.",
        "deployment_approved": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": output_path.relative_to(ROOT).as_posix(),
        "manifest": manifest_path.relative_to(ROOT).as_posix(),
        "raw_response_sha256": manifest["raw_response_sha256"],
        "compressed_response_bytes": len(compressed),
        "locations": summary,
    }, indent=2))


if __name__ == "__main__":
    main()
