#!/usr/bin/env python3
"""Archive compact, route-level snapshots of INPE's public fire forecasts.

The public directory exposes only the latest T0-T3 GeoTIFFs. This script
captures their issue/validity metadata and samples the eight Argentine route
centers from geography.json, plus exploratory 5 km and 10 km neighborhoods.
It stores only JSON; downloaded rasters are temporary and removed afterward.

Run daily to build a prospective forecast archive. These scores are danger
indices, not calibrated probabilities of ignition. See the accompanying audit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.windows import from_bounds


BASE_URL = (
    "https://dataserver-coids.inpe.br/queimadas/queimadas/"
    "riscofogo_meteorologia/previsto/risco_fogo"
)
ROOT = Path(__file__).resolve().parents[2]
GEOGRAPHY_PATH = ROOT / "training/data/environmental/geography.json"
OUTPUT_DIR = ROOT / "training/data/environmental/inpe_fire_forecasts"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def raster_stats(dataset: rasterio.DatasetReader, lon: float, lat: float,
                 radius_km: float) -> dict[str, Any]:
    if radius_km == 0:
        sample = next(dataset.sample([(lon, lat)], masked=True))[0]
        if np.ma.is_masked(sample):
            return {"n": 0, "value": None}
        return {"n": 1, "value": round(float(sample), 6)}

    dlat = radius_km / 110.574
    dlon = radius_km / (111.320 * max(math.cos(math.radians(lat)), 0.01))
    window = from_bounds(
        lon - dlon, lat - dlat, lon + dlon, lat + dlat, dataset.transform
    ).round_offsets().round_lengths()
    values = dataset.read(1, window=window, masked=True).astype("float64")
    array = np.asarray(values.filled(np.nan))
    rows, cols = np.indices(array.shape)
    transform = dataset.window_transform(window)
    xs = transform.c + (cols + 0.5) * transform.a + (rows + 0.5) * transform.b
    ys = transform.f + (cols + 0.5) * transform.d + (rows + 0.5) * transform.e
    distance = np.sqrt(
        ((ys - lat) * 110.574) ** 2
        + ((xs - lon) * 111.320 * math.cos(math.radians(lat))) ** 2
    )
    array = np.where(distance <= radius_km, array, np.nan)
    if dataset.nodata is not None:
        array = np.where(array == dataset.nodata, np.nan, array)
    valid = array[np.isfinite(array)]
    if not valid.size:
        return {"n": 0, "median": None, "p90": None, "max": None}
    return {
        "n": int(valid.size),
        "median": round(float(np.median(valid)), 6),
        "p90": round(float(np.quantile(valid, 0.9)), 6),
        "max": round(float(np.max(valid)), 6),
        "fraction_ge_0_7": round(float(np.mean(valid >= 0.7)), 6),
        "fraction_ge_0_95": round(float(np.mean(valid >= 0.95)), 6),
    }


def extract_run_time(tags: dict[str, str]) -> str | None:
    match = re.search(r"/netcdf/(\d{10})/", tags.get("NC_GLOBAL#history", ""))
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y%m%d%H").replace(
        tzinfo=timezone.utc
    ).isoformat().replace("+00:00", "Z")


def download_raster_to_temp(request: urllib.request.Request, attempts: int = 3) -> tuple[Path, str | None]:
    """Download one forecast raster with bounded retries and clean partial files."""
    for attempt in range(attempts):
        temp_path = None
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                last_modified = response.headers.get("Last-Modified")
                with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as handle:
                    temp_path = Path(handle.name)
                    while block := response.read(1024 * 1024):
                        handle.write(block)
            return temp_path, last_modified
        except Exception:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            if attempt + 1 == attempts:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("download attempts must be greater than zero")


def capture_raster(path: Path, horizon: str, source_url: str,
                   last_modified: str | None, regions: list[dict[str, Any]]) -> dict[str, Any]:
    with rasterio.open(path) as dataset:
        tags = dataset.tags()
        bands = dataset.tags(1)
        routes = []
        for route in regions:
            lon, lat = float(route["longitude"]), float(route["latitude"])
            routes.append({
                "name": route["name"],
                "location": route.get("location"),
                "latitude": lat,
                "longitude": lon,
                "geometry_sha256": route.get("geometry_sha256"),
                "sample": {
                    "point": raster_stats(dataset, lon, lat, 0),
                    "radius_5km": raster_stats(dataset, lon, lat, 5),
                    "radius_10km": raster_stats(dataset, lon, lat, 10),
                },
            })
        history = tags.get("NC_GLOBAL#history", "")
        valid_match = re.search(r"(\d{4}-\d{2}-\d{2},\d{2}:\d{2}:\d{2})", history)
        return {
            "horizon_file": f"RF.PREV.{horizon}.tif",
            "source_url": source_url,
            "http_last_modified": last_modified,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "forecast_run_utc": extract_run_time(tags),
            "forecast_valid_utc": (
                datetime.strptime(valid_match.group(1), "%Y-%m-%d,%H:%M:%S")
                .replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
                if valid_match else None
            ),
            "title": tags.get("NC_GLOBAL#title"),
            "creation_date": tags.get("NC_GLOBAL#creation_date"),
            "raster": {
                "crs": str(dataset.crs),
                "bounds": [round(float(v), 8) for v in dataset.bounds],
                "resolution_degrees": [float(v) for v in dataset.res],
                "width": dataset.width,
                "height": dataset.height,
                "nodata": dataset.nodata,
                "band_variable": bands.get("NETCDF_VARNAME"),
            },
            "routes": routes,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raster", type=Path,
                        help="Use one local GeoTIFF instead of downloading the latest T0-T3")
    parser.add_argument("--horizon", choices=["T0", "T1", "T2", "T3"],
                        help="Required with --raster")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    if bool(args.raster) != bool(args.horizon):
        parser.error("--raster and --horizon must be supplied together")

    geography = json.loads(GEOGRAPHY_PATH.read_text(encoding="utf-8"))
    regions = geography["fire_regions"]
    capture_time = datetime.now(timezone.utc).replace(microsecond=0)
    results = []
    acquisition_errors = []
    if args.raster:
        results.append(capture_raster(
            args.raster, args.horizon, "local-file", None, regions
        ))
    else:
        for horizon in ("T0", "T1", "T2", "T3"):
            url = f"{BASE_URL}/RF.PREV.{horizon}.tif"
            request = urllib.request.Request(url, headers={"User-Agent": "MiSenderoResearch/1.0"})
            temp_path = None
            try:
                # The public endpoint occasionally resets HTTPS connections.
                # Retry each horizon independently so one failed file does not
                # discard the other valid forecast rasters from this capture.
                temp_path, last_modified = download_raster_to_temp(request)
            except Exception as exc:
                acquisition_errors.append({
                    "horizon": horizon,
                    "source_url": url,
                    "stage": "download",
                    "attempts": 3,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                continue
            try:
                results.append(capture_raster(temp_path, horizon, url, last_modified, regions))
            except Exception as exc:
                acquisition_errors.append({
                    "horizon": horizon,
                    "source_url": url,
                    "stage": "raster_processing",
                    "attempts": 1,
                    "error": f"{type(exc).__name__}: {exc}",
                })
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)

    if not results:
        print(json.dumps({"captured_forecasts": 0, "acquisition_errors": acquisition_errors}, indent=2))
        return 1

    # The public endpoint can keep serving the same issued run across several
    # captures. Store each horizon/run/raster only once so repeated polling does
    # not inflate the apparent prospective sample size.
    existing = set()
    for archived in args.output_dir.glob("capture_*.json"):
        try:
            previous = json.loads(archived.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for forecast in previous.get("forecasts", []):
            existing.add((forecast.get("horizon_file"), forecast.get("forecast_run_utc"),
                          forecast.get("forecast_valid_utc"), forecast.get("sha256")))
    fresh_results = [forecast for forecast in results
        if (forecast.get("horizon_file"), forecast.get("forecast_run_utc"),
            forecast.get("forecast_valid_utc"), forecast.get("sha256")) not in existing]
    if not fresh_results:
        print("No new INPE forecast run or raster; duplicate capture skipped.")
        return 0

    record = {
        "schema_version": 1,
        "captured_at_utc": capture_time.isoformat().replace("+00:00", "Z"),
        "source": "INPE Risco de Fogo previsto (public latest T0-T3 files)",
        "geography_file": "training/data/environmental/geography.json",
        "geography_sha256": sha256_file(GEOGRAPHY_PATH),
        "extraction": {
            "point": "pixel at route center coordinate",
            "radius_km": [5, 10],
            "distance_approximation": "local equirectangular distance from pixel center",
            "warning": "Route centers and radius buffers are proxies, not trail geometries.",
        },
        "forecasts": fresh_results,
        "interpretation": "INPE fire-danger score; not a calibrated probability of ignition or route incident.",
    }
    if acquisition_errors:
        record["acquisition_errors"] = acquisition_errors
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"capture_{capture_time.strftime('%Y%m%dT%H%M%SZ')}.json"
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    print(f"Captured {len(fresh_results)} new forecast raster(s) for {len(regions)} routes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
