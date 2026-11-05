"""Temporal test of JMA weather against a union of MODIS and INPE detections.

Research-only label union. INPE AMS reference detections are Aqua/MODIS, so
they are retained as source lineage but are not independent sensor evidence.
Clear MODIS observations are required for negative labels.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import zipfile
from collections import defaultdict
from datetime import date

from environmental_sources import ROOT, sha256
from evaluate_argentina_trail_corridor_weather import (
    LABELS, LABEL_MANIFEST, WEATHER_ARCHIVES, WEATHER_MANIFESTS,
    WEATHER_FEATURES, add_calendar, choose_threshold, count_events, fit_logistic,
    load_route_day_labels, load_weather, predict, summary, wilson_lower,
)

REPORT_DIR = ROOT / "docs/environmental-models-2026-10-22"
PRIVATE = ROOT / "training/data/environmental/private"
ROUTE_FILES = (ROOT / "backend/src/data/additionalTrailRoutes.json",
               ROOT / "backend/src/data/catalogExpansionRoutes20261017.json")
INPE_DIR = PRIVATE / "inpe-ams-satellite-reference"
INPE_CACHE = PRIVATE / "inpe-41-trail-positive-days-2018-2025.json"
MODIS_DAY_CACHE = PRIVATE / "modis-41-trail-route-days-cache.json"
OUT = REPORT_DIR / "fire-modis-inpe-union-jma-temporal-evaluation-all-41.json"
OUT_MD = REPORT_DIR / "fire-modis-inpe-union-jma-temporal-evaluation-all-41.md"
UNIFIED_CATALOG = REPORT_DIR / "fire-unified-all-41-route-event-catalog.json"
DATASET = PRIVATE / "argentina-route-fire-evidence-jma-unified-all-41-2022-2026.csv.gz"
DATASET_MANIFEST = PRIVATE / "argentina-route-fire-evidence-jma-unified-all-41-2022-2026-manifest.json"
TRAIN_START, VALIDATION_START, TEST_START, TEST_END = (
    "2022-01-01", "2023-01-01", "2024-01-01", "2027-01-01")
RADIUS_KM = 5.0
KM_PER_DEG = 111.32


def route_lines() -> dict[str, list[list[float]]]:
    result = {}
    for path in ROUTE_FILES:
        for route_id, route in json.loads(path.read_text(encoding="utf-8")).items():
            points = route.get("points") or []
            if len(points) >= 2:
                result[route_id] = [[float(p[0]), float(p[1])] for p in points]
    return result


def distance_to_line_km(lat: float, lon: float, points: list[list[float]]) -> float:
    cosine = math.cos(math.radians(lat))
    best = math.inf
    for (lat1, lon1), (lat2, lon2) in zip(points, points[1:]):
        ax, ay = (lon1 - lon) * KM_PER_DEG * cosine, (lat1 - lat) * KM_PER_DEG
        bx, by = (lon2 - lon) * KM_PER_DEG * cosine, (lat2 - lat) * KM_PER_DEG
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length2))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def extract_inpe_days(routes: dict[str, list[list[float]]]) -> tuple[dict, dict]:
    """Read archived Argentina AMS reference CSVs and map points to full route lines."""
    if INPE_CACHE.is_file():
        cached = json.loads(INPE_CACHE.read_text(encoding="utf-8"))
        expected_hashes = {str(year): sha256(INPE_DIR / f"focos_ams_ref_{year}.zip")
                           for year in range(2018, 2026)}
        if cached.get("source_hashes") == expected_hashes:
            detections = {(r["route"], r["date"]): set(map(tuple, r["coordinates"]))
                          for r in cached["route_days"]}
            return detections, cached["summary"]
    route_bounds = {}
    for route, points in routes.items():
        lats, lons = [p[0] for p in points], [p[1] for p in points]
        cos_lat = max(math.cos(math.radians(sum(lats) / len(lats))), 0.1)
        route_bounds[route] = (min(lats) - RADIUS_KM / 110.574,
            max(lats) + RADIUS_KM / 110.574,
            min(lons) - RADIUS_KM / (KM_PER_DEG * cos_lat),
            max(lons) + RADIUS_KM / (KM_PER_DEG * cos_lat))
    detections = defaultdict(set)
    source_hashes = {}
    rows_screened = 0
    for year in range(2018, 2026):
        archive = INPE_DIR / f"focos_ams_ref_{year}.zip"
        source_hashes[str(year)] = {"path": archive.relative_to(ROOT).as_posix(),
                                    "sha256": sha256(archive)}
        with zipfile.ZipFile(archive) as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if len(csv_names) != 1:
                raise ValueError(f"Expected one CSV in {archive.name}")
            with zf.open(csv_names[0]) as raw:
                reader = csv.DictReader(io.TextIOWrapper(raw, encoding="latin1", newline=""))
                required = {"lat", "lon", "data_pas", "pais"}
                if not required.issubset(reader.fieldnames or []):
                    raise ValueError(f"Unexpected INPE schema in {archive.name}")
                for row in reader:
                    if row["pais"].strip().casefold() != "argentina":
                        continue
                    rows_screened += 1
                    day = row["data_pas"][:10]
                    try:
                        date.fromisoformat(day)
                        lat, lon = float(row["lat"]), float(row["lon"])
                    except (ValueError, TypeError):
                        continue
                    for route, points in routes.items():
                        south, north, west, east = route_bounds[route]
                        if not (south <= lat <= north and west <= lon <= east):
                            continue
                        if distance_to_line_km(lat, lon, points) <= RADIUS_KM:
                            detections[(route, day)].add((round(lat, 4), round(lon, 4)))
    summary = {"annual_archives": source_hashes,
        "argentina_detection_rows_screened": rows_screened,
        "route_date_detections_within_5km": len(detections),
        "unique_route_count_with_detection": len({r for r, _ in detections}),
        "unique_detection_coordinates": sum(len(v) for v in detections.values())}
    INPE_CACHE.write_text(json.dumps({"source_hashes": {year: item["sha256"] for year, item in source_hashes.items()},
        "summary": summary, "route_days": [{"route": route, "date": day,
            "coordinates": sorted(coords)} for (route, day), coords in sorted(detections.items())]},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return detections, summary


def load_cached_modis_route_days() -> tuple[list, dict]:
    source_hash = sha256(LABELS)
    if MODIS_DAY_CACHE.is_file():
        cached = json.loads(MODIS_DAY_CACHE.read_text(encoding="utf-8"))
        if cached.get("source_sha256") == source_hash:
            return cached["rows"], cached["quality"]
    rows, quality = load_route_day_labels()
    MODIS_DAY_CACHE.write_text(json.dumps({"source_sha256": source_hash,
        "rows": rows, "quality": quality}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return rows, quality


def export_unified_dataset(rows: list[dict], source_manifest: dict) -> dict:
    """Write a compact, deterministic route-day table and its lineage manifest."""
    columns = ["route_id", "date", "source_evidence_label", "source_evidence_sources",
        "catalog_event_ids", "inpe_detection_coordinates", "inpe_unique_coordinates",
        "modis_source_item_count", "modis_positive_pixels", "modis_clear_pixels",
        "modis_qa_coverage", *WEATHER_FEATURES, "annual_sin", "annual_cos",
        "temporal_partition"]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in sorted(rows, key=lambda r: (r["date"], r["route"])):
        day = row["date"]
        temporal_partition = ("train_2022" if "2022-01-01" <= day < "2023-01-01" else
            "validation_2023" if "2023-01-01" <= day < "2024-01-01" else
            "test_2024_2026" if "2024-01-01" <= day < "2027-01-01" else "outside_evaluation")
        feature_values = {name: row["features"][index]
                          for index, name in enumerate([*WEATHER_FEATURES, "annual_sin", "annual_cos"])}
        writer.writerow({"route_id": row["route"], "date": day,
            "source_evidence_label": row["label"],
            "source_evidence_sources": json.dumps(row["sources"], ensure_ascii=False, separators=(",", ":")),
            "catalog_event_ids": json.dumps(row["catalog_event_ids"], ensure_ascii=False, separators=(",", ":")),
            "inpe_detection_coordinates": json.dumps(row["inpe_detection_coordinates"], separators=(",", ":")),
            "inpe_unique_coordinates": row["inpe_unique_coordinates"],
            "modis_source_item_count": row["modis_source_item_count"],
            "modis_positive_pixels": row["modis_positive_pixels"],
            "modis_clear_pixels": row["modis_clear_pixels"],
            "modis_qa_coverage": row["modis_qa_coverage"],
            **feature_values, "temporal_partition": temporal_partition})
    csv_bytes = output.getvalue().encode("utf-8")
    compressed = bytearray(gzip.compress(csv_bytes, compresslevel=9, mtime=0))
    # Python versions may use the host OS code in the gzip header when mtime=0.
    # Normalize it so the same CSV has the same artifact hash across platforms.
    compressed[9] = 255
    DATASET.write_bytes(compressed)
    dataset_sha = sha256(DATASET)
    manifest = {"schema_version": 1,
        "dataset": DATASET.relative_to(ROOT).as_posix(),
        "dataset_sha256": dataset_sha, "compressed_bytes": len(compressed),
        "uncompressed_bytes": len(csv_bytes),
        "uncompressed_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "compression": "gzip level 9, mtime=0, normalized OS header byte",
        "rows": len(rows), "routes_with_labeled_observations": len({row["route"] for row in rows}),
        "weather_archive_route_count": 41, "columns": columns,
        "target": "At least one source-preserved MOD14A1, INPE Aqua/MODIS, SNMF or GFA record on the route-day.",
        "label_0_definition": "No catalogued event plus an MOD14A1 sampled corridor with >=80% clear-land QA and no detected active-fire pixel; not verified physical absence.",
        "temporal_partition": {"train": ["2022-01-01", "2023-01-01"],
            "validation": ["2023-01-01", "2024-01-01"],
            "test": ["2024-01-01", "2027-01-01"]},
        "feature_availability": "JMA GSM Previous Runs previous_day1, 24-hour lead, one archived route-midpoint forecast per target date.",
        "source_provenance": source_manifest,
        "limitations": ["INPE AMS reference detections use Aqua/MODIS and are not an independent sensor family from MOD14A1.",
            "A missing source record is not a negative; only route-days with valid MODIS clear QA enter as label 0.",
            "Label 0 means observed no detection in sampled corridor and no listed source event, not that no physical fire existed.",
            "Availability is discontinuous across 2024-2026; inspect source manifests and row dates before use.",
            "Check third-party source licenses before redistribution."]}
    DATASET_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def best_validation_precision(rows: list[dict], scores: list[float], min_alerts: int = 5) -> dict | None:
    """Select the highest-precision validation cutoff with a minimum alert count."""
    candidates = []
    for threshold in sorted(set(scores)):
        predicted = [score >= threshold for score in scores]
        alerts = sum(predicted)
        if alerts < min_alerts:
            continue
        positives = sum(row["label"] for row in rows)
        tp = sum(row["label"] and alert for row, alert in zip(rows, predicted))
        precision = tp / alerts
        recall = tp / positives if positives else 0.0
        candidates.append((precision, recall, -alerts, threshold, tp, alerts))
    if not candidates:
        return None
    precision, recall, negative_alerts, threshold, tp, alerts = max(candidates)
    return {"threshold": threshold, "validation_precision": precision,
        "validation_recall": recall, "validation_true_positives": tp,
        "validation_alerts": alerts, "minimum_alerts": min_alerts}


def aggregate_date_scores(rows: list[dict], scores: list[float]) -> tuple[list[dict], list[float]]:
    groups = defaultdict(lambda: {"label": 0, "score": 0.0, "routes": set()})
    for row, score in zip(rows, scores):
        group = groups[row["date"]]
        group["label"] = max(group["label"], row["label"])
        group["score"] = max(group["score"], score)
        group["routes"].add(row["route"])
    date_rows = [{"route": "all_argentine_routes", "date": day,
        "label": value["label"], "label_modis_detection": value["label"],
        "features": []} for day, value in sorted(groups.items())]
    return date_rows, [groups[row["date"]]["score"] for row in date_rows]


def main() -> None:
    manifest = json.loads(LABEL_MANIFEST.read_text(encoding="utf-8"))
    if sha256(LABELS) != manifest["observations_sha256"]:
        raise ValueError("MODIS label archive hash mismatch")
    weather = load_weather()
    modis_rows, quality = load_cached_modis_route_days()
    routes = route_lines()
    expected_routes = {route for route, _ in weather}
    routes = {name: line for name, line in routes.items() if name in expected_routes}
    inpe, inpe_provenance = extract_inpe_days(routes)
    catalog = json.loads(UNIFIED_CATALOG.read_text(encoding="utf-8"))
    catalog_sources = defaultdict(set)
    catalog_event_ids = defaultdict(list)
    unmapped_catalog_routes = defaultdict(int)
    for event in catalog["events"]:
        route = event["route"]
        if route not in routes:
            unmapped_catalog_routes[event["route"]] += 1
            continue
        catalog_sources[(route, event["start_date"])].update(event["source_families"])
        catalog_event_ids[(route, event["start_date"])].append(event["event_id"])

    # MODIS corridor observations define the evaluable route-days. INPE may
    # upgrade an observed clear MODIS route-day to a positive; missing days are
    # never treated as negatives.
    rows = []
    for modis in modis_rows:
        route, day = modis["route"], modis["date"]
        forecast = weather.get((route, day))
        if forecast is None:
            continue
        inpe_coords = sorted(inpe.get((route, day), set()))
        event_sources = sorted(catalog_sources.get((route, day), set()))
        label = int(bool(modis["label_modis_detection"] or inpe_coords or event_sources))
        sources = []
        if modis["label_modis_detection"]:
            sources.append("MOD14A1_corridor_detection")
        if inpe_coords:
            sources.append("INPE_AMS_Aqua_MODIS_reference_detection")
        sources.extend(event_sources)
        rows.append({"route": route, "date": day, "label": label,
            "label_modis_detection": label, "sources": sources,
            "inpe_unique_coordinates": len(inpe_coords),
            "catalog_event_ids": sorted(catalog_event_ids.get((route, day), [])),
            "inpe_detection_coordinates": [[lat, lon] for lat, lon in inpe_coords],
            "modis_source_item_count": modis["source_items"],
            "modis_positive_pixels": modis["positive_pixels"],
            "modis_clear_pixels": modis["clear_pixels"],
            "modis_qa_coverage": modis["qa_coverage"],
            "features": [forecast[name] for name in WEATHER_FEATURES] + list(add_calendar(day))})

    train = [row for row in rows if TRAIN_START <= row["date"] < VALIDATION_START]
    validation = [row for row in rows if VALIDATION_START <= row["date"] < TEST_START]
    test = [row for row in rows if TEST_START <= row["date"] < TEST_END]
    if not train or not validation or not test:
        raise ValueError("A temporal partition is empty")
    for archive, manifest_path in zip(WEATHER_ARCHIVES, WEATHER_MANIFESTS):
        weather_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if sha256(archive) != weather_manifest["compressed_response_sha256"]:
            raise ValueError(f"Weather archive hash mismatch: {archive.name}")
    weather_source_manifest = [{"archive": archive.relative_to(ROOT).as_posix(),
        "sha256": sha256(archive), "manifest": manifest.relative_to(ROOT).as_posix(),
        "manifest_sha256": sha256(manifest)}
        for archive, manifest in zip(WEATHER_ARCHIVES, WEATHER_MANIFESTS)]
    dataset_manifest = export_unified_dataset(rows, {"modis_sha256": sha256(LABELS),
        "inpe": inpe_provenance, "unified_catalog_sha256": sha256(UNIFIED_CATALOG),
        "route_geometry_files": {p.relative_to(ROOT).as_posix(): sha256(p) for p in ROUTE_FILES},
        "weather_archives": weather_source_manifest})
    feature_names = list(WEATHER_FEATURES) + ["annual_sin", "annual_cos"]
    model = fit_logistic(train, feature_names, sorted(routes))
    val_scores = predict(model, validation)
    validation_metrics = summary(validation, val_scores, 0.5)
    chosen = choose_threshold([row["label"] for row in validation], val_scores)
    best_route_threshold = best_validation_precision(validation, val_scores)
    # Fixed diagnostic only. It is never presented as a validated operating point.
    diagnostic_threshold = 0.5
    test_scores = predict(model, test)
    test_metrics = summary(test, test_scores, diagnostic_threshold)
    selected_route_metrics = (summary(test, test_scores, best_route_threshold["threshold"])
                              if best_route_threshold else None)
    date_rows, date_scores = aggregate_date_scores(test, test_scores)
    validation_date_rows, validation_date_scores = aggregate_date_scores(validation, val_scores)
    best_validation_date_threshold = best_validation_precision(validation_date_rows, validation_date_scores)
    event_metrics = summary(date_rows, date_scores, diagnostic_threshold)
    event_metrics["event_dates"] = event_metrics.pop("route_days")
    event_metrics["positive_event_dates"] = event_metrics.pop("positive_route_days")
    selected_event_date_metrics = (summary(date_rows, date_scores, best_validation_date_threshold["threshold"])
                                   if best_validation_date_threshold else None)
    if selected_event_date_metrics:
        selected_event_date_metrics["event_dates"] = selected_event_date_metrics.pop("route_days")
        selected_event_date_metrics["positive_event_dates"] = selected_event_date_metrics.pop("positive_route_days")
    test_positives = sorted(row["date"] for row in date_rows if row["label"])
    counts_by_year = {}
    for year in (2022, 2023, 2024, 2025, 2026):
        subset = [r for r in rows if r["date"].startswith(str(year))]
        counts_by_year[str(year)] = {"route_days": len(subset),
            "positive_route_days": sum(r["label"] for r in subset),
            "positive_dates": len({r["date"] for r in subset if r["label"]}),
            "route_fire_episodes_gap_gt_2_days": count_events(subset)["positive_route_fire_episodes_gap_gt_2_days"],
            "inpe_added_route_days": sum("INPE_AMS_Aqua_MODIS_reference_detection" in r["sources"]
                                         and "MOD14A1_corridor_detection" not in r["sources"] for r in subset)}
    result = {"experiment_id": "mod14a1-inpe-snmf-gfa-union-jma-all-41-2022-train-2023-validation-2024-2026-test",
        "status": "exploratory_satellite_detection_proxy_not_physical_fire_probability",
        "target": "At least one MOD14A1 corridor detection, INPE Aqua/MODIS reference hotspot, or SNMF/Global Fire Atlas source-preserved event on the route-day.",
        "negative_definition": "MOD14A1 corridor sample has at least 80% clear-land QA coverage and no active-fire pixel, and no catalogued source event is present; this is only a negative for the defined evidence target.",
        "sources": {"modis_observations_sha256": sha256(LABELS),
            "modis_label_quality": quality, "inpe": inpe_provenance,
            "unified_dataset": DATASET.relative_to(ROOT).as_posix(),
            "unified_dataset_sha256": dataset_manifest["dataset_sha256"],
            "unified_dataset_manifest": DATASET_MANIFEST.relative_to(ROOT).as_posix(),
            "unified_dataset_manifest_sha256": sha256(DATASET_MANIFEST),
            "unified_dataset_rows": dataset_manifest["rows"],
            "unified_catalog_sha256": sha256(UNIFIED_CATALOG),
            "unmapped_catalog_routes": dict(unmapped_catalog_routes),
            "inpe_family_caveat": "INPE AMS reference archive uses Aqua/MODIS; it is the same sensor family as the Aqua MOD14A1 evidence and is not independent confirmation.",
            "route_files_sha256": {p.relative_to(ROOT).as_posix(): sha256(p) for p in ROUTE_FILES}},
        "method": {"forecast": "JMA GSM Previous Runs, previous_day1 (24h lead), one route midpoint",
            "partition": {"train": [TRAIN_START, VALIDATION_START],
                "validation": [VALIDATION_START, TEST_START], "test": [TEST_START, TEST_END]},
            "diagnostic_threshold": diagnostic_threshold,
            "validated_operating_threshold": chosen,
            "best_precision_threshold_route_day": best_route_threshold,
            "best_precision_threshold_event_date": best_validation_date_threshold,
            "validation_gate_passed": chosen is not None,
            "threshold_selection": "Validation threshold sought for >=90% precision and >=5 alerts. No candidate passed; 0.5 below is a fixed diagnostic only, no test tuning.",
            "algorithm": "Class-balanced logistic regression, standardized weather, route effect, annual sine/cosine; batch gradient descent.",
            "features": feature_names},
        "cohort_by_year": counts_by_year,
        "aligned_route_days": len(rows), "train_route_days": len(train),
        "validation_route_days": len(validation), "validation_metrics_at_fixed_0_5_diagnostic": validation_metrics,
        "test_route_days": len(test),
        "test_positive_dates": test_positives,
        "test_route_day_metrics_at_fixed_0_5_diagnostic": test_metrics,
        "test_route_day_metrics_at_validation_max_precision_threshold": selected_route_metrics,
        "test_average_precision_baseline": {"route_day_prevalence": test_metrics["prevalence"],
            "calendar_date_prevalence": event_metrics["prevalence"],
            "meaning": "Test prevalence is the no-skill average-precision baseline; labels are source evidence, not all physical fires."},
        "test_event_date_metrics_at_fixed_0_5_diagnostic": event_metrics,
        "test_event_date_metrics_at_validation_max_precision_threshold": selected_event_date_metrics,
        "test_event_date_precision_wilson_one_sided_95_descriptive_lower_bound": wilson_lower(event_metrics["true_positives"], event_metrics["alerts"]),
        "limitations": ["The target is satellite detection evidence, not confirmed ignition or fire probability.",
            "INPE Aqua/MODIS and MOD14A1 are the same sensor family and some detections can overlap.",
            "Route dates with insufficient MODIS QA are omitted, not negatives.",
            "One daily route midpoint forecast may not represent weather along a long trail.",
            "A 2024-2026 temporal holdout is used once; the Wilson interval is descriptive and does not correct for temporal autocorrelation, source incompleteness, or shared incident episodes.",
            "This experiment does not authorize deployment or establish a reliable safety alert."],
        "synthetic_observations": 0, "model_artifact_written": False, "deployment_approved": False}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    OUT_MD.write_text("# Evaluación temporal MODIS + INPE + SNMF + GFA\n\n" +
        f"Entrenamiento 2022, selección del umbral en 2023 y test temporal 2024-2026. Ningún umbral de validación alcanzó el criterio de 90% de precisión con al menos cinco alertas. Se informa también el máximo de precisión en validación con cinco alertas mínimas y su resultado en test; 0,5 es solo un diagnóstico fijo.\n\n" +
        f"Dataset unificado reproducible (archivo privado local): `{DATASET.relative_to(ROOT).as_posix()}`; SHA-256 `{dataset_manifest['dataset_sha256']}`. Manifiesto: `{DATASET_MANIFEST.relative_to(ROOT).as_posix()}`.\n\n" +
        f"Mejor corte de validación por fecha: `{json.dumps(best_validation_date_threshold, ensure_ascii=False)}`; métricas de test en ese corte: `{json.dumps(selected_event_date_metrics, ensure_ascii=False)}`.\n\n" +
        f"Métricas por ruta-día: {json.dumps(test_metrics, ensure_ascii=False)}.\n\n" +
        f"Métricas agrupadas por fecha: {json.dumps(event_metrics, ensure_ascii=False)}; límite inferior Wilson unilateral 95% descriptivo de precisión: {result['test_event_date_precision_wilson_one_sided_95_descriptive_lower_bound']}.\n\n" +
        "INPE AMS referencia Aqua/MODIS; por eso su coincidencia con MOD14A1 no cuenta como confirmación independiente. Son detecciones satelitales, no verdad exhaustiva de incendios físicos. No se generó dataset sintético ni artefacto para la app.\n", encoding="utf-8")
    print(json.dumps({"report": OUT.relative_to(ROOT).as_posix(),
        "cohort_by_year": counts_by_year, "validation_threshold": chosen or "none",
        "validation_max_precision_route_day": best_route_threshold,
        "validation_max_precision_event_date": best_validation_date_threshold,
        "test_at_validation_max_precision_event_date": selected_event_date_metrics,
        "validation_diagnostic": validation_metrics,
        "test_route_day": test_metrics, "test_event_date": event_metrics,
        "test_precision_wilson_lower_descriptive": result["test_event_date_precision_wilson_one_sided_95_descriptive_lower_bound"]},
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
