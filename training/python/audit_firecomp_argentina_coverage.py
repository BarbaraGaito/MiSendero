"""Check whether FireComp's held-out South America samples reach MiSendero routes.

The full FireComp HDF5 dataset is very large. This audit uses only its small
test/index metadata to decide whether a regional evaluation is feasible; it
does not evaluate predictions or claim fire/no-fire outcomes.
"""
from __future__ import annotations

import json
import math
import subprocess
from collections import defaultdict
from pathlib import Path

from environmental_sources import ROOT, sha256

PRIVATE = ROOT / "training/data/environmental/private/firecomp-metadata"
TRAILS = ROOT / "training/data/environmental/private/firecomp_all_argentine_trails.json"
OUT = ROOT / "docs/environmental-models-2026-10-22/fire-firecomp-argentina-route-coverage.json"
TEST = PRIVATE / "next_day_v3_splits_test.jsonl"
SHARDS = [PRIVATE / f"dataset_{i}.json" for i in range(8)]
ROUTE_EXPORT_JS = r"""
const fs = require('fs');
const a = require('./backend/src/data/realTrailRoutes.js');
const b = require('./backend/src/data/additionalTrailRoutes.json');
const c = require('./backend/src/data/catalogExpansionRoutes20261017.json');
const routes = [
  ...Object.entries(a).map(([name, route_coordinates]) => ({name, route_coordinates})),
  ...Object.entries(b).map(([name, v]) => ({name, route_coordinates: v.points})),
  ...Object.entries(c).map(([name, v]) => ({name, route_coordinates: v.points})),
];
fs.writeFileSync('training/data/environmental/private/firecomp_all_argentine_trails.json', JSON.stringify(routes));
"""

# MiSendero route traces are short relative to the Earth. Equirectangular
# distances at -35° latitude are sufficient for a conservative 70 km patch
# intersection screen (FireComp patches are 256 x 375 m, about 96 km wide).
LATITUDE_REFERENCE = -35.0
KM_PER_DEGREE = 111.32
PATCH_HALF_DIAGONAL_KM = math.sqrt(2) * 256 * 0.375 / 2


def distance_to_trace_km(lat: float, lon: float, trace: list[list[float]]) -> float:
    scale_lon = math.cos(math.radians(LATITUDE_REFERENCE))
    x = lon * scale_lon
    best = math.inf
    for route_lat, route_lon in trace:
        dx = (lon - route_lon) * scale_lon
        dy = lat - route_lat
        best = min(best, math.hypot(dx, dy) * KM_PER_DEGREE)
    return best


def main() -> None:
    required = [TEST, *SHARDS]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Missing FireComp coverage metadata. Run acquire_firecomp_coverage_metadata.py first: "
            + ", ".join(missing)
        )

    subprocess.run(["node", "-e", ROUTE_EXPORT_JS], cwd=ROOT, check=True)

    test_rows = [json.loads(line) for line in TEST.read_text(encoding="utf-8").splitlines() if line.strip()]
    south_america_test = [row for row in test_rows if row.get("region_id") == 9]
    argentina_bbox_rows = [
        row for row in south_america_test
        if -56 <= row["lat"] <= -20 and -75 <= row["lon"] <= -52
    ]
    routes = json.loads(TRAILS.read_text(encoding="utf-8"))

    nearby: dict[str, list[dict]] = defaultdict(list)
    candidates = []
    for row in argentina_bbox_rows:
        distances = [
            (distance_to_trace_km(row["lat"], row["lon"], route["route_coordinates"]), route["name"])
            for route in routes
        ]
        distance, route_name = min(distances)
        if distance <= 70:
            item = {**row, "nearest_route": route_name, "nearest_route_vertex_km": distance}
            candidates.append(item)
            nearby[route_name].append(item)

    # Resolve each candidate to the HDF5 shard whose metadata owns its sample
    # index. Do not download or read the multi-GB HDF5 shard in this audit.
    candidate_ids = {row["fire_id"] for row in candidates}
    owners = {}
    for path in SHARDS:
        metadata = json.loads(path.read_text(encoding="utf-8"))
        for item in metadata:
            if item.get("fire_id") in candidate_ids:
                owners.setdefault(item["fire_id"], []).append({
                    "shard": path.name,
                    "idx": item.get("idx"),
                    "date": item.get("dt"),
                    "region_id": item.get("region_id"),
                    "lat": item.get("lat"),
                    "lon": item.get("lon"),
                })

    per_route = []
    for route_name, rows in sorted(nearby.items()):
        unique_events = {row["fire_id"] for row in rows}
        per_route.append({
            "route": route_name,
            "test_sample_rows": len(rows),
            "unique_fire_ids": len(unique_events),
            "unique_target_dates": len({row["dt"] for row in rows}),
            "nearest_route_vertex_km": min(row["nearest_route_vertex_km"] for row in rows),
            "events": [
                {
                    "fire_id": fire_id,
                    "dates": sorted({row["dt"] for row in rows if row["fire_id"] == fire_id}),
                    "test_indices": sorted({row["idx"] for row in rows if row["fire_id"] == fire_id}),
                    "shard_metadata": owners.get(fire_id, []),
                }
                for fire_id in sorted(unique_events)
            ],
        })

    result = {
        "experiment_id": "firecomp-heldout-south-america-mi-sendero-route-coverage-audit",
        "status": "coverage_screen_only",
        "dataset": "FireComp next-day VIIRS fire-spread benchmark, public test split",
        "test_split_rows": len(test_rows),
        "south_america_test_rows": len(south_america_test),
        "south_america_rows_inside_argentina_bounding_box": len(argentina_bbox_rows),
        "route_geometry_count": len(routes),
        "route_vertex_distance_screen_km": 70,
        "patch_half_diagonal_km": PATCH_HALF_DIAGONAL_KM,
        "candidate_test_rows_near_argentine_routes": len(candidates),
        "candidate_unique_fire_ids": len(candidate_ids),
        "per_route": per_route,
        "sources_sha256": {
            "test_split": sha256(TEST),
            "route_geometry": sha256(TRAILS),
            **{path.name: sha256(path) for path in SHARDS},
        },
        "limitations": [
            "A sample center within 70 km is only a conservative patch-intersection candidate, not proof that its pixel grid overlaps the trail.",
            "The South America region is not synonymous with Argentina; the bounding box is only a preliminary filter.",
            "No HDF5 pixels were read and no FireComp model or baseline was evaluated.",
            "FireComp predicts next-day spread from an already active fire; it does not predict ignition.",
            "One or a few nearby independent fires cannot support a reliable precision estimate.",
        ],
        "synthetic_observations": 0,
        "prediction_evaluated": False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "sources_sha256"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
