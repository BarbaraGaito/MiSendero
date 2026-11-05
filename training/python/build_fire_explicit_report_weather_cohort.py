"""Join official SNMF route-fire evidence and explicit no-fire reports to archived forecasts.

The output is a small, exploratory labeled cohort. It is deliberately not used
to fit a production model: events and negative-report dates are too sparse and
clustered for a reliable precision estimate.
"""
from __future__ import annotations

from collections import Counter
import math
import json

import pandas as pd

from environmental_sources import ROOT, sha256
from fire_sources import PRIVATE
from train_snmf_report_proxy_gfs_model import WEATHER_FILES, load_weather_with_geography

REPORT_DIR = ROOT / "docs/environmental-models-2026-10-22"
CATALOG = REPORT_DIR / "fire-unified-route-event-catalog.json"
NO_FIRE_AUDIT = REPORT_DIR / "fire-snmf-national-no-fire-report-audit.json"
OUT_DATA = PRIVATE / "fire-explicit-report-weather-cohort.csv.gz"
OUT_JSON = REPORT_DIR / "fire-explicit-report-weather-cohort-audit.json"
OUT_MD = REPORT_DIR / "fire-explicit-report-weather-cohort-audit.md"
FEATURES = ["temperature_mean", "temperature_max", "humidity_mean", "humidity_min",
            "wind_mean", "wind_max", "precipitation_sum"]


def all_correct_alerts_for_precision_lower_bound(target: float = 0.90, alpha: float = 0.05) -> int:
    """One-sided exact binomial lower bound when every observed alert is correct."""
    return math.ceil(math.log(alpha) / math.log(target))


