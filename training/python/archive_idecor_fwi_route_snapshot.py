#!/usr/bin/env python3
"""Archive the public Córdoba OHMC/IDECOR FWI forecast at a real MiSendero route.

This is a prospective evidence collector, not a fire-occurrence predictor. The
official map exposes a current-day layer and a next-day layer; this script
stores the next-day forecast values and the HTTP metadata needed to audit them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_URL = "https://mapascordoba.gob.ar/api/v1/config/getMapConfigByNumber/442?token="
ROUTE_URL = "https://gn-idecor.mapascordoba.gob.ar/geoserver/wms"
CATALOG_FILE = ROOT / "training/data/catalog/misendero-catalog.jsonl"
ROUTES_FILE = ROOT / "backend/src/data/additionalTrailRoutes.json"
DEFAULT_OUTPUT_DIR = ROOT / "training/data/environmental/private/idecor-fwi-route-snapshots"
ROUTES = {"condorito": 73, "uritorco": 171}
SAMPLE_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 1.0)
MAP_SIZE = 1024
FIELDS = {
    "Band1": "fwi",
    "Band2": "precipitation_mm",
    "Band3": "wind_kmh",
    "Band4": "relative_humidity_pct",
    "Band5": "temperature_c",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request_bytes(url: str, timeout: int) -> tuple[bytes, dict[str, str]]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "MiSendero-research/1.0", "Accept": "application/json, text/plain"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(), {
                    name: response.headers.get(name, "")
                    for name in ("Date", "Last-Modified", "ETag", "Content-Type")
                }
        except (urllib.error.URLError, TimeoutError, ConnectionResetError):
            if attempt == 2:
                raise
            time.sleep(1 + attempt * 2)
    raise RuntimeError("Unreachable retry state")


def load_route(route_key: str) -> tuple[dict[str, Any], list[list[float]], dict[str, Any], bytes, bytes]:
    catalog_row = next(
        json.loads(line)
        for line in CATALOG_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("trail_id") == ROUTES[route_key]
    )
    if "cordoba" not in catalog_row.get("location", "").lower():
        raise ValueError("The selected route is not in Córdoba, where the FWI layer applies")
    routes_raw = ROUTES_FILE.read_bytes()
    routes = json.loads(routes_raw)
    route = routes[route_key]
    points = route.get("points")
    if not isinstance(points, list) or len(points) < 2:
        raise ValueError("The route geometry must contain at least two points")
    return catalog_row, points, route, routes_raw, CATALOG_FILE.read_bytes()


def haversine_km(a: list[float], b: list[float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(h))


def sample_route(points: list[list[float]]) -> list[dict[str, Any]]:
    lengths = [0.0]
    for previous, current in zip(points, points[1:]):
        lengths.append(lengths[-1] + haversine_km(previous, current))
    total = lengths[-1]
    samples = []
    for fraction in SAMPLE_FRACTIONS:
        target = total * fraction
        index = next((i for i, value in enumerate(lengths) if value >= target), len(points) - 1)
        if index == 0 or lengths[index] == target:
            coordinate = points[index]
        else:
            span = lengths[index] - lengths[index - 1]
            ratio = (target - lengths[index - 1]) / span if span else 0.0
            coordinate = [
                points[index - 1][axis] + ratio * (points[index][axis] - points[index - 1][axis])
                for axis in (0, 1)
            ]
        samples.append({"fraction_along_route": fraction, "latitude": coordinate[0], "longitude": coordinate[1]})
    return samples


def parse_valid_date(title: str) -> str:
    match = re.search(r"(\d{2}/\d{2}/\d{2})", title)
    if not match:
        raise ValueError(f"Cannot identify validity date in official layer title: {title!r}")
    return datetime.strptime(match.group(1), "%d/%m/%y").date().isoformat()


def get_feature_info(
    sample: dict[str, Any], bounds: tuple[float, float, float, float], layer_name: str, timeout: int
) -> tuple[dict[str, float | None], bytes]:
    min_lat, min_lon, max_lat, max_lon = bounds
    # CRS:84 fixes longitude/latitude order and avoids the EPSG:4326 axis-order
    # ambiguity in WMS 1.3.0. The map pixels then align with route coordinates.
    i = min(MAP_SIZE - 1, max(0, int((sample["longitude"] - min_lon) / (max_lon - min_lon) * MAP_SIZE)))
    j = min(MAP_SIZE - 1, max(0, int((max_lat - sample["latitude"]) / (max_lat - min_lat) * MAP_SIZE)))
    params = {
        "service": "WMS",
        "version": "1.3.0",
        "request": "GetFeatureInfo",
        "layers": layer_name,
        "query_layers": layer_name,
        "styles": "sty_fwi",
        "crs": "CRS:84",
        "bbox": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "width": str(MAP_SIZE),
        "height": str(MAP_SIZE),
        "i": str(i),
        "j": str(j),
        "info_format": "text/plain",
        "feature_count": "1",
    }
    raw, _ = request_bytes(ROUTE_URL + "?" + urllib.parse.urlencode(params), timeout)
    text = raw.decode("utf-8", "replace")
    values: dict[str, float | None] = {}
    for band, key in FIELDS.items():
        match = re.search(rf"\b{band}\s*=\s*(-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)", text)
        values[key] = float(match.group(1)) if match else None
    if all(value is None for value in values.values()):
        raise ValueError(f"No numeric FWI values returned for {layer_name}: {text[:300]!r}")
    return values, raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--route-key", choices=sorted(ROUTES), default="condorito",
                        help="In-app Córdoba trail. Run once per route to archive both locations.")
    args = parser.parse_args()

    catalog_row, coordinates, route_data, route_bytes, catalog_bytes = load_route(args.route_key)
    route_samples = sample_route(coordinates)
    lats = [point[0] for point in coordinates]
    lons = [point[1] for point in coordinates]
    bounds = (min(lats) - 0.02, min(lons) - 0.02, max(lats) + 0.02, max(lons) + 0.02)

    config_raw, config_headers = request_bytes(CONFIG_URL, args.timeout)
    config = json.loads(config_raw)
    fwi_layers = [
        layer for layer in config.get("layers", [])
        if layer.get("name") in {"FWI_Geotiff", "FWI_Geotiff_anterior"}
    ]
    by_name = {layer["name"]: layer for layer in fwi_layers}
    if set(by_name) != {"FWI_Geotiff", "FWI_Geotiff_anterior"}:
        raise ValueError("The public map config did not return both current and next-day FWI layers")

    captured_layers = []
    for layer_name in ("FWI_Geotiff_anterior", "FWI_Geotiff"):
        layer = by_name[layer_name]
        samples = []
        for sample in route_samples:
            values, raw = get_feature_info(sample, bounds, layer_name, args.timeout)
            samples.append({
                **sample,
                "values": values,
                "get_feature_info_sha256": sha256(raw),
                "get_feature_info_raw": raw.decode("utf-8", "replace").strip(),
            })
        captured_layers.append({
            "layer_name": layer_name,
            "title": layer.get("title"),
            "valid_date": parse_valid_date(layer.get("title", "")),
            "kind": "current_day" if layer_name.endswith("anterior") else "next_day_forecast",
            "ows_url": layer.get("ows_url"),
            "style": layer.get("style"),
            "attribute_dictionary": layer.get("attributeDictionary", []),
            "samples": samples,
        })

    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    result = {
        "schema_version": 1,
        "source": {
            "name": "OHMC / Mapas Córdoba FWI map 442",
            "map_config_url": CONFIG_URL,
            "map_viewer_url": "https://mapascordoba.gob.ar/viewer/mapa/442",
            "retrieved_at_utc": now,
            "map_config_http_headers": config_headers,
            "map_config_sha256": sha256(config_raw),
            "official_owner": config.get("dataOwner"),
        },
        "route": {
            "trail_id": ROUTES[args.route_key],
            "key": args.route_key,
            "name": catalog_row.get("name"),
            "location": catalog_row.get("location"),
            "geometry_source": "backend/src/data/additionalTrailRoutes.json",
            "geometry_source_sha256": sha256(route_bytes),
            "catalog_source_sha256": sha256(catalog_bytes),
            "coordinate_count": len(coordinates),
            "geometry_bounds_lat_lon": list(bounds),
            "mapping_provenance": {
                key: route_data.get(key)
                for key in ("source", "source_url", "license", "retrieved_at", "ways")
            },
            "catalog_mapping_provenance": catalog_row.get("provenance", {}).get("mapping", {}),
            "official_sources": catalog_row.get("sources", []),
            "sample_method": "five equal-distance points over full mapped polyline",
            "samples_per_layer": len(route_samples),
        },
        "layers": captured_layers,
        "limitations": [
            "FWI is a meteorological fire-behaviour danger index, not a calibrated probability that ignition will occur.",
            "This is one route and one retrieval time; it is not an independent accuracy evaluation.",
            "The public map exposes current-day and next-day layers; historic issued forecasts were not established by this capture.",
            "The five route samples can share the same approximately 4 km grid cell and are not independent observations.",
        ],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"{args.route_key}-{now[:10]}.json"
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing forecast capture: {output.name}")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output.relative_to(ROOT)),
        "forecast_valid_date": next(layer["valid_date"] for layer in captured_layers if layer["kind"] == "next_day_forecast"),
        "current_valid_date": next(layer["valid_date"] for layer in captured_layers if layer["kind"] == "current_day"),
        "sample_fwi": {
            layer["kind"]: [sample["values"]["fwi"] for sample in layer["samples"]]
            for layer in captured_layers
        },
        "sha256": sha256(output.read_bytes()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
