"""Exploratory 24-hour fire-pixel evaluation using archived GFS forecasts.

Research only. Uses weather forecasts that were issued 24h before each target
hour, combines them with satellite history available at issue time, and keeps
January 2026 as a chronological test. It does not evaluate ignition warning.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import beta
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_score, recall_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from environmental_sources import PUBLIC, ROOT, sha256, utc
from train_fire_hourly import issue_features


PRIVATE = PUBLIC / "private"
WEATHER_FILES = (
    (PRIVATE / "openmeteo-gfs-previous-runs-argentina-trails-2024-01-01-2024-02-01.json.gz",
     PRIVATE / "openmeteo-gfs-previous-runs-argentina-trails-2024-01-01-2024-02-01-manifest.json"),
    (PRIVATE / "openmeteo-gfs-previous-runs-argentina-trails-2025-01-01-2026-02-01.json.gz",
     PRIVATE / "openmeteo-gfs-previous-runs-argentina-trails-2025-01-01-2026-02-01-manifest.json"),
)
EXPERIMENTS = ("fire-hourly", "fire-goes16-2025-q1", "fire-goes19-2025q4-2026jan")
REPORT = ROOT / "docs/environmental-models-2026-10-22/fire-goes-gfs-24h-evaluation.json"
SNMF_EVENTS = ROOT / "docs/environmental-models-2026-10-22/snmf-2026-jan-daily-occurrence-events.json"
GEOGRAPHY = PUBLIC / "geography.json"
EVENT_REPORT = ROOT / "docs/environmental-models-2026-10-22/goes-gfs-24h-snmf-2026-jan-event-audit.json"
WEATHER_VARIABLES = (
    "temperature_2m_previous_day1",
    "relative_humidity_2m_previous_day1",
    "wind_speed_10m_previous_day1",
    "precipitation_previous_day1",
)


def load_weather() -> dict[tuple[str, str], list[float]]:
    result: dict[tuple[str, str], list[float]] = {}
    for weather_path, manifest_path in WEATHER_FILES:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        with gzip.open(weather_path, "rt", encoding="utf-8") as stream:
            response = json.load(stream)
        if len(response) != len(manifest["locations"]):
            raise ValueError("Weather response and location manifest do not align")
        for location, payload in zip(manifest["locations"], response):
            region = location["region"]
            hourly = payload["hourly"]
            for idx, timestamp in enumerate(hourly["time"]):
                values = [hourly[name][idx] for name in WEATHER_VARIABLES]
                if any(value is None for value in values):
                    continue
                result[(region, timestamp[:13])] = [float(value) for value in values]
    return result


def load_goes():
    scan_set: set[str] = set()
    source_by_scan: dict[str, str] = {}
    scan_sensor: dict[str, str] = {}
    coordinates: dict[tuple[str, str, str], tuple[float, float]] = {}
    regions: dict[tuple[str, str, str], str] = {}
    availability_by_experiment = {}
    source_hashes = {}
    for experiment in EXPERIMENTS:
        obs = PRIVATE / f"{experiment}-observations.csv.gz"
        availability = PRIVATE / f"{experiment}-availability-by-scan.csv"
        if not availability.exists():
            availability = PRIVATE / f"{experiment}-source-manifest.json"
        source_hashes[experiment] = {"observations": sha256(obs), "availability_or_manifest": sha256(availability)}
        availability_by_id = {}
        if experiment != "fire-hourly":
            with availability.open(encoding="utf-8", newline="") as stream:
                for row in csv.DictReader(stream):
                    availability_by_id[row["source_id"]] = utc(row["product_created_at"])
        availability_by_experiment[experiment] = availability_by_id
        with gzip.open(obs, "rt", encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                scan = row["scan_start"]
                scan_set.add(scan)
                scan_sensor[scan] = experiment
                source_by_scan.setdefault(scan, row["source_id"])
                if experiment == "fire-hourly" and row.get("available_at"):
                    source_by_scan[scan] = row["available_at"]
                key = (experiment, row["region"], row["pixel_id"])
                point = (float(row["latitude"]), float(row["longitude"]))
                if key in coordinates and coordinates[key] != point:
                    raise ValueError(f"Inconsistent coordinate for {key}")
                coordinates[key] = point
                regions[key] = row["region"]

    times = sorted(scan_set)
    keys = sorted(coordinates)
    issued = {}
    for scan, source_id in source_by_scan.items():
        experiment = scan_sensor[scan]
        if experiment == "fire-hourly":
            issued[scan] = utc(source_id)
        else:
            issued[scan] = availability_by_experiment[experiment][source_id]
    columns = {key: idx for idx, key in enumerate(keys)}
    time_rows = {stamp: idx for idx, stamp in enumerate(times)}
    matrix = np.full((len(times), len(keys)), -1, dtype=np.int8)
    for experiment in EXPERIMENTS:
        obs = PRIVATE / f"{experiment}-observations.csv.gz"
        with gzip.open(obs, "rt", encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                mask, dqf = int(row["mask"]), int(row["dqf"])
                label = 1 if dqf == 0 and mask in (10, 11, 30, 31) else 0 if dqf == 1 and mask == 100 else -1
                key = (experiment, row["region"], row["pixel_id"])
                matrix[time_rows[row["scan_start"]], columns[key]] = label
    created = [issued[t] for t in times]
    coord = np.asarray([coordinates[key] for key in keys], dtype=np.float32)
    region_by_column = [regions[key] for key in keys]
    experiment_by_column = [key[0] for key in keys]
    return times, created, matrix, coord, region_by_column, experiment_by_column, [scan_sensor[t] for t in times], source_hashes


def exact_interval(successes: int, trials: int) -> list[float] | None:
    if not trials:
        return None
    alpha = 0.05
    low = 0.0 if successes == 0 else float(beta.ppf(alpha / 2, successes, trials - successes + 1))
    high = 1.0 if successes == trials else float(beta.ppf(1 - alpha / 2, successes + 1, trials - successes))
    return [low, high]


def summarize(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    pred = scores >= threshold
    tp = int(np.sum(pred & (y == 1)))
    alerts = int(pred.sum())
    return {
        "threshold": threshold,
        "alerts_route_sector_days": alerts,
        "true_positive_route_sector_days": tp,
        "precision": tp / alerts if alerts else None,
        "precision_exact_95ci_descriptive": exact_interval(tp, alerts),
        "recall": tp / int(y.sum()) if int(y.sum()) else None,
        "positive_route_sector_days": int(y.sum()),
        "caution": "Nearby sectors and adjacent days can belong to one fire; this is not event-level precision.",
    }


def aggregate_days(y, scores, persistence, groups):
    grouped = {}
    for label, score, baseline, group in zip(y, scores, persistence, groups):
        row = grouped.setdefault(group, [0, -1.0, 0])
        row[0] = max(int(row[0]), int(label))
        row[1] = max(float(row[1]), float(score))
        row[2] = max(int(row[2]), int(baseline))
    keys = sorted(grouped)
    return (np.asarray([grouped[k][0] for k in keys], dtype=np.uint8),
            np.asarray([grouped[k][1] for k in keys], dtype=np.float64),
            np.asarray([grouped[k][2] for k in keys], dtype=np.uint8), keys)


def main() -> None:
    global REPORT, EVENT_REPORT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-start", default="2025-12-01", help="First valid date reserved for validation")
    parser.add_argument("--run-name", default="", help="Optional safe suffix for distinct research outputs")
    args = parser.parse_args()
    validation_start = datetime.fromisoformat(args.validation_start).date()
    if args.run_name:
        if not args.run_name.replace("-", "").isalnum():
            parser.error("--run-name may contain only letters, numbers, and hyphens")
        REPORT = ROOT / f"docs/environmental-models-2026-10-22/fire-goes-gfs-24h-evaluation-{args.run_name}.json"
        EVENT_REPORT = ROOT / f"docs/environmental-models-2026-10-22/goes-gfs-24h-snmf-2026-jan-event-audit-{args.run_name}.json"
    weather = load_weather()
    times, created, matrix, coord, regions, experiments, scan_sensor, source_hashes = load_goes()
    feature_buckets = {name: [] for name in ("train", "validation", "test")}
    label_buckets = {name: [] for name in ("train", "validation", "test")}
    persistence_buckets = {name: [] for name in feature_buckets}
    group_buckets = {name: [] for name in feature_buckets}
    valid_pairs = 0
    pairs_without_valid_sector_inputs = 0
    region_names = sorted(set(regions))
    region_columns = {
        (sensor, region): np.asarray([
            col for col, (col_sensor, col_region) in enumerate(zip(experiments, regions))
            if sensor == col_sensor and region == col_region
        ], dtype=np.int64)
        for sensor in EXPERIMENTS for region in region_names
    }
    start_dates = {
        "validation": validation_start,
        "test": datetime(2026, 1, 1, tzinfo=timezone.utc).date(),
        "test_end": datetime(2026, 2, 1, tzinfo=timezone.utc).date(),
    }
    for issue, issue_time in enumerate(created):
        # Match the scan 24 hours later, allowing the observed product cadence.
        target_instant = issue_time.timestamp() + 24 * 3600
        candidates = range(issue + 1, min(issue + 30, len(created)))
        target_idx = min(candidates, key=lambda j: abs(created[j].timestamp() - target_instant), default=None)
        if target_idx is None or abs(created[target_idx].timestamp() - target_instant) > 15 * 60:
            continue
        valid_pairs += 1
        target_stamp = times[target_idx]
        target_dt = datetime.fromisoformat(target_stamp.replace("Z", "+00:00"))
        wanted_key = target_dt.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H")
        features, usable = issue_features(issue, created, matrix, coord)
        labels = matrix[target_idx]
        sensor = scan_sensor[target_idx]
        x_rows, y_rows, persistence_rows, groups = [], [], [], []
        for region in region_names:
            cols = region_columns[(sensor, region)]
            if not len(cols):
                continue
            valid_target = cols[labels[cols] >= 0]
            if len(valid_target) < max(10, int(0.50 * len(cols))):
                continue
            valid_history = cols[usable[cols]]
            if len(valid_history) < max(10, int(0.25 * len(cols))):
                continue
            target_label = int(np.any(labels[valid_target] == 1))
            history = features[valid_history]
            region_features = np.concatenate((
                np.mean(history[:, :6], axis=0),
                np.asarray([np.mean(history[:, 6]), np.mean(history[:, 7]),
                    np.mean(history[:, 8]), np.mean(history[:, 9])], dtype=np.float32),
                np.mean(history[:, 10:14], axis=0),
                np.asarray([len(valid_history) / len(cols)], dtype=np.float32),
            ))
            weather_values = weather.get((region, wanted_key))
            if weather_values is None:
                continue
            x_rows.append(np.concatenate((region_features, np.asarray(weather_values, dtype=np.float32))))
            y_rows.append(target_label)
            persistence_rows.append(int(np.any(history[:, 6] == 1)))
            groups.append((region, target_dt.date().isoformat()))
        if not x_rows:
            pairs_without_valid_sector_inputs += 1
            continue
        X, y = np.asarray(x_rows, dtype=np.float32), np.asarray(y_rows, dtype=np.uint8)
        if target_dt.date() < start_dates["validation"]:
            part = "train"
        elif target_dt.date() < start_dates["test"]:
            part = "validation"
        elif target_dt.date() < start_dates["test_end"]:
            part = "test"
        else:
            continue
        feature_buckets[part].append(X)
        label_buckets[part].append(y)
        persistence_buckets[part].append(np.asarray(persistence_rows, dtype=np.uint8))
        group_buckets[part].extend(groups)

    results = {
        "experiment_id": "goes-gfs-previous-runs-24h-sector-fire-detection",
        "candidate_status": "pending_evaluation",
        "protocol": {
            "weather_model": "NCEP GFS Seamless via Open-Meteo Previous Runs API",
            "weather_lead_hours": 24,
            "weather_features": list(WEATHER_VARIABLES),
            "fire_target": "Any high-quality GOES FDCF detection in a fixed sector in a scan 24h after issue time; not ignition or route safety.",
            "evaluation_unit": "Sector-hour for fitting; route-sector-day (maximum score) for threshold selection and test reporting.",
            "label_coverage_rule": "Count a positive if any sampled pixel has a nominal/high-quality GOES fire label; count a negative only when at least 50% of the sector's fixed pixels have valid target labels. Require valid recent GOES history for at least 25% of fixed pixels.",
            "training_period": "2024-01-01 through 2025-11-30 (only dates with GOES coverage and archived 24h weather)",
            "validation_period": f"{validation_start.isoformat()} through 2025-12-31",
            "test_period": "2026-01-01 through 2026-01-31",
            "target_split_uses_valid_scan_time": True,
            "threshold_rule": "On validation only, maximize recall with route-sector-day precision >= 0.80 and at least 5 alerts; otherwise select no threshold.",
        },
        "sources": {
            "weather": {path.name: {"response_sha256": sha256(path), "manifest_sha256": sha256(manifest)}
                for path, manifest in WEATHER_FILES},
            "goes": source_hashes,
        },
        "data_coverage": {"aligned_24h_scan_pairs": valid_pairs, "pairs_without_valid_sector_inputs": pairs_without_valid_sector_inputs},
        "partitions": {},
        "deployment_approved": False,
    }
    arrays = {}
    for part in feature_buckets:
        if feature_buckets[part]:
            arrays[part] = (np.concatenate(feature_buckets[part]), np.concatenate(label_buckets[part]))
            X, y = arrays[part]
            results["partitions"][part] = {
                "sector_hour_rows": len(y),
                "positive_sector_hours": int(y.sum()),
            }
        else:
            results["partitions"][part] = {"sector_hour_rows": 0, "positive_sector_hours": 0}

    if not all(part in arrays and len(arrays[part][1]) for part in ("train", "validation", "test")):
        results["candidate_status"] = "insufficient_temporal_data"
    else:
        X_train, y_train = arrays["train"]
        X_valid, y_valid = arrays["validation"]
        X_test, y_test = arrays["test"]
        model = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=500, random_state=42))
        model.fit(X_train, y_train)
        valid_scores = model.predict_proba(X_valid)[:, 1]
        y_valid_day, valid_day_scores, valid_persistence, valid_day_keys = aggregate_days(
            y_valid, valid_scores, np.concatenate(persistence_buckets["validation"]), group_buckets["validation"])
        candidates = []
        for threshold in np.unique(valid_day_scores):
            selected = valid_day_scores >= threshold
            alert_count = int(selected.sum())
            if alert_count < 5:
                continue
            precision = float(precision_score(y_valid_day, selected, zero_division=0))
            if precision >= 0.80:
                recall = float(recall_score(y_valid_day, selected, zero_division=0))
                candidates.append((recall, precision, alert_count, float(threshold)))
        selected_threshold = max(candidates)[3] if candidates else None
        test_scores = model.predict_proba(X_test)[:, 1]
        y_test_day, test_day_scores, test_persistence, test_day_keys = aggregate_days(
            y_test, test_scores, np.concatenate(persistence_buckets["test"]), group_buckets["test"])
        # Evaluate a conservative continuation-warning rule: only consider a
        # sector-day if satellite history already shows active fire, then rank
        # those cases by the weather+history model. This is not an ignition
        # forecast; it tests whether weather can filter persistence alerts.
        valid_gated_scores = np.where(valid_persistence == 1, valid_day_scores, -1.0)
        gated_candidates = []
        for threshold in np.unique(valid_gated_scores[valid_persistence == 1]):
            selected = valid_gated_scores >= threshold
            alert_count = int(selected.sum())
            if alert_count < 5:
                continue
            precision = float(precision_score(y_valid_day, selected, zero_division=0))
            if precision >= 0.80:
                recall = float(recall_score(y_valid_day, selected, zero_division=0))
                gated_candidates.append((recall, precision, alert_count, float(threshold)))
        gated_threshold = max(gated_candidates)[3] if gated_candidates else None
        test_gated_scores = np.where(test_persistence == 1, test_day_scores, -1.0)
        # Independent official-event check for fresh SNMF incidents whose
        # reported start date falls in the held-out January 2026 period.
        # SNMF dates have day precision only, so this cannot establish an
        # exact 24-hour ignition lead.
        event_source = json.loads(SNMF_EVENTS.read_text(encoding="utf-8"))
        geography = json.loads(GEOGRAPHY.read_text(encoding="utf-8"))
        centers = {region["name"]: (float(region["latitude"]), float(region["longitude"]))
            for region in geography["fire_regions"]}
        route_predictions = {key: (float(score), int(persist))
            for key, score, persist in zip(test_day_keys, test_day_scores, test_persistence)}
        event_groups = {}
        active_states = {"ACTIVO", "CONTENIDO", "CONTROLADO"}
        for event in event_source["deduplicated_events"]:
            day = event["reported_start_date"]
            if not ("2026-01-01" <= day < "2026-02-01") or event["latitude"] is None or event["longitude"] is None:
                continue
            key = (event["province"], day, round(float(event["latitude"]), 3), round(float(event["longitude"]), 3))
            grouped = event_groups.setdefault(key, {"province": event["province"], "reported_start_date": day,
                "latitude": float(event["latitude"]), "longitude": float(event["longitude"]),
                "names": set(), "active_reported": False})
            grouped["names"].add(event["incident_name"])
            grouped["active_reported"] |= event["status"] in active_states
        # Collapse same-province, same-start-day records within 1 km to avoid
        # counting spelling aliases or slightly shifted coordinates twice.
        # This is deliberately conservative; it can also merge distinct
        # nearby incidents, so the cluster rule is reported explicitly.
        clustered_events = []
        for event in event_groups.values():
            match = None
            for candidate in clustered_events:
                if (candidate["province"] != event["province"]
                        or candidate["reported_start_date"] != event["reported_start_date"]):
                    continue
                lat1, lat2 = np.radians([candidate["latitude"], event["latitude"]])
                dlat = lat2 - lat1
                dlon = np.radians(event["longitude"] - candidate["longitude"])
                a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
                if 6371.0088 * 2 * np.arcsin(np.sqrt(a)) <= 1.0:
                    match = candidate
                    break
            if match is None:
                clustered_events.append(event)
            else:
                match["names"].update(event["names"])
                match["active_reported"] |= event["active_reported"]
        event_matches = []
        for event in clustered_events:
            if not event["active_reported"]:
                continue
            nearby = []
            for region, (lat, lon) in centers.items():
                lat1, lat2 = np.radians([event["latitude"], lat])
                dlat = lat2 - lat1
                dlon = np.radians(lon - event["longitude"])
                a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
                distance_km = 6371.0088 * 2 * np.arcsin(np.sqrt(a))
                if distance_km <= 10.0 and (region, event["reported_start_date"]) in route_predictions:
                    score, persist = route_predictions[(region, event["reported_start_date"])]
                    nearby.append({"route_sector": region, "distance_km": round(float(distance_km), 3),
                        "model_score": score, "model_alert_at_0_5": score >= 0.5,
                        "persistence_alert": bool(persist)})
            event_matches.append({"province": event["province"], "reported_start_date": event["reported_start_date"],
                "incident_names": sorted(event["names"]), "latitude": event["latitude"],
                "longitude": event["longitude"], "nearby_covered_route_sectors_within_10km": nearby,
                "covered": bool(nearby), "alert_at_0_5": any(item["model_alert_at_0_5"] for item in nearby),
                "persistence_alert": any(item["persistence_alert"] for item in nearby)})
        covered_event_matches = [event for event in event_matches if event["covered"]]
        active_event_report = {
            "experiment_id": "goes-gfs-24h-independent-snmf-start-date-audit-2026-01",
            "interpretation": "Exploratory event sensitivity audit only. Official incident start dates have day precision and do not prove an exact 24-hour lead; no event precision is calculated because the archive is not an exhaustive fire/no-fire registry.",
            "protocol": {"event_period": "2026-01-01 through 2026-01-31 reported start dates",
                "spatial_rule": "At least one sampled route-sector center within 10 km with a scored route-sector-day",
                "duplicate_rule": "Merge records in the same province and reported start date when coordinates are within 1 km; this may merge distinct nearby incidents.",
                "diagnostic_score_threshold": 0.5, "model_horizon_hours": 24,
                "active_statuses": sorted(active_states)},
            "sources": {"snmf_events_sha256": sha256(SNMF_EVENTS), "geography_sha256": sha256(GEOGRAPHY)},
            "official_active_incidents_with_start_in_period": len(event_matches),
            "events_with_route_sector_score_coverage": len(covered_event_matches),
            "covered_events_alerted_at_0_5": sum(event["alert_at_0_5"] for event in covered_event_matches),
            "covered_event_sensitivity_at_0_5": (sum(event["alert_at_0_5"] for event in covered_event_matches) / len(covered_event_matches) if covered_event_matches else None),
            "covered_event_sensitivity_exact_95ci_descriptive": exact_interval(sum(event["alert_at_0_5"] for event in covered_event_matches), len(covered_event_matches)),
            "covered_events_with_persistence_alert": sum(event["persistence_alert"] for event in covered_event_matches),
            "events": event_matches,
            "deployment_approved": False,
        }
        results["candidate_status"] = "not_reliable" if selected_threshold is None else "exploratory_threshold_selected"
        results["validation"] = {
            "sector_hour_average_precision": float(average_precision_score(y_valid, valid_scores)),
            "route_sector_day_average_precision": float(average_precision_score(y_valid_day, valid_day_scores)),
            "threshold_at_precision_floor_0_80": None if selected_threshold is None else summarize(y_valid_day, valid_day_scores, selected_threshold),
            "precision_at_0_5_route_sector_day": summarize(y_valid_day, valid_day_scores, 0.5),
            "persistence_baseline_precision_recall": {
                "precision": float(precision_score(y_valid_day, valid_persistence, zero_division=0)),
                "recall": float(recall_score(y_valid_day, valid_persistence, zero_division=0)),
            },
            "route_sector_day_predictions": [
                {"route_sector": region, "target_date": target_date, "label_goes_fire": int(label),
                 "score": float(score), "alert_at_0_5": bool(score >= 0.5), "persistence": bool(persist)}
                for (region, target_date), label, score, persist in zip(
                    valid_day_keys, y_valid_day, valid_day_scores, valid_persistence)
            ],
        }
        results["test"] = {
            "sector_hour_average_precision": float(average_precision_score(y_test, test_scores)),
            "route_sector_day_average_precision": float(average_precision_score(y_test_day, test_day_scores)),
            "precision_at_0_5_route_sector_day": summarize(y_test_day, test_day_scores, 0.5),
            "persistence_baseline_precision_recall": {
                "precision": float(precision_score(y_test_day, test_persistence, zero_division=0)),
                "recall": float(recall_score(y_test_day, test_persistence, zero_division=0)),
            },
            "route_sector_day_predictions": [
                {"route_sector": region, "target_date": target_date, "label_goes_fire": int(label),
                 "score": float(score), "alert_at_0_5": bool(score >= 0.5), "persistence": bool(persist)}
                for (region, target_date), label, score, persist in zip(
                    test_day_keys, y_test_day, test_day_scores, test_persistence)
            ],
        }
        results["persistence_gated_candidate"] = {
            "meaning": "Continuation-risk filter only: issues a forecast alert only if satellite history at issue time already reports active fire in the sector; it does not predict ignition.",
            "validation_precision_floor": 0.80,
            "validation_minimum_alerts": 5,
            "threshold": gated_threshold,
            "validation": None if gated_threshold is None else summarize(y_valid_day, valid_gated_scores, gated_threshold),
            "test": None if gated_threshold is None else summarize(y_test_day, test_gated_scores, gated_threshold),
            "deployment_approved": False,
        }
        if selected_threshold is not None:
            results["protocol"]["frozen_threshold"] = selected_threshold
            results["test"]["at_validation_threshold"] = summarize(y_test_day, test_day_scores, selected_threshold)
        results["data_coverage"]["positive_route_sector_days"] = {
            "validation": int(y_valid_day.sum()), "test": int(y_test_day.sum())
        }
        if int(y_valid_day.sum()) < 10 or int(y_test_day.sum()) < 10:
            results["candidate_status"] = "insufficient_positive_route_sector_days"
        results["limitations"] = [
            "GOES fire detections are satellite labels, not ignition events or verified route-safety outcomes.",
            "Eight point samples and coarse GFS grid do not represent full trail geometry.",
            "Nearby sectors and adjacent days can belong to the same physical fire; route-sector-days are not independent incidents.",
            "This comparison does not establish event-level precision because there is no exhaustive independent negative-event registry.",
            "Class-weighted logistic scores are not calibrated probabilities.",
        ]
    REPORT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    active_event_report["sources"]["evaluation_sha256"] = sha256(REPORT)
    EVENT_REPORT.write_text(json.dumps(active_event_report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(json.dumps({"independent_snmf_event_audit": active_event_report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