def inputs_hashes() -> dict[str, str]:
    paths = [CATALOG, NO_FIRE_AUDIT, *WEATHER_FILES["jma_gsm"]]
    return {path.relative_to(ROOT).as_posix(): sha256(path) for path in paths}


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    no_fire_audit = json.loads(NO_FIRE_AUDIT.read_text(encoding="utf-8"))
    weather = load_weather_with_geography(WEATHER_FILES["jma_gsm"])
    weather = weather.rename(columns={"region": "route"})
    weather["date"] = weather["date"].astype(str)

    positives: dict[tuple[str, str], dict] = {}
    for event in catalog["events"]:
        for record in event["source_records"]:
            if record["source"] != "SNMF_daily_reports":
                continue
            key = (event["route"], record["start_date"])
            row = positives.setdefault(key, {"label": 1, "label_source": "SNMF_reported_incident_start",
                "evidence_ids": [], "source_record_count": 0})
            row["evidence_ids"].append(event["event_id"])
            row["source_record_count"] += record["source_record_count"]

    negatives: dict[tuple[str, str], dict] = {}
    for row in no_fire_audit["verified_negative_route_day_labels"]:
        key = (row["route_sector"], row["report_date"])
        negatives[key] = {"label": 0, "label_source": "SNMF_explicit_national_no_fire_report",
                          "evidence_ids": [row["evidence_pdf_sha256"]], "source_record_count": 1}

    overlap = set(positives) & set(negatives)
    if overlap:
        raise ValueError(f"Positive and explicit-negative labels overlap: {sorted(overlap)[:5]}")

    # A second count shows the effect of taking the union of every positive
    # source. It is not the primary training target because the sources observe
    # different phenomena and have different temporal resolution.
    union_positive: dict[tuple[str, str], set[str]] = {}
    for event in catalog["events"]:
        key = (event["route"], event["start_date"])
        union_positive.setdefault(key, set()).update(
            record["source"] for record in event["source_records"])
    union_conflicts = set(union_positive) & set(negatives)
    weather_keys = set(zip(weather["route"], weather["date"]))
    union_aligned = {key for key in union_positive if key in weather_keys}
    union_by_year = {}
    for year in sorted({day[:4] for _, day in union_aligned}):
        selected = [key for key in union_aligned if key[1].startswith(year)]
        union_by_year[year] = {"positive_route_dates": len(selected),
                               "positive_incident_dates": len({day for _, day in selected})}
    union_test = {key for key in union_aligned if key[1].startswith("2025")}
    union_source_counts = Counter(source for key in union_aligned for source in union_positive[key])

    label_rows = []
    for (route, day), label in positives.items():
        label_rows.append({"route": route, "date": day, **label})
    for (route, day), label in negatives.items():
        label_rows.append({"route": route, "date": day, **label})
    labels = pd.DataFrame(label_rows)
    if labels.duplicated(["route", "date"]).any():
        raise ValueError("Duplicate route-date target after source normalization")

    frame = labels.merge(weather, on=["route", "date"], how="left", validate="one_to_one", indicator=True)
    missing_forecast = frame["_merge"] != "both"
    aligned = frame.loc[~missing_forecast].drop(columns="_merge").copy()
    if aligned[FEATURES].isna().any().any():
        raise ValueError("Matched forecast row contains missing daily feature values")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    aligned.to_csv(OUT_DATA, index=False, compression={"method": "gzip", "mtime": 0})

    by_year = {}
    for year, group in aligned.groupby(aligned["date"].str[:4], sort=True):
        pos = group[group["label"] == 1]
        neg = group[group["label"] == 0]
        by_year[str(year)] = {
            "aligned_route_dates": int(len(group)),
            "positive_route_dates": int(len(pos)),
            "negative_route_dates": int(len(neg)),
            "positive_incident_dates": int(pos["date"].nunique()),
            "negative_report_dates": int(neg["date"].nunique()),
            "negative_report_date_groups": int(neg["date"].nunique()),
        }
    positives_aligned = aligned[aligned["label"] == 1]
    negatives_aligned = aligned[aligned["label"] == 0]
    independent_test_2025 = aligned[aligned["date"].str.startswith("2025")]
    result = {
        "experiment_id": "snmf-explicit-report-fire-weather-cohort-v1",
        "status": "joined_but_insufficient_for_reliable_precision_claim",
        "target": "SNMF-reported incident start within 10 km of route versus an explicit national no-fire SNMF report date; this is a report-evidence target, not universal physical fire/no-fire truth.",
        "feature_source": "Open-Meteo previous-run JMA GSM forecast features for the full target UTC date, archived in advance; 24 valid hourly forecast values are aggregated to daily features.",
        "features": FEATURES,
        "data": {
            "source_positive_route_dates": len(positives),
            "source_negative_route_dates": len(negatives),
            "label_overlap_route_dates": len(overlap),
            "forecast_rows_available": int(len(weather)),
            "labels_without_complete_archived_forecast": int(missing_forecast.sum()),
            "aligned_route_dates": int(len(aligned)),
            "aligned_positive_route_dates": int(len(positives_aligned)),
            "aligned_positive_incident_dates": int(positives_aligned["date"].nunique()),
            "aligned_negative_route_dates": int(len(negatives_aligned)),
            "aligned_negative_report_dates": int(negatives_aligned["date"].nunique()),
            "temporal_holdout_2025_route_dates": int(len(independent_test_2025)),
            "temporal_holdout_2025_positive_route_dates": int(independent_test_2025["label"].sum()),
            "temporal_holdout_2025_negative_route_dates": int((independent_test_2025["label"] == 0).sum()),
            "temporal_holdout_2025_negative_report_dates": int(independent_test_2025.loc[independent_test_2025["label"] == 0, "date"].nunique()),
            "years": by_year,
        },
        "all_positive_sources_union_diagnostic": {
            "positive_route_dates_aligned": len(union_aligned),
            "positive_dates_aligned": len({day for _, day in union_aligned}),
            "route_date_conflicts_with_explicit_no_fire_reports": len(union_conflicts),
            "source_record_presence_counts_not_additive": dict(sorted(union_source_counts.items())),
            "temporal_holdout_2025_positive_route_dates": len(union_test),
            "temporal_holdout_2025_positive_dates": len({day for _, day in union_test}),
            "by_year": union_by_year,
            "training_use": "diagnostic only; source targets are heterogeneous and a union can change the outcome definition",
        },
        "forecast_archive_files": [path.relative_to(ROOT).as_posix() for path in WEATHER_FILES["jma_gsm"]],
        "feature_issue_valid_alignment": "previous_day1 forecasts are matched by their valid UTC date to the reported incident start or negative bulletin date. The feature set uses no observed weather after issue time.",
        "precision_evidence_gate": {
            "measure": "event-level precision on an untouched temporal test set",
            "one_sided_confidence": 0.95,
            "target_lower_bound": 0.90,
            "minimum_independent_alert_events_if_all_are_correct": all_correct_alerts_for_precision_lower_bound(),
            "method": "Exact binomial lower bound; for zero false alerts, lower bound = 0.05^(1/n). Any false alert increases the sample size needed.",
            "independence_unit": "fire episode, with alerts and repeated route-days for the same episode grouped together",
        },
        "source_sha256": inputs_hashes(),
        "dataset_path": OUT_DATA.relative_to(ROOT).as_posix(),
        "dataset_sha256": sha256(OUT_DATA),
        "negative_label_audit": NO_FIRE_AUDIT.relative_to(ROOT).as_posix(),
        "limitations": [
            "The 2025 negative holdout contains only one distinct official no-fire report date, so eight route rows do not provide eight independent negative dates.",
            "The 2026 source cohort has positive events but no explicit no-fire report days in the current audit.",
            "The cohort is small and clustered by dates; model fitting or hyperparameter tuning would overfit and cannot establish reliable precision.",
            "An explicit SNMF no-fire report is a negative for the defined report target only; it does not establish absence of every physical or undetected fire.",
            "No synthetic observations, oversampling, or imputed weather values are used.",
        ],
        "synthetic_observations": 0,
        "model_fitted": False,
        "deployment_approved": False,
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    OUT_MD.write_text(
        "# Cohorte SNMF explícita unida con pronósticos históricos\n\n"
        "Se unieron únicamente etiquetas de incidentes SNMF dentro de 10 km de senderos y fechas cuyo parte nacional dice explícitamente que no hubo incendios reportados. Para cada fecha se asociaron variables JMA GSM archivadas con vigencia UTC ese día y emitidas en la corrida previa. No se mezclaron positivos satelitales de otros productos con la etiqueta de partes oficiales.\n\n"
        f"El cruce produjo **{len(aligned)} pares sendero-fecha**: {len(positives_aligned)} positivos de {positives_aligned['date'].nunique()} fechas de incidente y {len(negatives_aligned)} negativos de {negatives_aligned['date'].nunique()} fechas de parte. En el test temporal 2025 hay **{int(independent_test_2025['label'].sum())} positivos y {int((independent_test_2025['label'] == 0).sum())} negativos**, pero esos negativos pertenecen a solo **{int(independent_test_2025.loc[independent_test_2025['label'] == 0, 'date'].nunique())} fecha**.\n\n"
        f"Como referencia de tamaño muestral, hacen falta al menos **{all_correct_alerts_for_precision_lower_bound()} episodios de alerta independientes y todos correctos** para que el límite inferior unilateral exacto al 95 % supere el 90 %; con falsas alarmas se necesitan más. El test disponible no alcanza esa escala.\n\n"
        f"Si se toma como positivo cualquier señal de las tres fuentes unificadas, aparecen {len(union_aligned)} fechas-sendero positivas alineadas ({len(union_test)} en 2025), pero cambia el significado del objetivo y se mantienen solo ocho negativos de una fecha en el test. Esa unión sirve para estudiar concordancia de fuentes, no para atribuir una única precisión de predicción.\n\n"
        "Por esa concentración no entrené ni ajusté hiperparámetros: una precisión calculada aquí sería inestable. El CSV comprimido conserva ruta, fecha, clase, procedencia y siete variables meteorológicas; el JSON registra hashes y conteos.\n\n"
        "**Resultado:** se confirmó que el empalme de fuentes y pronósticos funciona, pero la cohorte aún no permite afirmar una precisión fiable. Se requieren más fechas negativas explícitas y más eventos independientes en el período posterior reservado.\n",
        encoding="utf-8")
    print(json.dumps({"audit": str(OUT_JSON.relative_to(ROOT)), "dataset": str(OUT_DATA.relative_to(ROOT)),
                      "aligned": len(aligned), "by_year": by_year,
                      "test_2025": result["data"]["temporal_holdout_2025_route_dates"],
                      "test_2025_positive": result["data"]["temporal_holdout_2025_positive_route_dates"],
                      "test_2025_negative": result["data"]["temporal_holdout_2025_negative_route_dates"],
                      "test_2025_negative_dates": result["data"]["temporal_holdout_2025_negative_report_dates"],
                      "minimum_all_correct_independent_alert_events_for_precision_gate": result["precision_evidence_gate"]["minimum_independent_alert_events_if_all_are_correct"],
                      "model_fitted": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
