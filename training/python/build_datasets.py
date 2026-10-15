"""Build normalized training CSVs from public dataset exports.

This script keeps the model-facing CSV schemas stable while making dataset
provenance auditable. Raw public downloads stay under `training/data/raw/`
and are not committed. Optional processed public exports can be placed under
`training/data/processed/` using the same normalized schemas documented in
`ai/datasets/README.md`.
"""

from __future__ import annotations

from common.data_policy import require_public_ground_truth
if __name__ == "__main__":
    require_public_ground_truth("legacy_dataset_builder")

import argparse
import csv
import json
import math
import pickle
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from common.privacy import assert_no_restricted_columns

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "training" / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "training" / "data" / "processed"
OSM_ARGENTINA_CACHE_DIR = RAW_DIR / "osm_argentina"

FATIGUE_PATH = REPO_ROOT / "ai" / "datasets" / "fatigue_windows.csv"
PHYSIO_RISK_PATH = REPO_ROOT / "ai" / "datasets" / "physio_risk.csv"
ROUTE_DIFFICULTY_PATH = (
    REPO_ROOT / "training" / "route-difficulty" / "datasets" / "route_difficulty_training.csv"
)

FATIGUE_COLUMNS = ["hr", "speed_kmh", "elapsed_minutes", "hr_reserve_percent", "label"]
RISK_COLUMNS = [
    "hr",
    "spo2",
    "speed_kmh",
    "elapsed_minutes",
    "elevation_gain_m",
    "fatigue_score",
    "label",
]
ROUTE_COLUMNS = [
    "distance_km",
    "elevation_gain_m",
    "avg_slope_percent",
    "max_slope_percent",
    "technical_score",
    "label",
]

PAMAP2_SPEED_BY_ACTIVITY = {
    1: 0.0,   # lying
    2: 0.0,   # sitting
    3: 0.0,   # standing
    4: 4.5,   # walking
    5: 3.2,   # running, clipped to trekking-like speed
    6: 3.8,   # cycling, clipped to trekking-like speed
    7: 0.8,   # nordic walking warmup-like records vary
    12: 0.5,  # ascending stairs
    13: 0.6,  # descending stairs
    16: 3.5,  # vacuum cleaning
    17: 2.8,  # ironing
    24: 3.0,  # rope jumping, clipped to trekking-like speed
}

# WESAD condition codes kept for fatigue rows; 0/5/6/7 are transient/undefined
# segments the dataset authors say to discard.
WESAD_CONDITIONS = {1, 2, 3, 4}
WESAD_BVP_HZ = 64
WESAD_LABEL_HZ = 700


@dataclass(frozen=True)
class BuildResult:
    target: Path
    rows_before: int
    rows_after: int
    rows_added: int
    sources: list[str]


def _normalize_columns(df: pd.DataFrame, columns: list[str], source_name: str) -> pd.DataFrame:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{source_name}: missing columns: {', '.join(missing)}")

    normalized = df[columns].copy()
    for column in columns:
        if column != "label":
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized["label"] = normalized["label"].astype(str).str.strip()
    normalized = normalized.dropna(subset=[column for column in columns if column != "label"])
    normalized = normalized[normalized["label"] != ""]
    return normalized.reset_index(drop=True)


