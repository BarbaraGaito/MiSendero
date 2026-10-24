"""Archive fixed-lead JMA GSM forecasts at representative in-app trail points.

Research-only acquisition. One midpoint per route is derived from the supplied
OpenStreetMap route geometry; route locations and provenance are stored with
the raw Open-Meteo Previous Runs response in the ignored private cache.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from environmental_sources import ROOT

ROUTE_FILES = (ROOT / "backend/src/data/additionalTrailRoutes.json",
               ROOT / "backend/src/data/catalogExpansionRoutes20261017.json")
PRIVATE = ROOT / "training/data/environmental/private"
ENDPOINT = "https://previous-runs-api.open-meteo.com/v1/forecast"
VARIABLES = ("temperature_2m_previous_day1", "relative_humidity_2m_previous_day1",
             "wind_speed_10m_previous_day1", "precipitation_previous_day1")


def route_midpoint(points: list[list[float]]) -> tuple[float, float]:
    segments = []
    total = 0.0
    for first, second in zip(points, points[1:]):
        lat1, lon1 = first
        lat2, lon2 = second
        mean_lat = math.radians((lat1 + lat2) / 2)
        dx = (lon2 - lon1) * 111_320 * math.cos(mean_lat)
        dy = (lat2 - lat1) * 110_574
        length = math.hypot(dx, dy)
        segments.append((first, second, length))
        total += length
    if total <= 0:
        raise ValueError("Route geometry has no measurable length")
    target, covered = total / 2, 0.0
    for first, second, length in segments:
        if covered + length >= target:
            ratio = (target - covered) / length if length else 0.0
            return (first[0] + (second[0] - first[0]) * ratio,
                    first[1] + (second[1] - first[1]) * ratio)
        covered += length
    return tuple(points[-1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default="2024-01-01", help="Exclusive UTC date")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if start >= end:
        parser.error("--start must precede --end")
    routes = {}
    for path in ROUTE_FILES:
        for name, route in json.loads(path.read_text(encoding="utf-8")).items():
            if len(route.get("points") or []) < 2 or not route.get("source_url"):
                raise ValueError(f"Route lacks sourced geometry: {name}")
            routes[name] = route
    ordered = sorted(routes.items())
    coordinates = [route_midpoint(route["points"]) for _, route in ordered]
    params = {
        "latitude": ",".join(f"{lat:.6f}" for lat, _ in coordinates),
        "longitude": ",".join(f"{lon:.6f}" for _, lon in coordinates),
        "hourly": ",".join(VARIABLES), "models": "jma_gsm",
        "start_date": start.isoformat(), "end_date": (end - timedelta(days=1)).isoformat(),
        "timezone": "UTC", "timeformat": "iso8601", "cell_selection": "land",
    }
    request = Request(ENDPOINT + "?" + urlencode(params), headers={
        "User-Agent": "MiSendero-thesis-research/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=args.timeout) as response:
        raw, status = response.read(), response.status
    if status != 200:
        raise RuntimeError(f"Open-Meteo returned HTTP {status}")
    locations = json.loads(raw)
    if not isinstance(locations, list) or len(locations) != len(ordered):
        raise ValueError(f"Expected {len(ordered)} location responses")
    summaries = []
    for (name, route), (lat, lon), response in zip(ordered, coordinates, locations):
        hourly = response.get("hourly", {})
        times = hourly.get("time", [])
        if not times or any(len(hourly.get(variable, [])) != len(times) for variable in VARIABLES):
            raise ValueError(f"Missing or misaligned forecast values for route {name}")
        summaries.append({"route_id": name, "source_url": route["source_url"],
            "route_midpoint_latitude": lat, "route_midpoint_longitude": lon,
            "returned_latitude": response.get("latitude"),
            "returned_longitude": response.get("longitude"),
            "grid_elevation_m": response.get("elevation"), "hours": len(times),
            "missing_by_variable": {v: sum(value is None for value in hourly[v]) for v in VARIABLES}})
    PRIVATE.mkdir(parents=True, exist_ok=True)
    suffix = f"{start.isoformat()}-{end.isoformat()}"
    output = PRIVATE / f"openmeteo-jma-gsm-trail-midpoints-{suffix}.json.gz"
    manifest_path = PRIVATE / f"openmeteo-jma-gsm-trail-midpoints-{suffix}-manifest.json"
    if output.exists() or manifest_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing acquisition: {output.name}")
    compressed = gzip.compress(raw, mtime=0)
    output.write_bytes(compressed)
    manifest = {"experiment_id": "jma-gsm-in-app-trail-midpoint-weather-archive",
        "source": "Open-Meteo Previous Runs API, jma_gsm",
        "source_url": ENDPOINT, "forecast_lead_hours": 24,
        "valid_period_utc": {"start_inclusive": start.isoformat(), "end_exclusive": end.isoformat()},
        "variables": list(VARIABLES), "route_count": len(ordered), "locations": summaries,
        "route_files_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in ROUTE_FILES},
        "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_response_sha256": hashlib.sha256(compressed).hexdigest(),
        "compressed_response_bytes": len(compressed),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "limitations": ["One route midpoint represents each whole route and can miss local weather variation.",
            "Forecasts are archived model outputs, not observations or fire labels.",
            "Check Open-Meteo and upstream model terms before redistribution or deployment."],
        "deployment_approved": False}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"archive": output.relative_to(ROOT).as_posix(),
        "manifest": manifest_path.relative_to(ROOT).as_posix(),
        "sha256": manifest["compressed_response_sha256"], "route_count": len(ordered),
        "rows_per_location": sorted({item["hours"] for item in summaries}),
        "missing_values": {name: sum(row["missing_by_variable"][name] for row in summaries)
                           for name in VARIABLES}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
