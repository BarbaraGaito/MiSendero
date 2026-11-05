"""Inspect an official FireCCI51 monthly tile around MiSendero route centers.

This is a label-coverage audit only. It does not fit or approve a predictor.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from datetime import date, timedelta

import numpy as np
import rasterio
from rasterio.windows import from_bounds

from environmental_sources import PUBLIC, ROOT, sha256


DEFAULT_DIR = ROOT / "training/data/environmental/private/firecci51/2022"
DEFAULT_OUT = ROOT / "docs/environmental-models-2026-10-22/firecci51-route-sample-2022-fire-season.json"
TILE_URL = "https://dap.ceda.ac.uk/neodc/esacci/fire/data/burned_area/MODIS/pixel/v5.1/compressed/2022/"
SNMF_MBURUCUYA = {
    "name": "PN MBURUCUYA",
    "latitude": -(28 + 2 / 60 + 44 / 3600),
    "longitude": -(58 + 0 / 60 + 37 / 3600),
    "reported_start_date": "2022-02-22",
    "reported_extinguished_date": "2022-03-08",
    "source_report_date": "2022-03-09",
    "source_url": "https://www.argentina.gob.ar/sites/default/files/2021/09/reporte_diario_09-03-2022.pdf",
    "radius_km": 10.0,
    "date_margin_days": 3,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--radius-km", type=float, default=10.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if args.radius_km <= 0:
        raise ValueError("radius-km must be positive")

    jd_paths = sorted(args.data_dir.glob("*-ESACCI-L3S_FIRE-BA-MODIS-AREA_2-fv5.1-JD.tif"))
    if not jd_paths:
        raise FileNotFoundError(f"No extracted South America FireCCI JD tiles under {args.data_dir}")
    geography = json.loads((PUBLIC / "geography.json").read_text(encoding="utf-8"))
    rows = []
    event_rows = []
    for jd_path in jd_paths:
        cl_path = jd_path.with_name(jd_path.name.replace("-JD.tif", "-CL.tif"))
        archive = jd_path.with_name(jd_path.name.replace("-JD.tif", ".tar.gz"))
        if not cl_path.exists() or not archive.exists():
            raise FileNotFoundError(f"Missing paired confidence raster or source archive for {jd_path.name}")
        with rasterio.open(jd_path) as jd, rasterio.open(cl_path) as cl:
            if jd.crs != cl.crs or jd.transform != cl.transform or jd.shape != cl.shape:
                raise ValueError(f"FireCCI JD/CL rasters do not align: {jd_path.name}")
            for route in geography["fire_regions"]:
                lat, lon = route["latitude"], route["longitude"]
                lat_pad = args.radius_km / 110.574
                lon_pad = args.radius_km / (111.320 * max(0.2, math.cos(math.radians(lat))))
                window = from_bounds(lon - lon_pad, lat - lat_pad, lon + lon_pad, lat + lat_pad,
                    transform=jd.transform).round_offsets().round_lengths()
                values = jd.read(1, window=window)
                confidence = cl.read(1, window=window)
                transform = jd.window_transform(window)
                row_idx, col_idx = np.indices(values.shape)
                xs = transform.c + (col_idx + 0.5) * transform.a
                ys = transform.f + (row_idx + 0.5) * transform.e
                dx = (xs - lon) * 111.320 * math.cos(math.radians(lat))
                dy = (ys - lat) * 110.574
                inside = dx * dx + dy * dy <= args.radius_km ** 2
                selected = values[inside]
                selected_conf = confidence[inside]
                positive = selected > 0
                class_counts = {str(value): int(np.count_nonzero(selected == value))
                    for value in (-2, -1, 0)}
                class_counts["burned_pixel_count"] = int(np.count_nonzero(positive))
                burned_conf = selected_conf[positive]
                conf_bins = {"1_49": int(np.count_nonzero((burned_conf >= 1) & (burned_conf < 50))),
                    "50_79": int(np.count_nonzero((burned_conf >= 50) & (burned_conf < 80))),
                    "80_100": int(np.count_nonzero((burned_conf >= 80) & (burned_conf <= 100))),
                    "outside_1_100": int(np.count_nonzero((burned_conf < 1) | (burned_conf > 100)))}
                burn_days = []
                for doy in np.unique(selected[positive]):
                    date_text = (date(2022, 1, 1) + timedelta(days=int(doy) - 1)).isoformat()
                    burn_days.append({"date": date_text, "pixels": int(np.count_nonzero(selected == doy)),
                        "confidence_ge_80_pixels": int(np.count_nonzero((selected == doy) & (selected_conf >= 80)))})
                rows.append({"month": jd_path.name[:6], "route_center": route["name"],
                    "location": route["location"], "radius_km": args.radius_km,
                    "sampled_pixel_count": int(selected.size), "jd_class_counts": class_counts,
                    "burned_confidence_bins": conf_bins, "burn_days": burn_days,
                    "source_hashes": {"archive_sha256": sha256(archive),
                        "jd_sha256": sha256(jd_path), "cl_sha256": sha256(cl_path)}})

            if jd_path.name.startswith(("202202", "202203")):
                event = SNMF_MBURUCUYA
                lat, lon, radius = event["latitude"], event["longitude"], event["radius_km"]
                lat_pad = radius / 110.574
                lon_pad = radius / (111.320 * max(0.2, math.cos(math.radians(lat))))
                window = from_bounds(lon - lon_pad, lat - lat_pad, lon + lon_pad, lat + lat_pad,
                    transform=jd.transform).round_offsets().round_lengths()
                values = jd.read(1, window=window)
                confidence = cl.read(1, window=window)
                transform = jd.window_transform(window)
                row_idx, col_idx = np.indices(values.shape)
                xs = transform.c + (col_idx + 0.5) * transform.a
                ys = transform.f + (row_idx + 0.5) * transform.e
                dx = (xs - lon) * 111.320 * math.cos(math.radians(lat))
                dy = (ys - lat) * 110.574
                distance = np.sqrt(dx * dx + dy * dy)
                positive = (values > 0) & (distance <= radius)
                event_start = date.fromisoformat(event["reported_start_date"])
                event_end = date.fromisoformat(event["reported_extinguished_date"])
                lower = event_start - timedelta(days=event["date_margin_days"])
                upper = event_end + timedelta(days=event["date_margin_days"])
                dated = []
                for doy in np.unique(values[positive]):
                    burn_date = date(2022, 1, 1) + timedelta(days=int(doy) - 1)
                    if lower <= burn_date <= upper:
                        mask = positive & (values == doy)
                        distances = distance[mask]
                        dated.append({"burn_date": burn_date.isoformat(),
                            "pixels_within_radius": int(mask.sum()),
                            "confidence_ge_80_pixels": int(np.count_nonzero(confidence[mask] >= 80)),
                            "nearest_pixel_distance_km": round(float(distances.min()), 3)})
                event_rows.append({"month": jd_path.name[:6], "event": event,
                    "comparison_window": [lower.isoformat(), upper.isoformat()],
                    "positive_pixels_within_radius_and_window": sum(item["pixels_within_radius"] for item in dated),
                    "date_matches": dated,
                    "source_hashes": {"archive_sha256": sha256(archive),
                        "jd_sha256": sha256(jd_path), "cl_sha256": sha256(cl_path)}})

    report = {"experiment_id": "firecci51-route-month-label-coverage-audit",
        "dataset": "ESA Fire_cci MODIS burned-area pixel product v5.1, South America tile AREA_2",
        "source_url": TILE_URL, "periods": sorted({row["month"][:4] + "-" + row["month"][4:] for row in rows}),
        "product_note": "JD is the day of year of first burn detection; 0 means not burned in the month, -1 not observed, and -2 non-burnable. CL is the product's burned-pixel confidence score, not model probability.",
        "spatial_rule": "Great-circle local approximation within a fixed radius of route-sector centers; not the full trail geometry.",
        "routes": rows, "official_event_crosscheck": event_rows,
        "limitations": ["Single month is only a source usability/coverage audit, not a model evaluation.",
            "Monthly burned-area mapping does not identify fire start time or prove that a fire was active at a particular hour.",
            "A mapped unburned pixel is a negative only for mapped burned area within this month and product limitations; it is not a comprehensive fire-free observation.",
            "FireCCI51 uses MODIS observations and includes MODIS active-fire information, so it is not fully sensor-independent from a MODIS-based predictor.",
            "Route centers and radius are approximations; the next experiment must use trail geometries and a held-out year."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": args.output.relative_to(ROOT).as_posix(), "routes": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
