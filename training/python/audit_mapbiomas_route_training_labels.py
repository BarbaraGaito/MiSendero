"""Audit public MapBiomas object-training labels near Argentine trail centers.

This reports coverage only. These curated labels are not an exhaustive fire
inventory and must not be used as negatives for unlabelled space or time.
"""
import csv
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from environmental_sources import ROOT, sha256


SOURCE = ROOT / "training/data/environmental/private/mapbiomas-polygons-data-merged.csv"
GEOGRAPHY = ROOT / "training/data/environmental/geography.json"
OUTPUT = ROOT / "docs/environmental-models-2026-10-22/mapbiomas-training-label-route-coverage-2026-10-23.json"
RADIUS_KM = 10.0


def main():
    with SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    geography = json.loads(GEOGRAPHY.read_text(encoding="utf-8"))
    class_counts = Counter(row.get("class", "") for row in rows)
    conflict_counts = Counter(row.get("oid_class_conflict", "") for row in rows)
    geom_counts = Counter(row.get("geom_type", "") for row in rows)
    years = sorted({int(row["fire_year"]) for row in rows if row.get("fire_year")})
    routes = []
    for route in geography["fire_regions"]:
        lat, lon = float(route["latitude"]), float(route["longitude"])
        matches = []
        for row in rows:
            if not row.get("lon") or not row.get("lat"):
                continue
            dx = (float(row["lon"]) - lon) * 111.320 * math.cos(math.radians(lat))
            dy = (float(row["lat"]) - lat) * 110.574
            distance_km = math.hypot(dx, dy)
            if distance_km <= RADIUS_KM:
                matches.append((row, distance_km))
        unambiguous = [(row, distance) for row, distance in matches
            if row.get("oid_class_conflict", "").upper() != "TRUE" and row.get("class") in {"0", "1"}]
        routes.append({
            "route_center": route["name"],
            "radius_km": RADIUS_KM,
            "matched_rows": len(matches),
            "distinct_oids": len({row.get("oid") for row, _ in matches if row.get("oid")}),
            "ambiguous_conflict_rows": sum(row.get("oid_class_conflict", "").upper() == "TRUE" for row, _ in matches),
            "unambiguous_class_counts": dict(sorted(Counter(row["class"] for row, _ in unambiguous).items())),
            "distinct_fire_years": sorted({int(row["fire_year"]) for row, _ in unambiguous if row.get("fire_year")}),
            "nearest_sample_distance_km": round(min((distance for _, distance in matches), default=float("nan")), 3) if matches else None,
        })

    report = {
        "experiment_id": "mapbiomas-curated-object-training-label-route-coverage",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": "MapBiomas Argentina Fire Collection 1 merged object-label training table",
        "source_url": "https://drive.google.com/drive/folders/1hmWZWkX1iHcGAGvqtv-5JSynvLnPx7wX",
        "source_file": SOURCE.relative_to(ROOT).as_posix(),
        "source_sha256": sha256(SOURCE),
        "geography_sha256": sha256(GEOGRAPHY),
        "spatial_rule": "Representative lon/lat from each labeled feature within 10 km of the catalog route center; local equirectangular approximation, not full route geometry.",
        "coverage": {
            "rows": len(rows),
            "classes": dict(sorted(class_counts.items())),
            "object_class_conflicts": dict(sorted(conflict_counts.items())),
            "geometry_types": dict(sorted(geom_counts.items())),
            "fire_year_min": min(years) if years else None,
            "fire_year_max": max(years) if years else None,
            "route_centers_with_any_labeled_sample_within_10km": sum(bool(row["matched_rows"]) for row in routes),
            "route_centers_with_both_classes_within_10km": sum(set(row["unambiguous_class_counts"]) == {"0", "1"} for row in routes),
        },
        "routes": routes,
        "limitations": [
            "Curated objects are selected to train or review the MapBiomas burned-area product; they are not a census of fires or a random sample of route-days.",
            "Class 0 is a labeled object, not evidence that the surrounding route and date had no fire.",
            "The source product is based on Landsat and its own classification workflow; labels are not field-confirmed event reports.",
            "No model probabilities or performance metrics are calculated by this coverage audit.",
            "The 10 km center buffer is an approximate association and can include events outside the trail itself.",
        ],
        "synthetic_observations": 0,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": OUTPUT.relative_to(ROOT).as_posix(), "coverage": report["coverage"], "routes": routes}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
