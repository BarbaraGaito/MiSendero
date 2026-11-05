#!/usr/bin/env python3
"""Select official SNMF fire events near the eight route geometries for a VIIRS L3 pilot.

The output is an event acquisition cohort only. It does not create negative
labels, download imagery, or estimate model performance.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "docs/environmental-models-2026-10-22"
GEOMETRY = ROOT / "training/data/environmental/private/fire-route-geometries.json"
ROUTE_TILES = BASE / "fire-viirs-daily-l3-candidate-audit-2026-10-23.json"
EFIRE_2025 = BASE / "fire-viirs-snmf-event-route-pass-audit-2025.json"
YEARS = ("2023", "2024", "2025")
ROUTE_BUFFER_KM = 10.0
DEDUP_DISTANCE_KM = 1.0
EARTH_RADIUS_KM = 6371.0088
OUT = BASE / "fire-viirs-daily-l3-event-cohort-2023-2025.json"
OUT_MD = BASE / "fire-viirs-daily-l3-event-cohort-2023-2025.md"
ACQUISITION_MANIFEST = ROOT / "training/data/environmental/private/viirs-daily-l3-snmf-route-events-2023-2025/acquisition-manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def point_distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    term = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(term))


def point_to_route_km(point: tuple[float, float], coordinates: list[list[float]]) -> float:
    """Approximate distance to a polyline in a local metric projection (lat, lon input)."""
    lat0, lon0 = point
    cosine = math.cos(math.radians(lat0))

    def xy(lat: float, lon: float) -> tuple[float, float]:
        return (EARTH_RADIUS_KM * math.radians(lon - lon0) * cosine,
                EARTH_RADIUS_KM * math.radians(lat - lat0))

    px, py = 0.0, 0.0
    best = math.inf
    points = [xy(float(lat), float(lon)) for lat, lon in coordinates]
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        t = 0.0 if length_sq == 0 else max(0.0, min(1.0, -((ax - px) * dx + (ay - py) * dy) / length_sq))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    if len(points) == 1:
        best = math.hypot(points[0][0], points[0][1])
    return best


def normalized_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def match_existing_efire(events: list[dict]) -> dict:
    """Cross-reference 2025 selected events with already-audited exact-date E-FIRE pixels."""
    source = json.loads(EFIRE_2025.read_text(encoding="utf-8"))
    observations = source["snmf_event_coordinate_cross_check"]["observations"]
    checked = []
    for event in events:
        if not event["reported_start_date"].startswith("2025-"):
            continue
        matches = []
        point = (event["latitude"], event["longitude"])
        for observation in observations:
            if observation["reported_start_date"] != event["reported_start_date"] or observation["route_sector"] != event["route"]:
                continue
            distance = point_distance_km(point, (observation["event_latitude"], observation["event_longitude"]))
            if distance <= 1.0:
                matches.append({
                    "mask_status": observation["mask_status"],
                    "mask_label": observation["mask_label"],
                    "distance_between_report_coordinates_km": round(distance, 4),
                    "nearest_pixel_distance_km": observation["nearest_pixel_distance_km"],
                })
        statuses = sorted({item["mask_status"] for item in matches})
        if "observed_fire_detection" in statuses:
            status = "observed_fire_detection"
        elif "observed_clear_land" in statuses and "unknown_quality_or_nonland" in statuses:
            status = "mixed_clear_and_unknown"
        elif "observed_clear_land" in statuses:
            status = "clear_land_without_detection_at_overpass"
        elif matches:
            status = "unknown_quality_or_nonland"
        else:
            status = "no_matched_overpass_in_downloaded_cohort"
        checked.append({
            "reported_start_date": event["reported_start_date"],
            "route": event["route"],
            "incident_name": event["incident_name"],
            "distance_to_route_km": event["distance_to_route_km"],
            "status": status,
            "same_day_observations": matches,
        })
    counts = Counter(row["status"] for row in checked)
    return {
        "source_report": EFIRE_2025.relative_to(ROOT).as_posix(),
        "source_sha256": sha256(EFIRE_2025),
        "selected_2025_events": len(checked),
        "status_counts": dict(sorted(counts.items())),
        "events": checked,
        "interpretation": "Exact-date I-band overpasses at the reported point do not establish whether a fire was active before or after the pass. Cloud/quality, no matching pass, and clear-land without detection are separate observation states, not fire/no-fire ground truth.",
    }


def main() -> int:
    geometry_path = json.loads(GEOMETRY.read_text(encoding="utf-8"))
    routes = geometry_path["fire_route_geometries"]
    tile_audit = json.loads(ROUTE_TILES.read_text(encoding="utf-8"))
    tiles_by_route = {row["route"]: row["tiles"] for row in tile_audit["spatial_sampling"]["routes"]}
    candidates: list[dict] = []
    event_hashes = {}
    for year in YEARS:
        event_file = BASE / f"snmf-{year}-daily-occurrence-events.json"
        event_hashes[year] = sha256(event_file)
        payload = json.loads(event_file.read_text(encoding="utf-8"))
        for event in payload["deduplicated_events"]:
            lat, lon = event.get("latitude"), event.get("longitude")
            event_date = event.get("reported_start_date")
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not event_date:
                continue
            for route in routes:
                distance = point_to_route_km((float(lat), float(lon)), route["route_coordinates"])
                if distance <= ROUTE_BUFFER_KM:
                    candidates.append({
                        "reported_start_date": event_date,
                        "report_date": event.get("report_date"),
                        "route": route["name"],
                        "route_geometry_sha256": route["geometry_sha256"],
                        "distance_to_route_km": round(distance, 3),
                        "incident_name": event.get("incident_name"),
                        "province": event.get("province"),
                        "status_in_source_snapshot": event.get("status"),
                        "latitude": float(lat),
                        "longitude": float(lon),
                        "_event_key": (event_date, route["name"], normalized_name(event.get("incident_name"))),
                    })

    # Collapse repeated SNMF names for one start date and route. Preserve distinct
    # nearby incident points by clustering only when their reported coordinates
    # are within one kilometre.
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in candidates:
        groups.setdefault((row["reported_start_date"], row["route"]), []).append(row)
    selected: list[dict] = []
    duplicate_rows_collapsed = 0
    for group_rows in groups.values():
        clusters: list[list[dict]] = []
        for row in sorted(group_rows, key=lambda item: item["distance_to_route_km"]):
            match = next((cluster for cluster in clusters if any(
                point_distance_km((row["latitude"], row["longitude"]), (other["latitude"], other["longitude"])) <= DEDUP_DISTANCE_KM
                for other in cluster)), None)
            if match is None:
                clusters.append([row])
            else:
                match.append(row)
        for cluster in clusters:
            chosen = min(cluster, key=lambda item: item["distance_to_route_km"])
            names = sorted({name for name in (x["incident_name"] for x in cluster) if name})
            output = {k: v for k, v in chosen.items() if not k.startswith("_")}
            output["source_name_variants_collapsed"] = names
            output["source_records_collapsed"] = len(cluster)
            selected.append(output)
            duplicate_rows_collapsed += len(cluster) - 1

    selected.sort(key=lambda item: (item["reported_start_date"], item["route"], item["distance_to_route_km"]))
    tile_dates = sorted({(row["reported_start_date"], tile)
                         for row in selected for tile in tiles_by_route[row["route"]]})
    efire_check = match_existing_efire(selected)
    downloaded_granules = 0
    if ACQUISITION_MANIFEST.is_file():
        acquisition = json.loads(ACQUISITION_MANIFEST.read_text(encoding="utf-8"))
        downloaded_granules = sum(
            row.get("status") in {"downloaded", "present"}
            for row in acquisition.get("granules", [])
        )
    planned_granules = len(tile_dates) * 3
    report = {
        "experiment_id": "viirs-daily-l3-snmf-route-event-cohort-2023-2025",
        "status": "official_positive_event_cohort_granules_acquired_for_mask_audit"
        if downloaded_granules == planned_granules else "official_positive_event_cohort_ready_for_bounded_download",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "purpose": "Select historical daily VIIRS L3 tiles around official SNMF event coordinates near mapped Argentine trekking routes.",
        "selection": {
            "route_buffer_km": ROUTE_BUFFER_KM,
            "route_distance_method": "local equirectangular point-to-segment distance over the full route polyline",
            "years": list(YEARS),
            "same_start_date_route_deduplication_km": DEDUP_DISTANCE_KM,
            "candidate_event_records_within_buffer": len(candidates),
            "source_name_duplicate_records_collapsed": duplicate_rows_collapsed,
            "selected_route_event_clusters": len(selected),
            "by_year": dict(sorted(Counter(row["reported_start_date"][:4] for row in selected).items())),
            "by_route": dict(sorted(Counter(row["route"] for row in selected).items())),
        },
        "sources": {
            "route_geometry_path": GEOMETRY.relative_to(ROOT).as_posix(),
            "route_geometry_sha256": sha256(GEOMETRY),
            "daily_route_tile_audit_sha256": sha256(ROUTE_TILES),
            "snmf_event_report_sha256_by_year": event_hashes,
            "existing_efire_2025_sha256": efire_check["source_sha256"],
        },
        "cohort": selected,
        "existing_375m_same_day_event_coordinate_check": efire_check,
        "interpretation": [
            "These are official-report positive event candidates by reported coordinates and start dates; event times are only daily precision.",
            "A route-buffer match does not prove the incident affected the trail or was detected by satellite.",
            "The cohort contains positive events only; precision, specificity, false-alarm rate, and overall accuracy are not estimable from it.",
            "No negative labels or synthetic observations are created. A VIIRS class-5 pixel can only mean observed clear-land non-detection in that composite.",
            "Use later years as a temporal holdout after freezing any model or thresholds; do not randomly split adjacent days from one incident.",
        ],
        "acquisition_plan": {
            "daily_products": ["VNP14A1.002", "VJ114A1.002", "VJ214A1.002"],
            "event_dates": sorted({row["reported_start_date"] for row in selected}),
            "event_route_tile_pairs": [{"date": date, "tile": tile} for date, tile in tile_dates],
            "unique_route_tile_date_pairs": len(tile_dates),
            "maximum_granules_before_deduplication": planned_granules,
            "downloaded_granules_in_acquisition_manifest": downloaded_granules,
            "downloaded_granules": downloaded_granules,
        },
        "synthetic_observations": 0,
        "deployment_approved": False,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        "# Cohorte de eventos SNMF para piloto VIIRS diario",
        "",
        "Esta auditoria selecciona eventos oficiales SNMF 2023–2025 con coordenadas a menos de 10 km de las ocho rutas argentinas mapeadas. Los compuestos diarios VIIRS de la cohorte fueron descargados y auditados; el cruce es de corroboración de positivos y no calcula métricas de precisión del modelo.",
        "",
        f"Se encontraron **{len(candidates)} registros fuente** dentro del buffer y se agruparon en **{len(selected)} eventos por ruta y fecha de inicio** ({duplicate_rows_collapsed} registros con nombres repetidos colapsados). El plan inicial tiene {len(report['acquisition_plan']['event_dates'])} fechas, {len(tile_dates)} combinaciones fecha-tile de las rutas involucradas y un máximo de {report['acquisition_plan']['maximum_granules_before_deduplication']} granulos para los tres productos diarios.",
        "",
        "| Fecha de inicio SNMF | Ruta | Incidente reportado | Provincia | Distancia a ruta | Estado en parte |",
        "|---|---|---|---|---:|---|",
    ]
    for row in selected:
        lines.append(f"| {row['reported_start_date']} | {row['route']} | {', '.join(row['source_name_variants_collapsed'])} | {row.get('province') or 'sin dato'} | {row['distance_to_route_km']:.1f} km | {row.get('status_in_source_snapshot') or 'sin dato'} |")
    lines += [
        "",
        "La fecha es la fecha de inicio informada por SNMF, no una hora de ignición comprobada. La proximidad de un punto del parte a una ruta tampoco confirma que el sendero estuviera afectado. Esta cohorte contiene positivos candidatos, sin negativos: no permite afirmar precisión, especificidad ni tasa de falsas alarmas.",
        "",
        f"Como control de factibilidad, se cruzaron los {efire_check['selected_2025_events']} eventos seleccionados de 2025 con la auditoria de pasadas VIIRS E-FIRE de 375 m ya disponible: {json.dumps(efire_check['status_counts'], ensure_ascii=False)}. Los pasos sobre nubes y la falta de pasada coincidente quedan como desconocidos; incluso una clase de tierra despejada sin deteccion solo describe el instante del paso y no fija si el incendio estaba activo en ese momento.",
        "",
        f"La adquisición usa como máximo {planned_granules} granulos de `VNP14A1.002`, `VJ114A1.002` y `VJ214A1.002`; el manifiesto privado registra {downloaded_granules} descargados/presentes. La auditoria separada comprueba sus bytes y SHA-256. Los compuestos clase 5 solo representan tierra despejada sin detección asignada en ese producto; no demuestran ausencia física de fuego.",
        "",
        f"Fuentes privadas locales (no incluidas en Git): geometría `{GEOMETRY.relative_to(ROOT).as_posix()}` y reportes SNMF 2023–2025. Hashes y cohorte reproducible en [{OUT.name}]({OUT.name}). Reproducción: [`audit_viirs_daily_l3_event_cohort.py`](../../training/python/audit_viirs_daily_l3_event_cohort.py).",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"output": OUT.relative_to(ROOT).as_posix(), "markdown": OUT_MD.relative_to(ROOT).as_posix(),
                      "candidate_records": len(candidates), "selected_events": len(selected),
                      "dates": len(report["acquisition_plan"]["event_dates"]),
                      "max_granules": report["acquisition_plan"]["maximum_granules_before_deduplication"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
