#!/usr/bin/env python3
"""Consolidate current real-data fire reliability evidence and sample needs."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from scipy.stats import beta

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "docs/environmental-models-2026-10-22"
GOES_TRAINING = REPORT_DIR / "fire-goes19-2025q4-2026jan-training-report.json"
GOES_SSNMF = REPORT_DIR / "goes19-snmf-2026-jan-event-audit.json"
WRF_SSNMF_2025 = REPORT_DIR / "fire-smn-wrf-snmf-2025-event-test.json"
MAPBIOMAS_2025 = REPORT_DIR / "fire-mapbiomas-snmf-route-month-2025.json"
GFS_EPISODES = REPORT_DIR / "fire-gfs-24h-snmf-2026-jan-alert-episodes.json"
SNMF_2026_JAN = REPORT_DIR / "snmf-2026-jan-daily-occurrence-events.json"
SNMF_2022 = REPORT_DIR / "snmf-2022-daily-occurrence-events.json"
GOES_SHORT_LEAD = REPORT_DIR / "fire-goes19-short-lead-route-sector-evaluation.json"
GOES_FIRMS_CROSSCHECK = REPORT_DIR / "fire-goes19-alert-firms-crosscheck-2026-jan.json"
GOES_TRAIL_10KM = REPORT_DIR / "fire-goes19-full-trail-10km-evaluation.json"
VIIRS_SWATH_COVERAGE = REPORT_DIR / "fire-viirs-full-swath-coverage-barda-2026-jan.json"
VIIRS_POSITIVE_SCREEN = REPORT_DIR / "fire-viirs-full-swath-barda-2026-jan-positive-screen.json"
VIIRS_GEOLOCATION_PILOT = REPORT_DIR / "fire-viirs-geolocation-pilot-barda-2026-jan.json"
VIIRS_GEOLOCATION_READINESS = REPORT_DIR / "fire-viirs-geolocation-companion-readiness-2026-jan.json"
VIIRS_ROUTE_OBSERVATIONS = REPORT_DIR / "fire-viirs-full-swath-route-observations-barda-2026-jan.json"
VIIRS_DAILY_L3_CANDIDATE = REPORT_DIR / "fire-viirs-daily-l3-candidate-audit-2026-10-23.json"
VIIRS_DAILY_L3_COHORT = REPORT_DIR / "fire-viirs-daily-l3-event-cohort-2023-2025.json"
VIIRS_DAILY_L3_EVENT_AUDIT = REPORT_DIR / "fire-viirs-daily-l3-snmf-event-audit-2023-2025.json"
VIIRS_NO_FIRE_MODEL_CROSSCHECK = REPORT_DIR / "fire-viirs-explicit-no-fire-model-crosscheck-2023.json"
VIIRS_JMA_NO_FIRE_CROSSCHECK = REPORT_DIR / "fire-viirs-jma-2024-explicit-no-fire-alert-crosscheck.json"
VIIRS_JMA_ALLROUTES_NO_FIRE = REPORT_DIR / "fire-viirs-jma-2024-explicit-no-fire-all-routes.json"
VIIRS_JMA_CMR_GAP_FILL = REPORT_DIR / "fire-viirs-jma-2024-cmr-gap-fill-noaa20-21.json"
NOAA_EFIRE_BARDA = REPORT_DIR / "fire-viirs-efire-barda-route-mask-2026-01-05.json"
VIIRS_SNMF_2025 = REPORT_DIR / "fire-viirs-snmf-event-route-pass-audit-2025.json"
FIRMS_NRT_PROSPECTIVE = REPORT_DIR / "fire-nasa-firms-nrt-route-crosscheck-2026-10-22-23.json"
FIRMS_STANDARD_AVAILABILITY = REPORT_DIR / "fire-firms-standard-availability-2026-10-23.json"
INPE_PROSPECTIVE_PARTIAL = REPORT_DIR / "fire-inpe-prospective-partial-audit-2026-10-23.json"
INPE_PROSPECTIVE_FULL = REPORT_DIR / "fire-inpe-prospective-outcomes.json"
EFIRE_SCREEN_0430 = REPORT_DIR / "fire-viirs-efire-route-mask-2024-07-10-0430-n21.json"
EFIRE_SCREEN_1831 = REPORT_DIR / "fire-viirs-efire-route-mask-2024-07-10-1831-n21.json"
EFIRE_SCREEN_REPORT = REPORT_DIR / "fire-viirs-efire-route-mask-2024-07-10.md"
VIIRS_2024_CLEAR_COVERAGE = REPORT_DIR / "fire-viirs-2024-no-fire-clear-land-completeness.json"
GLOBAL_FIRE_ATLAS_ROUTE_IGNITIONS = REPORT_DIR / "fire-global-fire-atlas-route-ignitions-2022-2026.json"
IDECOR_FWI_PROSPECTIVE = ROOT / "training/data/environmental/private/idecor-fwi-route-snapshots/condorito-2026-10-23.json"
OUT = REPORT_DIR / "fire-reliability-gap-audit-2026-10-23.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def one_sided_exact_lower(successes: int, trials: int, confidence: float = 0.95) -> float | None:
    if not trials:
        return None
    if successes == 0:
        return 0.0
    return float(beta.ppf(1 - confidence, successes, trials - successes + 1))


def minimum_n(observed_fraction: float, lower_target: float) -> dict:
    for n in range(1, 100_001):
        k = math.ceil(n * observed_fraction)
        if k > n:
            continue
        lower = one_sided_exact_lower(k, n)
        if lower is not None and lower >= lower_target:
            return {
                "adjudicated_alerts": n,
                "true_alerts": k,
                "observed_precision": k / n,
                "one_sided_exact_95pct_lower_bound": lower,
            }
    raise RuntimeError("No sample size found")


def main() -> int:
    training = read(GOES_TRAINING)
    event_audit = read(GOES_SSNMF)
    wrf = read(WRF_SSNMF_2025)
    mapbiomas = read(MAPBIOMAS_2025)
    gfs_episodes = read(GFS_EPISODES)
    snmf_january = read(SNMF_2026_JAN)
    snmf_2022 = read(SNMF_2022)
    goes_short = read(GOES_SHORT_LEAD)
    firms_crosscheck = read(GOES_FIRMS_CROSSCHECK)
    goes_10km = read(GOES_TRAIL_10KM)
    viirs_swath = read(VIIRS_SWATH_COVERAGE)
    viirs_positive_screen = read(VIIRS_POSITIVE_SCREEN)
    viirs_geolocation_pilot = read(VIIRS_GEOLOCATION_PILOT)
    viirs_geolocation_readiness = read(VIIRS_GEOLOCATION_READINESS)
    viirs_route_observations = read(VIIRS_ROUTE_OBSERVATIONS)
    viirs_daily_l3_candidate = read(VIIRS_DAILY_L3_CANDIDATE)
    viirs_daily_l3_cohort = read(VIIRS_DAILY_L3_COHORT)
    viirs_daily_l3_event_audit = read(VIIRS_DAILY_L3_EVENT_AUDIT)
    viirs_no_fire_model_crosscheck = read(VIIRS_NO_FIRE_MODEL_CROSSCHECK)
    viirs_jma_no_fire_crosscheck = read(VIIRS_JMA_NO_FIRE_CROSSCHECK)
    viirs_jma_allroutes_no_fire = read(VIIRS_JMA_ALLROUTES_NO_FIRE)
    viirs_jma_cmr_gap_fill = read(VIIRS_JMA_CMR_GAP_FILL)
    noaa_efire_barda = read(NOAA_EFIRE_BARDA)
    viirs_snmf_2025 = read(VIIRS_SNMF_2025)
    firms_nrt_prospective = read(FIRMS_NRT_PROSPECTIVE)
    firms_standard_availability = read(FIRMS_STANDARD_AVAILABILITY)
    inpe_prospective_partial = read(INPE_PROSPECTIVE_PARTIAL)
    inpe_prospective_full = read(INPE_PROSPECTIVE_FULL)
    efire_screens = [read(EFIRE_SCREEN_0430), read(EFIRE_SCREEN_1831)]
    viirs_2024_clear_coverage = read(VIIRS_2024_CLEAR_COVERAGE)
    global_fire_atlas_route_ignitions = read(GLOBAL_FIRE_ATLAS_ROUTE_IGNITIONS)
    idecor_fwi_prospective = read(IDECOR_FWI_PROSPECTIVE)

    # Match frozen GOES alert episodes to VIIRS observations only when a sensor passed during the alert interval.
    # This is a descriptive check, not an adjudication of model alerts.
    goes_viirs_exact_time = []
    for episode in firms_crosscheck["alert_episode_matches"]:
        if episode["route_sector"] != viirs_route_observations["route"]:
            goes_viirs_exact_time.append({"episode_index": episode["episode_index"], "status": "outside_viirs_route_cohort", "matched_overpasses": []})
            continue
        start = datetime.fromisoformat(episode["alert_start_hour_utc"] + ":00:00+00:00")
        end = datetime.fromisoformat(episode["alert_end_hour_utc"] + ":59:59+00:00")
        matched = []
        for overpass in viirs_route_observations["per_overpass"]:
            acquisition = datetime.fromisoformat(overpass["acquisition_start_utc"].replace("Z", "+00:00"))
            if start <= acquisition <= end:
                classes = overpass["mask_classes_within_10km_of_route"]
                matched.append({
                    "acquisition_start_utc": overpass["acquisition_start_utc"],
                    "quality_valid_pixels": overpass["qa_valid_geolocated_pixels_within_10km_of_route"],
                    "clear_land_class_5_pixels": int(classes["5"]),
                    "active_fire_classes_7_to_9_pixels": sum(int(classes[str(code)]) for code in (7, 8, 9)),
                })
        goes_viirs_exact_time.append({
            "episode_index": episode["episode_index"],
            "alert_start_hour_utc": episode["alert_start_hour_utc"],
            "alert_end_hour_utc": episode["alert_end_hour_utc"],
            "status": "matched_observation" if matched else "no_viirs_overpass_during_alert",
            "matched_overpasses": matched,
        })


    one_hour = training["rows_by_horizon"]["1"]["test"]
    persistence = one_hour["persistence_baseline"]
    active_covered = int(event_audit["active_or_controlled_incidents_with_coverage"])
    active_alerted = int(event_audit["active_or_controlled_incidents_with_model_alert"])
    active_persistence = int(event_audit["active_or_controlled_incidents_with_persistence_alert"])

    sample_targets = {
        "precision_at_least_0_80_with_observed_at_least_0_90": minimum_n(0.90, 0.80),
        "precision_at_least_0_90_with_observed_at_least_0_95": minimum_n(0.95, 0.90),
        "precision_at_least_0_90_if_every_alert_is_correct": minimum_n(1.0, 0.90),
    }
    snmf_2022_rows = snmf_2022["deduplicated_events"]
    snmf_2022_rows_with_coordinates = sum(
        isinstance(row.get("latitude"), (int, float))
        and isinstance(row.get("longitude"), (int, float))
        for row in snmf_2022_rows
    )
    source_paths = [GOES_TRAINING, GOES_SSNMF, WRF_SSNMF_2025, MAPBIOMAS_2025, GFS_EPISODES, SNMF_2026_JAN, SNMF_2022,
                    GOES_SHORT_LEAD, GOES_FIRMS_CROSSCHECK, GOES_TRAIL_10KM, VIIRS_SWATH_COVERAGE,
                    VIIRS_POSITIVE_SCREEN, VIIRS_GEOLOCATION_PILOT, VIIRS_GEOLOCATION_READINESS,
                    VIIRS_ROUTE_OBSERVATIONS, VIIRS_DAILY_L3_CANDIDATE, VIIRS_DAILY_L3_COHORT,
                    VIIRS_DAILY_L3_EVENT_AUDIT, VIIRS_NO_FIRE_MODEL_CROSSCHECK,
                    VIIRS_JMA_NO_FIRE_CROSSCHECK,
                    VIIRS_JMA_ALLROUTES_NO_FIRE,
                    VIIRS_JMA_CMR_GAP_FILL,
                    NOAA_EFIRE_BARDA, VIIRS_SNMF_2025, FIRMS_NRT_PROSPECTIVE,
                    FIRMS_STANDARD_AVAILABILITY, INPE_PROSPECTIVE_PARTIAL, INPE_PROSPECTIVE_FULL,
                    EFIRE_SCREEN_0430, EFIRE_SCREEN_1831, EFIRE_SCREEN_REPORT,
                    VIIRS_2024_CLEAR_COVERAGE]
    source_paths.append(GLOBAL_FIRE_ATLAS_ROUTE_IGNITIONS)
    source_paths.append(IDECOR_FWI_PROSPECTIVE)
    report = {
        "experiment_id": "fire-reliability-gap-audit-2026-10-23",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "no_candidate_meets_independent_reliability_evidence",
        "candidate": {
            "name": "GOES-19 logistic forecast, 1-hour horizon",
            "test_period": training["temporal_split"],
            "test_pixel_label_metrics": {
                "average_precision": one_hour["average_precision"],
                "persistence_average_precision": persistence["average_precision"],
                "precision_at_0_5": one_hour["precision_at_0_5"],
                "recall_at_0_5": one_hour["recall_at_0_5"],
                "persistence_precision_at_0_5": persistence["precision"],
                "persistence_recall_at_0_5": persistence["recall"],
                "positive_pixel_scans": one_hour["positives"],
                "positive_region_days": training["rows_by_horizon"]["1"]["positive_region_days_by_partition"]["test"],
                "warning": "These are repeated pixel-scan labels, not independent physical fire events or trail-level precision.",
            },
            "independent_snmf_event_check": {
                "coverage_days": event_audit["test_days_with_predictions"],
                "active_or_controlled_incidents_with_coverage": active_covered,
                "incidents_alerted": active_alerted,
                "event_coincidence_fraction_on_covered_subset": active_alerted / active_covered if active_covered else None,
                "wilson_95pct_interval_reported": event_audit["event_coincidence_sensitivity_wilson_95pct"],
                "persistence_alerted_incidents": active_persistence,
                "total_snmf_incidents_without_test_day_coverage": event_audit["snmf_incidents_without_test_day_pixel_coverage"],
                "warning": "This is event coincidence/sensitivity among covered official reports, not alert precision; the incident archive cannot label every alert as false or true.",
            },
            "independent_wrf_snmf_check": {
                "event_days": wrf["result"]["alerts_on_scored_event_days"] + wrf["result"]["misses_on_scored_event_days"],
                "alerts": wrf["result"]["alerts_on_scored_event_days"],
                "misses": wrf["result"]["misses_on_scored_event_days"],
                "note": "Small selected cohort; diagnostic threshold and approximately 27-hour issue-to-valid interval do not establish reliability.",
            },
            "short_lead_route_sector_test": {
                "horizons_hours": list(goes_short["results_by_horizon"]),
                "threshold_selected_by_validation": {
                    horizon: item["validation_threshold"]["selected"]
                    for horizon, item in goes_short["results_by_horizon"].items()
                },
                "one_hour_validation_best_with_minimum_alerts": goes_short["results_by_horizon"]["1"]["validation_threshold"]["best_validation_precision_with_at_least_minimum_alerts"],
                "one_hour_january_test_diagnostic": goes_short["results_by_horizon"]["1"]["test_at_fixed_0_5_diagnostic"],
                "warning": "The unit is a GOES detection proxy in a fixed 20 km sampled sector; the model did not pass validation and January alerts cluster around one ongoing regional incident.",
            },
            "firms_independent_satellite_crosscheck": {
                "product": firms_crosscheck["firms_product"],
                "raw_hotspot_rows": firms_crosscheck["raw_firms_route_detection_rows"],
                "confidence_counts": firms_crosscheck["raw_firms_confidence_counts"],
                "sensor_breakdown": firms_crosscheck["firms_by_sensor"],
                "nearest_hotspot_to_trail_km": firms_crosscheck["raw_firms_nearest_route_distance_km"],
                "episodes_with_detection_within_24h_at_10km": firms_crosscheck["route_radius_summary"]["10"]["episodes_with_at_least_one_detection_within_24h"],
                "episodes_with_detection_within_24h_at_20km": firms_crosscheck["route_radius_summary"]["20"]["episodes_with_at_least_one_detection_within_24h"],
                "SNMF_incident_point_crosscheck": firms_crosscheck["snmf_incident_point_crosscheck"],
                "precision_estimable": False,
                "warning": "The alert-selected FIRMS cohort is positive-only; its 20 km coincidences are regional and repeated rows refer to an ongoing event. No detection is not a verified no-fire label.",
            },
            "full_trail_10km_frozen_GOES_sensitivity": {
                "sampled_core_pixels_by_route": goes_10km["protocol"]["sampled_core_pixels_by_route"],
                "one_hour_training_positive_route_hours": goes_10km["results_by_horizon"]["1"]["training_positive_route_hours"],
                "one_hour_validation_positive_route_hours": goes_10km["results_by_horizon"]["1"]["validation"]["positive_route_sector_hours"],
                "one_hour_test_positive_route_hours": goes_10km["results_by_horizon"]["1"]["test_at_fixed_0_5_diagnostic"]["positive_route_sector_hours"],
                "one_hour_test_alerts_at_diagnostic_0_5": goes_10km["results_by_horizon"]["1"]["test_at_fixed_0_5_diagnostic"]["alerts"],
                "independent_near_route_event_check": goes_10km["independent_near_route_event_check"],
                "warning": "No GOES positives occurred in the 10 km validation or test labels, so precision cannot be estimated; a nearby official SNMF incident had valid pixels but no model alert.",
            },
        "gfs_24h_snmf_daily_report_proxy_episode_check": {
            "model": gfs_episodes["model"]["summary"],
            "persistence": gfs_episodes["persistence"]["summary"],
            "warning": "Consecutive route-day alert streaks against an incomplete SNMF report proxy are not physical fire precision or independent fire-event counts.",
        },
        "snmf_daily_negative_label_audit": {
            "archive_dates_with_pdf": snmf_january["extraction"]["reports_used"],
            "dates_without_pdf": 31 - snmf_january["extraction"]["reports_used"],
            "reports_with_zero_parsed_events": snmf_january["extraction"]["reports_with_zero_parsed_events"],
            "parsed_snapshot_rows": snmf_january["extraction"]["snapshot_rows"],
            "interpretation": "No report in the acquired January archive was an empty national event report. This cohort cannot supply explicit nationwide no-fire days; no nearby event in a daily PDF remains a report-based proxy, not a verified physical negative.",
            "limitations": snmf_january["limitations"],
        },
        "snmf_2022_route_cohort_readiness": {
            "source_report_rows": snmf_2022["extraction"]["snapshot_rows"],
            "deduplicated_extracted_records": len(snmf_2022_rows),
            "records_with_numeric_coordinates": snmf_2022_rows_with_coordinates,
            "rows_without_coordinates_in_source_snapshots": snmf_2022["extraction"]["missing_coordinate_snapshot_rows"],
            "reports_used": snmf_2022["extraction"]["reports_used"],
            "reports_with_zero_parsed_events": snmf_2022["extraction"]["reports_with_zero_parsed_events"],
            "source_file_sha256": sha256(SNMF_2022),
            "route_event_cohort_can_be_expanded": snmf_2022_rows_with_coordinates > 0,
            "interpretation": "The archived 2022 extraction has no records with numeric latitude/longitude, so it cannot extend a route-specific event cohort. This is missing spatial information in the extraction, not evidence of no incidents or fire-free days. The original PDFs or a geocoded incident registry are needed to recover spatial labels.",
            "limitations": snmf_2022["limitations"],
        },
        },
        "external_label_audit": {
            "mapbiomas_2025_incident_coordinates": mapbiomas["summary"]["deduplicated_incident_coordinates"],
            "same_month_scar_within_2km": mapbiomas["summary"]["same_month_pixel_coincidences_by_incident_radius_m"]["2000"],
            "official_product_page": "https://argentina.mapbiomas.org/iniciativas-y-productos/fuego/",
            "official_collection_launch": "https://argentina.mapbiomas.org/2026/10/05/argentina-tiene-mas-superficie-agropecuaria-que-bosques-los-nuevos-datos-de-mapbiomas-muestran-como-cambio-el-territorio-desde-1985/",
            "monthly_year_coverage_verified_by_audit": "1999-2025; 27 annual and 27 monthly GeoTIFF objects listed in the public bucket; the 2025 raster checksum was verified.",
            "limitations": [
                "Monthly retrospective scar pixels do not establish ignition time or future prediction accuracy.",
                "The product page text still summarizes monthly maps as 2013-2024, while MapBiomas's September 2026 collection launch states monthly and annual products for 1999-2025; the public-bucket inventory and verified 2025 raster support the extended coverage.",
            ],
        },
        "minimum_independent_alert_evidence_examples": {
            "method": "One-sided 95% exact Clopper-Pearson lower bound. Alerts must be adjudicated against independent labels and be independent episodes; repeated pixels, scans, and adjacent days do not count separately.",
            "targets": sample_targets,
            "warning": "These are precision-only sample-size examples. They do not provide power for recall, calibrate a probability, validate lead time, or account for event clustering beyond the unit definition.",
        },
        "frozen_modis_model_independent_viirs_crosscheck_on_explicit_no_fire_reports_2023": {
            "status": viirs_no_fire_model_crosscheck["status"],
            "model_test_route_days": viirs_no_fire_model_crosscheck["coverage"]["frozen_model_route_days"],
            "same_day_route_buffers_with_viirs_fire_detections": viirs_no_fire_model_crosscheck["coverage"]["route_days_with_any_viirs_fire_detection"],
            "route_days_with_some_class5_land_observation": viirs_no_fire_model_crosscheck["coverage"]["route_days_with_at_least_one_class5_qa_land_sample"],
            "route_days_without_class5_land_observation": viirs_no_fire_model_crosscheck["coverage"]["route_days_without_class5_qa_land_sample"],
            "unique_logistic_or_xgboost_alert_route_days_at_0_5": viirs_no_fire_model_crosscheck["coverage"]["unique_logistic_or_xgboost_alert_route_days_at_0_5"],
            "those_alert_route_days_with_class5_land_samples": viirs_no_fire_model_crosscheck["coverage"]["such_alert_route_days_with_class5_qa_land_sample"],
            "those_alert_route_days_with_viirs_detections": viirs_no_fire_model_crosscheck["coverage"]["such_alert_route_days_with_viirs_fire_detection"],
            "crosscheck_by_model": viirs_no_fire_model_crosscheck["crosscheck_by_model"],
            "interpretation": "No VIIRS class 7-9 detections corroborated the logistic/XGBoost alerts in this small test. Two route buffers had no class-5 land sample; even class-5 samples are partial, so these are not verified physical-fire negatives and do not estimate model precision.",
            "report": VIIRS_NO_FIRE_MODEL_CROSSCHECK.with_suffix(".md").name,
        },
        "frozen_jma_2024_alert_independent_viirs_crosscheck_on_explicit_no_fire_reports": {
            "status": viirs_jma_no_fire_crosscheck["status"],
            "diagnostic_threshold": viirs_jma_no_fire_crosscheck["protocol"]["threshold"],
            "threshold_is_calibrated_probability": viirs_jma_no_fire_crosscheck["protocol"]["threshold_is_calibrated_probability"],
            "requested_route_alerts": viirs_jma_no_fire_crosscheck["acquisition"]["requested_route_alerts"],
            "observed_route_alerts": viirs_jma_no_fire_crosscheck["acquisition"]["observed_route_alerts"],
            "unavailable_route_alerts": viirs_jma_no_fire_crosscheck["acquisition"]["unavailable_route_alerts"],
            "verified_viirs_granules": viirs_jma_no_fire_crosscheck["acquisition"]["verified_granules"],
            "alert_route_days_with_viirs_detections": viirs_jma_no_fire_crosscheck["coverage"]["route_alerts_with_any_viirs_fire_detection"],
            "alert_route_days_with_some_class5_land_observation": viirs_jma_no_fire_crosscheck["coverage"]["route_alerts_with_at_least_one_class5_qa_land_sample"],
            "limitations": viirs_jma_no_fire_crosscheck["limitations"],
            "report": VIIRS_JMA_NO_FIRE_CROSSCHECK.with_suffix(".md").name,
        },
        "viirs_observations_on_all_route_days_with_2024_explicit_no_fire_reports": {
            "status": viirs_jma_allroutes_no_fire["status"],
            "explicit_no_fire_report_dates": viirs_jma_allroutes_no_fire["cohort"]["explicit_no_fire_report_dates"],
            "adjacent_date_clusters": viirs_jma_allroutes_no_fire["cohort"]["adjacent_date_clusters"],
            "requested_route_days": viirs_jma_allroutes_no_fire["cohort"]["requested_route_days"],
            "observed_route_days": viirs_jma_allroutes_no_fire["cohort"]["observed_route_days"],
            "unobserved_route_days": viirs_jma_allroutes_no_fire["cohort"]["unobserved_route_days"],
            "dates_without_any_matching_cmr_tile": viirs_jma_allroutes_no_fire["cohort"]["dates_without_any_matching_cmr_tile"],
            "route_days_with_viirs_classes_7_9": viirs_jma_allroutes_no_fire["observations"]["route_days_with_viirs_classes_7_9"],
            "route_days_with_some_class5_land_observation": viirs_jma_allroutes_no_fire["observations"]["route_days_with_some_class5_qa_land_sample"],
            "route_days_without_class5_land_observation": viirs_jma_allroutes_no_fire["observations"]["route_days_without_class5_qa_land_sample"],
            "fixed_0_1_alert_route_days_observed": viirs_jma_allroutes_no_fire["observations"]["fixed_0_1_alert_route_days_observed"],
            "fixed_0_1_alerts_with_viirs_classes_7_9": viirs_jma_allroutes_no_fire["observations"]["fixed_0_1_alerts_with_viirs_classes_7_9"],
            "interpretation": "This is an observation-coverage and sensor-coincidence audit on selected administrative no-fire report dates. Missing detections are not verified physical negatives, and the selected cohort does not estimate predictive precision or recall.",
            "report": VIIRS_JMA_ALLROUTES_NO_FIRE.with_suffix(".md").name,
        },
        "viirs_noaa20_21_gap_fill_for_2024_s_npp_missing_dates": {
            "status": viirs_jma_cmr_gap_fill["status"],
            "gap_dates": viirs_jma_cmr_gap_fill["acquisition"]["gap_dates"],
            "verified_granules": viirs_jma_cmr_gap_fill["acquisition"]["granules_verified"],
            "sensor_route_day_observations": viirs_jma_cmr_gap_fill["acquisition"]["sensor_route_day_observations"],
            "missing_s_npp_route_days_supplemented": viirs_jma_cmr_gap_fill["acquisition"]["gap_route_days"],
            "noaa20_route_days_with_fire_mask_7_9": viirs_jma_cmr_gap_fill["observations_by_sensor"]["NOAA-20"]["route_days_with_fire_mask_7_9"],
            "noaa21_route_days_with_fire_mask_7_9": viirs_jma_cmr_gap_fill["observations_by_sensor"]["NOAA-21"]["route_days_with_fire_mask_7_9"],
            "combined_gap_route_days_with_class5_qa_land": viirs_jma_cmr_gap_fill["combined_gap_route_days"]["route_days_with_any_class5_qa_land_sample"],
            "combined_gap_route_days_with_complete_clear_coverage": viirs_jma_cmr_gap_fill["combined_gap_route_days"]["route_days_with_complete_fire_free_coverage"],
            "full_2024_route_days_observed_after_gap_fill": viirs_jma_cmr_gap_fill["full_2024_no_fire_cohort_after_gap_fill"]["route_days_requested"] - viirs_jma_cmr_gap_fill["full_2024_no_fire_cohort_after_gap_fill"]["still_unobserved_route_days"],
            "full_2024_route_days_with_any_viirs_fire_detection": viirs_jma_cmr_gap_fill["full_2024_no_fire_cohort_after_gap_fill"]["route_days_with_at_least_one_viirs_fire_detection_across_available_platforms"],
            "diagnostic_alert_routes_filled": viirs_jma_cmr_gap_fill["fixed_threshold_alert_crosscheck"]["alert_route_days_filled_by_noaa_gap_data"],
            "diagnostic_alerts_with_noaa_viirs_detections": viirs_jma_cmr_gap_fill["fixed_threshold_alert_crosscheck"]["alert_route_days_with_any_noaa_viirs_fire_detection"],
            "limitations": viirs_jma_cmr_gap_fill["limitations"],
            "report": VIIRS_JMA_CMR_GAP_FILL.with_suffix(".md").name,
        },
        "daily_viirs_l3_label_candidate": {
            "status": viirs_daily_l3_event_audit["status"],
            "preflight_metadata_status": viirs_daily_l3_candidate["status"],
            "products": viirs_daily_l3_candidate["products"],
            "unique_route_buffer_tiles": viirs_daily_l3_candidate["spatial_sampling"]["unique_tiles"],
            "spatial_resolution_m": viirs_daily_l3_candidate["product_metadata"]["grid_resolution_m"],
            "temporal_composite_hours": viirs_daily_l3_candidate["product_metadata"]["composite_period_hours"],
            "local_acquisition_status": {
                "granules_downloaded_and_hash_verified": viirs_daily_l3_event_audit["acquisition"]["granules_expected_and_verified"],
                "total_size_mb_decimal": viirs_daily_l3_event_audit["acquisition"]["size_mb_decimal"],
                "masks_decoded": viirs_daily_l3_event_audit["acquisition"]["granules_expected_and_verified"],
                "model_metrics_created": False,
                "deployment_approved": False,
            },
            "report": VIIRS_DAILY_L3_CANDIDATE.with_suffix(".md").name,
            "snmf_event_pilot_cohort": {
                "status": viirs_daily_l3_cohort["status"],
                "selected_route_event_clusters": viirs_daily_l3_cohort["selection"]["selected_route_event_clusters"],
                "event_dates": viirs_daily_l3_cohort["acquisition_plan"]["event_dates"],
                "maximum_granules_before_deduplication": viirs_daily_l3_cohort["acquisition_plan"]["maximum_granules_before_deduplication"],
                "downloaded_granules": viirs_daily_l3_cohort["acquisition_plan"]["downloaded_granules"],
                "existing_375m_same_day_event_coordinate_check": {
                    "selected_2025_events": viirs_daily_l3_cohort["existing_375m_same_day_event_coordinate_check"]["selected_2025_events"],
                    "status_counts": viirs_daily_l3_cohort["existing_375m_same_day_event_coordinate_check"]["status_counts"],
                    "interpretation": viirs_daily_l3_cohort["existing_375m_same_day_event_coordinate_check"]["interpretation"],
                },
                "daily_l3_download_and_independent_positive_event_check": {
                    "status": viirs_daily_l3_event_audit["status"],
                    "verified_granules": viirs_daily_l3_event_audit["acquisition"]["granules_expected_and_verified"],
                    "verified_size_mb": viirs_daily_l3_event_audit["acquisition"]["size_mb_decimal"],
                    "unique_report_route_dates": viirs_daily_l3_event_audit["route_date_positive_event_coincidence"]["route_dates_with_snmf_event_cluster"],
                    "route_dates_with_same_day_viirs_detection_within_10km": viirs_daily_l3_event_audit["route_date_positive_event_coincidence"]["route_dates_with_same_day_viirs_fire_detection_within_10km_of_report_point"],
                    "descriptive_event_coincidence_fraction": viirs_daily_l3_event_audit["route_date_positive_event_coincidence"]["descriptive_event_coincidence_fraction"],
                    "coverage_by_sensor": viirs_daily_l3_event_audit["coverage_by_sensor"],
                    "warning": viirs_daily_l3_event_audit["route_date_positive_event_coincidence"]["warning"],
                    "report": VIIRS_DAILY_L3_EVENT_AUDIT.with_suffix(".md").name,
                },
                "report": VIIRS_DAILY_L3_COHORT.with_suffix(".md").name,
            },
            "interpretation": "The daily L3 positive-event pilot is downloaded and decoded. It corroborates only 2 of 15 selected SNMF route-dates with a same-day VIIRS fire pixel within 10 km; report-point cells are clear-land samples, and the cohort has no verified negatives. This is independent event-coincidence evidence, not model precision or a physical-fire false-negative rate.",
        },
        "full_swath_viirs_observation_candidate": {
            "target_incident": viirs_swath["target_incident"],
            "products": {
                product: {
                    "unique_sensor_overpass_times": row["unique_sensor_overpass_times"],
                    "reported_total_size_mb": row["reported_total_size_mb"],
                    "overpasses_by_utc_day": row["overpasses_by_utc_day"],
                }
                for product, row in viirs_swath["granules_by_product"].items()
            },
            "total_unique_overpasses": viirs_swath["total_unique_sensor_overpass_times"],
            "reported_download_size_mb": viirs_swath["reported_total_granule_size_mb"],
            "fire_mask_classes": viirs_swath["observation_mask_semantics"],
            "swath_data_downloaded": viirs_positive_screen["source"]["downloaded_and_hash_verified_overpasses"] == viirs_swath["total_unique_sensor_overpass_times"],
            "downloaded_and_hash_verified_overpasses": viirs_positive_screen["source"]["downloaded_and_hash_verified_overpasses"],
            "download_size_mb": viirs_positive_screen["source"]["reported_download_size_mb"],
            "positive_detection_screen": viirs_positive_screen["summary"],
            "positive_screen_report": VIIRS_POSITIVE_SCREEN.name,
            "geolocation_pilot": {
                "acquisition_utc": viirs_geolocation_pilot["acquisition_utc"],
                "paired_geolocation_granules_downloaded": 1,
                "downloaded_bytes": viirs_geolocation_pilot["source"]["geolocation_downloaded_bytes"],
                "downloaded_size_mb": viirs_geolocation_pilot["source"]["geolocation_downloaded_size_mb"],
                "summary": viirs_geolocation_pilot["summary"],
                "report": VIIRS_GEOLOCATION_PILOT.with_suffix(".md").name,
                "interpretation": "One exact-time mask/geolocation pair yielded quality-valid class-5 clear-land observations near the route. This validates a path to observed non-detection labels for individual overpasses, not physical no-fire labels or model precision.",
            },
            "geolocation_companion_cohort_readiness": {
                "matching_overpasses": viirs_geolocation_readiness["exact_time_matches"],
                "expected_overpasses": viirs_geolocation_readiness["expected_overpasses"],
                "estimated_total_download_mb": viirs_geolocation_readiness["reported_total_size_mb"],
                "downloaded_and_hash_verified_overpasses": viirs_route_observations["source"]["verified_geolocation_granules"],
                "actual_download_bytes": viirs_route_observations["source"]["geolocation_downloaded_bytes"],
                "actual_download_size_gb_decimal": viirs_route_observations["source"]["geolocation_downloaded_size_gb_decimal"],
                "status": "all_61_companions_downloaded_and_hash_verified",
                "report": VIIRS_GEOLOCATION_READINESS.with_suffix(".md").name,
                "cmr_response_sha256_by_product": {
                    name: row["cmr_response_sha256"]
                    for name, row in viirs_geolocation_readiness["products"].items()
                },
                "interpretation": "All exact-time companions were downloaded and hash-verified; their actual local size is reported above. The evidence still covers only one seven-day corridor case.",
            },
            "full_route_observation_screen": {
                "period_utc": viirs_route_observations["period_utc"],
                "verified_exact_time_pairs": viirs_route_observations["source"]["verified_exact_time_pairs"],
                "summary": viirs_route_observations["summary"],
                "report": VIIRS_ROUTE_OBSERVATIONS.with_suffix(".md").name,
                "interpretation": "Across 61 same-week sensor passes, 60 contained quality-valid class-5 clear-land pixels within the 10 km route buffer, and none contained a quality-screened classes 7, 8 or 9 detection there. These repeated observations from one corridor and short event window are not 61 independent fire/no-fire cases; SNMF lacks an exact ignition time. This improves observation coverage labels but cannot estimate model precision.",
            },
            "goes_alerts_same_time_viirs_observation_check": {
                "episodes": goes_viirs_exact_time,
                "interpretation": "Only VIIRS passes acquired during a GOES alert interval are listed. Class 5 is a clear-land non-detection at that pass; it does not establish an alert as false because this is one corridor and the incident labels lack exact ignition time.",
            },
            "interpretation": "All 61 full-swath fire-mask granules and their 61 exact-time geolocation companions were downloaded and hash-verified (9.143 GB actual companion size). Across the 10 km route buffer, 60 passes had quality-valid class-5 clear-land pixels; none had a quality-screened classes 7, 8 or 9 detection, and one pass had no eligible clear-land pixel. These repeated observations from one corridor do not establish event truth or estimate model precision.",
        },
        "historical_viirs_snmf_event_route_screen_2025": {
            "results_summary": viirs_snmf_2025["results_summary"],
            "event_coordinate_cross_check": {
                "granules_with_full_geolocation_audit": viirs_snmf_2025["snmf_event_coordinate_cross_check"]["granules_with_full_geolocation_audit"],
                "unique_event_coordinates": viirs_snmf_2025["snmf_event_coordinate_cross_check"]["unique_event_coordinates"],
                "mask_status_counts": viirs_snmf_2025["snmf_event_coordinate_cross_check"]["mask_status_counts"],
            },
            "report": VIIRS_SNMF_2025.name,
            "interpretation": "The 2025 archive has clear-land observations at some reported incident coordinates, but dates are report start dates, not exact ignition or sensor times. No fire-class pixel was found on sampled route vertices in this screened cohort; it is a coverage and label feasibility check, not a prediction evaluation.",
        },
        "noaa_efire_barda_case_study": {
            "target_incident": noaa_efire_barda["target_incident"],
            "verified_public_source_files": noaa_efire_barda["source"]["files_hash_verified"],
            "source_size_mb": round(noaa_efire_barda["source"]["total_bytes"] / 1_000_000, 2),
            "passes": [
                {
                    "sensor": row["platform"],
                    "start_utc": row["acquisition_start_utc"],
                    "sampled_route_vertices": row["route_observation"]["sampled_vertices"],
                    "clear_land_dqf1_route_vertices": row["route_observation"]["clear_land_dqf1_vertices"],
                    "bowtie_route_vertices": row["route_observation"]["bowtie_vertices"],
                    "quality_valid_clear_land_at_snmf_point": row["snmf_point_observation"]["clear_land_dqf1"],
                }
                for row in noaa_efire_barda["passes"]
            ],
            "report": NOAA_EFIRE_BARDA.with_suffix(".md").name,
            "interpretation": "Two full-geolocation NOAA E-FIRE passes observed quality-valid clear land at the Barda coordinate; one pass had all 103 sampled trail vertices clear, the next had 44 clear and 59 bowtie. This is a useful pixel-level non-detection case, but one reported event and two passes without exact ignition time cannot validate model precision or establish physical absence.",
        },
        "noaa_efire_route_overpasses_2024_07_10": {
            "passes": [
                {
                    "start_utc": audit["source"]["time_coverage_start"],
                    "route_observations": [
                        {
                            "route": row["route"],
                            "sampled_vertices": row["sampled_vertices"],
                            "resolved_vertices": row["vertices_resolved_to_swath_pixels"],
                            "mask_and_dqf_counts": row["nearest_pixel_mask_and_dqf_counts"],
                        }
                        for row in audit["per_route"] if row["vertices_resolved_to_swath_pixels"]
                    ],
                }
                for audit in efire_screens
            ],
            "report": EFIRE_SCREEN_REPORT.name,
            "interpretation": "The 18:31 UTC overpass had cloud-class pixels at all 127 sampled Condorito vertices, so the nearby JMA alert remains unverified by this pass. Che Roga had 117 clear-land samples with no fire class 7-9. Frey and Bosque Tallado had only cloud or bowtie samples. These are single-pass pixel observations, not independent fire/no-fire route-days and do not change model precision evidence.",
        },
        "nasa_firms_nrt_prospective_crosscheck": {
            "target_window_utc": firms_nrt_prospective["target_window_utc"],
            "sensors": firms_nrt_prospective["source"]["sensors"],
            "route_sensor_queries": firms_nrt_prospective["summary"]["route_sensor_queries"],
            "raw_responses_verified": firms_nrt_prospective["source"]["raw_responses_verified"],
            "raw_csv_records_all_areas": firms_nrt_prospective["summary"]["raw_csv_records_all_areas"],
            "route_matches_in_exact_forecast_window": firms_nrt_prospective["summary"]["route_matches_in_exact_forecast_window"],
            "negative_labels_created": firms_nrt_prospective["summary"]["negative_labels_created"],
            "report": FIRMS_NRT_PROSPECTIVE.with_suffix(".md").name,
            "interpretation": "All 24 archived NOAA/NASA FIRMS NRT queries for the two date range returned valid empty CSVs, with no records within 10 km of the eight full route polylines. NRT is a provisional positive-only source; this empty snapshot is not a no-fire observation or a precision estimate. The period should be refreshed from standard processing after NASA's product lag.",
        },
        "nasa_firms_standard_availability_for_prospective_window": {
            "target_window_utc_dates": firms_standard_availability["target_window_utc_dates"],
            "latest_standard_date_available_any_sensor": firms_standard_availability["summary"]["latest_standard_date_available_any_sensor"],
            "days_behind_target_end_date": firms_standard_availability["summary"]["days_behind_target_end_date"],
            "route_sensor_requests_outside_range": firms_standard_availability["summary"]["outside_available_date_range"],
            "detection_queries_made": firms_standard_availability["summary"]["detection_queries_made"],
            "availability_response_sha256": firms_standard_availability["source"]["availability_response_sha256"],
            "report": FIRMS_STANDARD_AVAILABILITY.with_suffix(".md").name,
            "interpretation": "At query time on 2026-10-23, NASA FIRMS VIIRS standard products were available only through 2026-06-30, 115 days before the target end date; no standard detections could be queried for the prospective window. This is missing product availability, not evidence of no fire.",
        },
        "inpe_prospective_window_status": {
            "partial_screen_as_of_utc": inpe_prospective_partial["as_of_utc"],
            "unique_forecast_windows": inpe_prospective_partial["summary"]["unique_forecast_windows"],
            "windows_with_matured_csv_segments": inpe_prospective_partial["summary"]["windows_with_any_matured_daily_csv_segment"],
            "complete_24h_matured_csv_windows": inpe_prospective_partial["summary"]["windows_with_24h_of_matured_daily_csv_segments"],
            "partial_route_detections": inpe_prospective_partial["summary"]["total_route_detection_records_in_available_files"],
            "full_window_status_counts": inpe_prospective_full["counts"],
            "negative_labels_created": 0,
            "partial_report": INPE_PROSPECTIVE_PARTIAL.with_suffix(".md").name,
            "full_window_report": "fire-inpe-prospective-outcomes-2026-10-23.md",
            "interpretation": "The refreshed daily INPE file has no listed detections within 10 km of the complete route polylines in the available partial intervals. The Oct 23 CSV remains immature and active-fire rows are not a sensor-coverage mask. Three forecast windows are waiting for an immature CSV and five for missing CSVs; no complete 24-hour outcome or precision estimate is available.",
        },
        "route_geometry_for_prospective_join": {
            "sha256": inpe_prospective_partial["route_geometry_sha256"],
            "detection_spatial_rule": inpe_prospective_partial["spatial_rule"],
            "forecast_index_spatial_rule": "INPE risk values remain sampled at route-sector centers.",
            "interpretation": "The observation join now uses complete reviewed trail polylines; the forecast raster sampling is still center-based.",
        },
        "viirs_clear_land_completeness_on_2024_explicit_no_fire_reports": {
            "route_days": viirs_2024_clear_coverage["summary"]["route_days"],
            "report_date_clusters": viirs_2024_clear_coverage["summary"]["adjacent_report_date_clusters"],
            "route_days_with_fire_class_7_9": viirs_2024_clear_coverage["summary"]["route_days_with_fire_class_7_9_on_any_sensor"],
            "coverage_at_least_90pct": viirs_2024_clear_coverage["summary"]["clear_land_coverage_thresholds"]["0.9"],
            "coverage_at_least_100pct": viirs_2024_clear_coverage["summary"]["clear_land_coverage_thresholds"]["1.0"],
            "report": VIIRS_2024_CLEAR_COVERAGE.with_suffix(".md").name,
            "interpretation": viirs_2024_clear_coverage["interpretation"],
            "separate_positive_snmf_event_cohort": viirs_2024_clear_coverage["positive_snmf_event_route_day_check"]["summary"],
            "positive_event_cohort_report": "fire-viirs-daily-l3-snmf-event-audit-2023-2025.md",
        },
        "global_fire_atlas_daily_ignition_route_crosscheck": {
            "route_event_records_within_10km": global_fire_atlas_route_ignitions["summary"]["route_event_records_within_10km"],
            "unique_route_fire_season_ids": global_fire_atlas_route_ignitions["summary"]["unique_route_fire_season_ids"],
            "unique_start_dates": global_fire_atlas_route_ignitions["summary"]["unique_start_dates_with_route_event"],
            "inpe_positive_detection_matches_within_2days_and_10km": global_fire_atlas_route_ignitions["summary"]["gfa_events_with_nearby_inpe_detection_within_2days"],
            "snmf_report_matches_within_2days_and_10km": global_fire_atlas_route_ignitions["summary"]["gfa_events_with_nearby_snmf_report_within_2days"],
            "report": GLOBAL_FIRE_ATLAS_ROUTE_IGNITIONS.with_suffix(".md").name,
            "interpretation": "GFA adds daily positive event candidates derived from burned-area progression. Its dates are inferred at daily resolution, it has no verified negative route-days, and it cannot validate hourly lead time or alert precision. INPE coincidences are positive-source corroboration and may share satellite platforms; SNMF corroborates only the small selected event subset.",
        },
        "idecor_ohmc_fwi_prospective_capture": {
            "route": idecor_fwi_prospective["route"]["name"],
            "retrieved_at_utc": idecor_fwi_prospective["source"]["retrieved_at_utc"],
            "forecast_valid_date": next(layer["valid_date"] for layer in idecor_fwi_prospective["layers"] if layer["kind"] == "next_day_forecast"),
            "forecast_fwi_values": [sample["values"]["fwi"] for layer in idecor_fwi_prospective["layers"] if layer["kind"] == "next_day_forecast" for sample in layer["samples"]],
            "samples": sum(len(layer["samples"]) for layer in idecor_fwi_prospective["layers"]),
            "report": "fire-idecor-fwi-prospective-capture-2026-10-23.md",
            "interpretation": "The official Córdoba map supplied one current-day and one next-day FWI layer at five route points. This starts prospective collection; it is one route-date, the points are spatially dependent, the map response has no WRF initialization timestamp, and FWI is fire-behaviour danger rather than calibrated ignition probability.",
        },
        "data_needed_to_resume_a_defensible_test": [
            "A complete timestamped incident/active-fire registry for the eight Argentina route corridors, with coordinates or perimeters, source observation time, confidence/quality, and explicit sensor-coverage gaps. The newer GFA screen adds 20 positive event-route records (16 with nearby INPE detections and 2 matched to the available SNMF event subset), but its inferred day-level starts do not provide observed ignition times or verified negatives.",
            "More independently adjudicated no-fire windows for those corridors. The 2024 VIIRS cohort now provides 122 route-days with at least 90% clear-land coverage across 14 report-date clusters for the sensor-detection target, but its 27 dates were selected from SNMF no-fire reports and do not establish physical fire absence.",
            "The daily 1-km VNP14A1/VJ114A1/VJ214A1 pilot now covers all 216 route-days on 27 selected 2024 dates; 122 have at least 90% clear-land coverage and 79 are fully clear by the sampled-grid criterion. This supports evaluation of the satellite-detection target, but the cohort has no positive fire detections and cannot establish physical no-fire labels. Extend it with independently timed positive events and broader prospective dates while retaining clouds, unprocessed classes, missing tiles and incomplete observations as unknown.",
            "Historical or prospectively archived weather forecasts with issue time and valid time, paired to independent fire observations. The first official OHMC/IDECOR FWI snapshot is only one route-date and does not expose the WRF initialization timestamp; continue daily captures and adjudicate event and observed no-fire outcomes.",
            "At least the required number of independent, adjudicated alert episodes for a chosen precision bound, plus a later untouched season for final evaluation.",
        ],
        "next_external_candidate": {
            "dataset": "NASA FIRMS standard-science active-fire archive (VIIRS S-NPP/NOAA-20/NOAA-21 and MODIS)",
            "official_archive_url": "https://firms.modaps.eosdis.nasa.gov/download/",
            "official_detection_limits_url": "https://firms.modaps.eosdis.nasa.gov/alerts/notes.php",
            "coverage_as_reported_by_NASA": {
                "MODIS_Terra": "2000-11 onward",
                "MODIS_Aqua": "2002-07 onward",
                "VIIRS_SNPP": "2012-01-20 onward",
                "VIIRS_NOAA20": "2018-04-01 onward",
                "VIIRS_NOAA21": "2023-03-01 onward",
            },
            "why_useful": "An independent active-fire sensor family could corroborate GOES alerts and add historical event detections.",
            "access": "A NASA FIRMS MAP_KEY and NASA_EARTHDATA_TOKEN are configured in the ignored local .env. The 61 exact-time NASA VNP03IMG/VJ103IMG/VJ203IMG granules were downloaded, hash-verified, and paired with VNP14IMG/VJ114IMG/VJ214IMG masks for the Barda corridor.",
            "data_limits": [
                "FIRMS is an active-fire detection archive, not a complete fire/no-fire panel.",
                "NASA notes that fires can be missed between satellite overpasses or under cloud, heavy smoke, or tree canopy; such absences cannot be labeled negative without valid observation/quality coverage.",
                "NRT data are replaced by standard detections after roughly 2-5 months; NASA recommends standard science-quality data for research.",
            ],
            "required_companion_data": "A per-pixel or per-route observation/quality mask for each overpass, plus independently archived forecast issue/valid times and official incident/perimeter records. A complete route-time cohort still requires valid fire-free periods or another independent source that can verify non-events.",
        },
        "source_files_sha256": {path.relative_to(ROOT).as_posix(): sha256(path) for path in source_paths},
        "synthetic_observations": 0,
        "deployment_approved": False,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": OUT.relative_to(ROOT).as_posix(),
        "candidate_event_coincidence": f"{active_alerted}/{active_covered}",
        "snmf_incidents_without_coverage": event_audit["snmf_incidents_without_test_day_pixel_coverage"],
        "sample_size_examples": sample_targets,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