def _read_optional_processed(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    return _normalize_columns(pd.read_csv(path), columns, path.name)


def _label_fatigue(hr_reserve_percent: float, elapsed_minutes: float) -> str:
    if hr_reserve_percent >= 70 or (hr_reserve_percent >= 58 and elapsed_minutes >= 45):
        return "alto"
    if hr_reserve_percent >= 42 or elapsed_minutes >= 25:
        return "medio"
    return "bajo"


def _fatigue_score(label: str) -> int:
    return {"bajo": 1, "medio": 2, "alto": 3}[label]


def _label_risk(hr: float, spo2: float, fatigue_score: int, elevation_gain_m: float) -> str:
    if spo2 < 90 or hr >= 165 or (fatigue_score >= 3 and elevation_gain_m >= 650):
        return "alto"
    if spo2 < 94 or hr >= 130 or fatigue_score >= 2 or elevation_gain_m >= 350:
        return "medio"
    return "bajo"


def _limit_balanced(df: pd.DataFrame, max_rows_per_label: int) -> pd.DataFrame:
    if df.empty:
        return df

    groups = []
    for _, group in df.groupby("label"):
        if len(group) > max_rows_per_label:
            groups.append(group.sample(max_rows_per_label, random_state=42))
        else:
            groups.append(group)
    return pd.concat(groups, ignore_index=True).sample(frac=1, random_state=42).reset_index(drop=True)


def build_fatigue_from_pamap2() -> pd.DataFrame:
    require_public_ground_truth("fatigue")
    """Create fatigue rows from PAMAP2 `.dat` files when present locally."""
    pamap_root = RAW_DIR / "pamap2"
    dat_files = sorted(pamap_root.glob("**/*.dat"))
    if not dat_files:
        return pd.DataFrame(columns=FATIGUE_COLUMNS)

    rows: list[pd.DataFrame] = []
    for dat_file in dat_files:
        chunks = pd.read_csv(
            dat_file,
            sep=r"\s+",
            header=None,
            usecols=[0, 1, 2],
            names=["timestamp", "activity_id", "hr"],
            chunksize=200_000,
        )

        for chunk in chunks:
            chunk = chunk.dropna(subset=["timestamp", "activity_id", "hr"])
            chunk = chunk[chunk["activity_id"].isin(PAMAP2_SPEED_BY_ACTIVITY)]
            chunk = chunk[chunk["hr"].between(40, 210)]
            if chunk.empty:
                continue

            start = float(chunk["timestamp"].min())
            chunk["elapsed_minutes"] = (chunk["timestamp"] - start) / 60.0
            chunk["minute_bucket"] = chunk["elapsed_minutes"].round().astype(int)
            aggregated = (
                chunk.groupby("minute_bucket", as_index=False)
                .agg(hr=("hr", "mean"), activity_id=("activity_id", "first"), elapsed_minutes=("elapsed_minutes", "mean"))
            )
            aggregated["speed_kmh"] = aggregated["activity_id"].map(PAMAP2_SPEED_BY_ACTIVITY)
            aggregated = aggregated[aggregated["speed_kmh"] > 0]
            aggregated["hr_reserve_percent"] = ((aggregated["hr"] - 60) / 120 * 100).clip(0, 100)
            aggregated["label"] = [
                _label_fatigue(hr_reserve, elapsed)
                for hr_reserve, elapsed in zip(
                    aggregated["hr_reserve_percent"], aggregated["elapsed_minutes"]
                )
            ]
            # Round before appending: `to_csv`/`read_csv` don't always round-trip a
            # float64 bit-for-bit, so an unrounded value can silently differ from
            # itself by ~1e-15 on the next run and defeat `_merge_dataset`'s exact
            # `drop_duplicates()`, slowly duplicating the same real rows on repeat
            # `--write` runs.
            rows.append(aggregated[FATIGUE_COLUMNS].round(4))

    if not rows:
        return pd.DataFrame(columns=FATIGUE_COLUMNS)

    return _limit_balanced(pd.concat(rows, ignore_index=True), max_rows_per_label=800)


def build_fatigue_from_wesad() -> pd.DataFrame:
    require_public_ground_truth("fatigue")
    """Create fatigue rows from WESAD `SXX.pkl` files when present locally.

    WESAD is a stress/affect protocol, not a locomotion dataset: subjects stay
    seated through baseline/stress/amusement/meditation segments, so unlike
    PAMAP2 there is no walking speed to derive. Rows are emitted with
    `speed_kmh=0` (accurate, not filtered out) so the fatigue label reflects
    physiological stress response rather than physical exertion - a
    deliberately different signal than PAMAP2's, per the PFI document's use
    of WESAD as a complement, not a replacement.

    Heart rate is estimated from the wrist BVP (PPG) channel via
    peak-to-peak interval, since that mirrors what a consumer wearable
    measures in the app, rather than the chest ECG electrodes.
    """
    wesad_root = RAW_DIR / "wesad"
    pkl_files = sorted(wesad_root.glob("**/S*.pkl"))
    if not pkl_files:
        return pd.DataFrame(columns=FATIGUE_COLUMNS)

    rows: list[pd.DataFrame] = []
    for pkl_file in pkl_files:
        with pkl_file.open("rb") as handle:
            data = pickle.load(handle, encoding="latin1")

        bvp = np.asarray(data["signal"]["wrist"]["BVP"], dtype=float).reshape(-1)
        labels_700hz = np.asarray(data["label"]).reshape(-1)
        if bvp.size == 0 or labels_700hz.size == 0:
            continue

        peaks, _ = find_peaks(bvp, distance=WESAD_BVP_HZ * 0.3, prominence=np.std(bvp) * 0.5)
        if peaks.size < 2:
            continue

        peak_times_s = peaks / WESAD_BVP_HZ
        instantaneous_hr = 60.0 / np.diff(peak_times_s)
        beat_times_s = peak_times_s[1:]

        valid_hr = (instantaneous_hr >= 40) & (instantaneous_hr <= 210)
        instantaneous_hr = instantaneous_hr[valid_hr]
        beat_times_s = beat_times_s[valid_hr]
        if beat_times_s.size == 0:
            continue

        label_index = np.clip((beat_times_s * WESAD_LABEL_HZ).astype(int), 0, labels_700hz.size - 1)
        beat_condition = labels_700hz[label_index]

        working = pd.DataFrame(
            {
                "hr": instantaneous_hr,
                "time_minutes": beat_times_s / 60.0,
                "condition": beat_condition,
            }
        )
        working = working[working["condition"].isin(WESAD_CONDITIONS)].reset_index(drop=True)
        if working.empty:
            continue

        # `time_minutes` is elapsed since the whole ~100-minute recording
        # started, not since this condition began. Resetting it per
        # contiguous condition block (baseline/stress/amusement/meditation)
        # keeps `elapsed_minutes` meaning "time in this state", matching how
        # PAMAP2's elapsed_minutes tracks a single activity bout - otherwise
        # a calm segment late in the protocol would inherit a large elapsed
        # value and get labeled as if it were sustained physical exertion.
        segment_id = (working["condition"] != working["condition"].shift()).cumsum()
        segment_id.name = "segment_id"
        segment_start = working.groupby(segment_id)["time_minutes"].transform("min")
        working["elapsed_minutes"] = working["time_minutes"] - segment_start
        working["minute_bucket"] = working["elapsed_minutes"].round().astype(int)

        aggregated = (
            working.groupby([segment_id, "minute_bucket"], as_index=False)
            .agg(hr=("hr", "mean"), elapsed_minutes=("elapsed_minutes", "mean"))
        )
        aggregated["speed_kmh"] = 0.0
        aggregated["hr_reserve_percent"] = ((aggregated["hr"] - 60) / 120 * 100).clip(0, 100)
        aggregated["label"] = [
            _label_fatigue(hr_reserve, elapsed)
            for hr_reserve, elapsed in zip(
                aggregated["hr_reserve_percent"], aggregated["elapsed_minutes"]
            )
        ]
        rows.append(aggregated[FATIGUE_COLUMNS].round(4))

    if not rows:
        return pd.DataFrame(columns=FATIGUE_COLUMNS)

    return _limit_balanced(pd.concat(rows, ignore_index=True), max_rows_per_label=800)


def _find_column(columns: list[str], patterns: list[str]) -> str | None:
    for pattern in patterns:
        regex = re.compile(pattern, re.IGNORECASE)
        for column in columns:
            if regex.search(str(column)):
                return column
    return None


def build_risk_from_bidmc() -> pd.DataFrame:
    require_public_ground_truth("physio_risk")
    """Create risk rows from BIDMC CSV numerics when present locally."""
    bidmc_root = RAW_DIR / "bidmc"
    csv_files = sorted(bidmc_root.glob("**/*Numerics.csv"))
    if not csv_files:
        return pd.DataFrame(columns=RISK_COLUMNS)

    rng = np.random.default_rng(42)
    rows: list[pd.DataFrame] = []
    for source_file in csv_files:
        frame = pd.read_csv(source_file)
        frame.columns = [str(column).strip() for column in frame.columns]
        columns = list(frame.columns)
        hr_column = _find_column(columns, [r"^hr$", r"heart"])
        spo2_column = _find_column(columns, [r"spo2", r"oxygen"])
        time_column = _find_column(columns, [r"time"])

        if hr_column is None or spo2_column is None:
            continue

        working = pd.DataFrame(
            {
                "hr": pd.to_numeric(frame[hr_column], errors="coerce"),
                "spo2": pd.to_numeric(frame[spo2_column], errors="coerce"),
            }
        )
        if time_column:
            working["elapsed_minutes"] = pd.to_numeric(frame[time_column], errors="coerce") / 60.0
        else:
            working["elapsed_minutes"] = np.arange(len(working)) / 60.0

        working = working.dropna()
        working = working[working["hr"].between(40, 220) & working["spo2"].between(70, 100)]
        if working.empty:
            continue

        working["minute_bucket"] = working["elapsed_minutes"].round().astype(int)
        aggregated = (
            working.groupby("minute_bucket", as_index=False)
            .agg(hr=("hr", "mean"), spo2=("spo2", "mean"), elapsed_minutes=("elapsed_minutes", "mean"))
        )
        aggregated["speed_kmh"] = rng.uniform(1.5, 4.8, len(aggregated))
        aggregated["elevation_gain_m"] = rng.uniform(40, 900, len(aggregated))
        fatigue_labels = [
            _label_fatigue(max(0, min(100, (hr - 60) / 120 * 100)), elapsed)
            for hr, elapsed in zip(aggregated["hr"], aggregated["elapsed_minutes"])
        ]
        aggregated["fatigue_score"] = [_fatigue_score(label) for label in fatigue_labels]
        aggregated["label"] = [
            _label_risk(hr, spo2, fatigue, elevation)
            for hr, spo2, fatigue, elevation in zip(
                aggregated["hr"],
                aggregated["spo2"],
                aggregated["fatigue_score"],
                aggregated["elevation_gain_m"],
            )
        ]
        rows.append(aggregated[RISK_COLUMNS].round(4))

    if not rows:
        return pd.DataFrame(columns=RISK_COLUMNS)

    return _limit_balanced(pd.concat(rows, ignore_index=True), max_rows_per_label=800)


# --- Route difficulty from real Argentine trails (OSM geometry + Open-Elevation) ---
#
# The PFI document's original plan (OSM `sac_scale` + NASA SRTM) doesn't work in
# practice: `sac_scale` tagging is dense in the Alps but sparse to nonexistent on
# Argentine trails, and SRTM distribution requires a NASA Earthdata login. Instead:
#   - Trail geometry + names come live from the public Overpass API, scoped to
#     Argentina's main hiking regions (still real OSM data, just not relying on
#     the sac_scale tag being present).
#   - Elevation comes from the free Open-Elevation API (point lookups, no DEM
#     raster/GDAL needed) instead of SRTM.
#   - Because a labeled difficulty dataset for Argentine trails doesn't exist
#     publicly, the Baja/Media/Alta label is computed from two independently
#     documented, citable formulas instead of a human rating:
#       1. Steepness, inspired by the qualitative criteria of the SAC hiking
#          scale (the same standard `sac_scale` encodes) - the exact percent
#          thresholds below are this project's own calibration from those
#          descriptions, not official published numbers.
#       2. Exertion, via the Shenandoah National Park hiking-difficulty formula
#          (sqrt(elevation_gain_ft * 2 * distance_miles)), a long-published,
#          citable method for combining distance and climb into one score.
#     A trail's label is whichever formula rates it harder - a route is only as
#     easy as its hardest dimension.
# Results are cached under `training/data/raw/osm_argentina/` after the first
# fetch so re-running the build doesn't repeatedly hit the public APIs.

ARGENTINA_HIKING_REGIONS: dict[str, tuple[float, float, float, float]] = {
    # (south, west, north, east)
    "bariloche_nahuel_huapi": (-41.5, -71.9, -40.8, -71.0),
    "el_bolson_san_martin_andes": (-41.9, -71.7, -40.1, -71.2),
    "el_chalten_los_glaciares": (-49.6, -73.1, -49.2, -72.7),
    "cordoba_sierras": (-32.0, -64.9, -31.0, -64.3),
    "mendoza_cordillera": (-33.2, -70.2, -32.5, -69.0),
    "ushuaia_tierra_del_fuego": (-54.9, -68.7, -54.7, -68.3),
}

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OPEN_ELEVATION_URL = "https://api.open-elevation.com/api/v1/lookup"
HTTP_USER_AGENT = "MiSenderoRouteDifficultyTraining/1.0"
MAX_WAYS_PER_REGION = 80
MAX_POINTS_PER_WAY = 40
ELEVATION_BATCH_SIZE = 100
EARTH_RADIUS_M = 6371000.0
# Comfortably above Open-Elevation's underlying DEM resolution, so a segment's
# slope isn't dominated by one grid cell's worth of noise (see comment where
# this is used, in build_route_difficulty_from_osm).
MIN_SEGMENT_DISTANCE_M = 30.0
MAX_PLAUSIBLE_SLOPE_PERCENT = 150.0

_SAC_SCALE_TECHNICAL_SCORE = {
    "hiking": 1,
    "mountain_hiking": 2,
    "demanding_mountain_hiking": 3,
    "alpine_hiking": 4,
    "demanding_alpine_hiking": 5,
    "difficult_alpine_hiking": 6,
    "T1": 1,
    "T2": 2,
    "T3": 3,
    "T4": 4,
    "T5": 5,
    "T6": 6,
}

_ROUTE_LABELS_BY_BUCKET = ["Baja", "Media", "Alta"]


def _overpass_fetch(bbox: tuple[float, float, float, float]) -> dict:
    south, west, north, east = bbox
    query = (
        "[out:json][timeout:60];"
        f'way["highway"="path"]["name"]({south},{west},{north},{east});'
        "out geom;"
    )
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    request = urllib.request.Request(
        OVERPASS_URL, data=data, headers={"User-Agent": HTTP_USER_AGENT}
    )

    # The free public instance occasionally 504s under load even for a query
    # that succeeds moments later, so retry a couple of times before giving up
    # on the region.
    last_error: Exception | None = None
    for attempt, backoff_seconds in enumerate((0, 20, 45)):
        if backoff_seconds:
            time.sleep(backoff_seconds)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            last_error = error
    raise last_error


def _haversine_m(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    lat1, lon1 = point_a
    lat2, lon2 = point_b
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _simplify_points(
    points: list[tuple[float, float]], max_points: int
) -> list[tuple[float, float]]:
    if len(points) <= max_points:
        return points
    step = len(points) / max_points
    indices = sorted({int(i * step) for i in range(max_points)} | {len(points) - 1})
    return [points[i] for i in indices]


def _fetch_elevations_m(points: list[tuple[float, float]]) -> list[float]:
    elevations: list[float] = []
    for start in range(0, len(points), ELEVATION_BATCH_SIZE):
        batch = points[start : start + ELEVATION_BATCH_SIZE]
        payload = json.dumps(
            {"locations": [{"latitude": lat, "longitude": lon} for lat, lon in batch]}
        ).encode("utf-8")
        request = urllib.request.Request(
            OPEN_ELEVATION_URL,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": HTTP_USER_AGENT},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
        elevations.extend(float(result["elevation"]) for result in body["results"])
        time.sleep(1.0)
    return elevations


def _technical_score(tags: dict, max_slope_percent: float) -> int:
    sac_scale = tags.get("sac_scale")
    if sac_scale in _SAC_SCALE_TECHNICAL_SCORE:
        return _SAC_SCALE_TECHNICAL_SCORE[sac_scale]
    if max_slope_percent >= 40:
        return 4
    if max_slope_percent >= 30:
        return 3
    if max_slope_percent >= 20:
        return 2
    return 1


def _slope_bucket(max_slope_percent: float) -> int:
    if max_slope_percent >= 40:
        return 2  # Alta
    if max_slope_percent >= 20:
        return 1  # Media
    return 0  # Baja


def _exertion_bucket(distance_km: float, elevation_gain_m: float) -> int:
    distance_miles = distance_km * 0.621371
    elevation_gain_ft = max(0.0, elevation_gain_m) * 3.28084
    score = math.sqrt(elevation_gain_ft * 2 * max(0.0, distance_miles))
    if score >= 150:
        return 2  # Alta
    if score >= 50:
        return 1  # Media
    return 0  # Baja


def _route_label(distance_km: float, elevation_gain_m: float, max_slope_percent: float) -> str:
    bucket = max(
        _slope_bucket(max_slope_percent),
        _exertion_bucket(distance_km, elevation_gain_m),
    )
    return _ROUTE_LABELS_BY_BUCKET[bucket]


def _load_or_fetch_region(region_name: str, bbox: tuple[float, float, float, float]) -> list[dict]:
    """Return this region's trails as `{tags, points: [[lat, lon, elevation_m], ...]}`.

    Cached to `training/data/raw/osm_argentina/<region>.json` after the first
    live fetch, so re-running the build stays offline and doesn't re-hit the
    public Overpass/Open-Elevation APIs.
    """
    cache_path = OSM_ARGENTINA_CACHE_DIR / f"{region_name}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    try:
        overpass_result = _overpass_fetch(bbox)
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        print(f"route_difficulty: skipping {region_name}, Overpass fetch failed ({error})")
        return []

    ways = [
        element
        for element in overpass_result.get("elements", [])
        if element.get("type") == "way" and element.get("geometry")
    ][:MAX_WAYS_PER_REGION]

    trails: list[dict] = []
    for way in ways:
        points = [(node["lat"], node["lon"]) for node in way["geometry"]]
        if len(points) < 2:
            continue
        sampled_points = _simplify_points(points, MAX_POINTS_PER_WAY)

        try:
            elevations = _fetch_elevations_m(sampled_points)
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            print(
                f"route_difficulty: skipping way {way.get('id')} in {region_name}, "
                f"elevation lookup failed ({error})"
            )
            continue

        trails.append(
            {
                "tags": way.get("tags", {}),
                "points": [
                    [lat, lon, elevation]
                    for (lat, lon), elevation in zip(sampled_points, elevations)
                ],
            }
        )

    OSM_ARGENTINA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(trails), encoding="utf-8")
    return trails


def build_route_difficulty_from_osm() -> pd.DataFrame:
    require_public_ground_truth("route_difficulty")
    """Create route-difficulty rows from real Argentine trail geometry.

    See the module-level comment above `ARGENTINA_HIKING_REGIONS` for why this
    replaces the originally planned OSM `sac_scale` + NASA SRTM pairing.
    """
    rows: list[dict] = []

    for region_name, bbox in ARGENTINA_HIKING_REGIONS.items():
        for trail in _load_or_fetch_region(region_name, bbox):
            points = trail["points"]
            if len(points) < 2:
                continue

            coords = [(lat, lon) for lat, lon, _ in points]
            elevations = [elevation for _, _, elevation in points]
            segment_distances_m = [
                _haversine_m(coords[i], coords[i + 1]) for i in range(len(coords) - 1)
            ]
            distance_km = sum(segment_distances_m) / 1000.0
            if distance_km < 0.3:
                continue

            elevation_diffs = [b - a for a, b in zip(elevations, elevations[1:])]
            elevation_gain_m = sum(diff for diff in elevation_diffs if diff > 0)
            # Open-Elevation's underlying DEM has real horizontal resolution
            # (tens of meters); two sampled points closer together than that
            # can land in the same or an adjacent grid cell and show a slope
            # spike that has nothing to do with the actual terrain (a few
            # meters of real elevation noise divided by a few meters of
            # distance reads as hundreds of percent grade). Segments shorter
            # than MIN_SEGMENT_DISTANCE_M are dropped, and anything still
            # beyond MAX_PLAUSIBLE_SLOPE_PERCENT is treated as leftover
            # sampling noise rather than a real hiking grade.
            slopes_percent = []
            for diff, dist in zip(elevation_diffs, segment_distances_m):
                if dist <= MIN_SEGMENT_DISTANCE_M:
                    continue
                slope = abs(diff) / dist * 100
                if slope <= MAX_PLAUSIBLE_SLOPE_PERCENT:
                    slopes_percent.append(slope)
            if not slopes_percent:
                continue

            avg_slope_percent = sum(slopes_percent) / len(slopes_percent)
            max_slope_percent = max(slopes_percent)
            technical_score = _technical_score(trail["tags"], max_slope_percent)
            label = _route_label(distance_km, elevation_gain_m, max_slope_percent)

            rows.append(
                {
                    "distance_km": round(distance_km, 2),
                    "elevation_gain_m": round(elevation_gain_m, 1),
                    "avg_slope_percent": round(avg_slope_percent, 1),
                    "max_slope_percent": round(max_slope_percent, 1),
                    "technical_score": technical_score,
                    "label": label,
                }
            )

    if not rows:
        return pd.DataFrame(columns=ROUTE_COLUMNS)

    return pd.DataFrame(rows)[ROUTE_COLUMNS]


def _merge_dataset(target: Path, columns: list[str], additions: list[tuple[str, pd.DataFrame]]) -> BuildResult:
    current = _normalize_columns(pd.read_csv(target), columns, target.name)
    sources: list[str] = []
    frames = [current]

    for source_name, frame in additions:
        normalized = _normalize_columns(frame, columns, source_name)
        if not normalized.empty:
            frames.append(normalized)
            sources.append(source_name)

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates().reset_index(drop=True)
    assert_no_restricted_columns(merged, target.name)
    return BuildResult(
        target=target,
        rows_before=len(current),
        rows_after=len(merged),
        rows_added=max(0, len(merged) - len(current)),
        sources=sources,
    ), merged


def build(write: bool) -> list[BuildResult]:
    require_public_ground_truth("legacy_dataset_builder")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    fatigue_result, fatigue = _merge_dataset(
        FATIGUE_PATH,
        FATIGUE_COLUMNS,
        [
            ("processed/fatigue_public.csv", _read_optional_processed(PROCESSED_DIR / "fatigue_public.csv", FATIGUE_COLUMNS)),
            ("raw/pamap2", build_fatigue_from_pamap2()),
            ("raw/wesad", build_fatigue_from_wesad()),
        ],
    )
    risk_result, risk = _merge_dataset(
        PHYSIO_RISK_PATH,
        RISK_COLUMNS,
        [
            ("processed/physio_risk_public.csv", _read_optional_processed(PROCESSED_DIR / "physio_risk_public.csv", RISK_COLUMNS)),
            ("raw/bidmc", build_risk_from_bidmc()),
        ],
    )
    route_result, route = _merge_dataset(
        ROUTE_DIFFICULTY_PATH,
        ROUTE_COLUMNS,
        [
            (
                "processed/route_difficulty_osm_srtm.csv",
                _read_optional_processed(
                    PROCESSED_DIR / "route_difficulty_osm_srtm.csv", ROUTE_COLUMNS
                ),
            ),
            ("osm_argentina", build_route_difficulty_from_osm()),
        ],
    )

    if write:
        fatigue.to_csv(FATIGUE_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
        risk.to_csv(PHYSIO_RISK_PATH, index=False, quoting=csv.QUOTE_MINIMAL)
        route.to_csv(ROUTE_DIFFICULTY_PATH, index=False, quoting=csv.QUOTE_MINIMAL)

    return [fatigue_result, risk_result, route_result]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="write normalized CSVs; without this flag the script only reports available sources",
    )
    args = parser.parse_args()

    for result in build(write=args.write):
        mode = "updated" if args.write else "dry-run"
        source_text = ", ".join(result.sources) if result.sources else "no extra local sources found"
        print(
            f"{mode}: {result.target.relative_to(REPO_ROOT)} "
            f"rows_before={result.rows_before} rows_after={result.rows_after} "
            f"rows_added={result.rows_added} sources={source_text}"
        )


if __name__ == "__main__":
    main()
