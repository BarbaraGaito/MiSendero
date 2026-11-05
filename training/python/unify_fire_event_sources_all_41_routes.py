"""Build a source-preserving fire-event catalog for all archived Argentina trails.

Inputs are the original SNMF reports, Global Fire Atlas shapefiles and INPE
Aqua/MODIS reference detections. Route association is within 10 km. This is an
evidence catalog, not a complete physical-fire census or a model-ready panel.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import audit_global_fire_atlas_route_ignitions as gfa
import evaluate_modis_inpe_union_weather as union
import unify_fire_event_sources as base
from environmental_sources import ROOT, sha256

REPORT_DIR = ROOT / "docs/environmental-models-2026-10-22"
PRIVATE = ROOT / "training/data/environmental/private"
SNMF_FILES = [REPORT_DIR / f"snmf-{year}-daily-occurrence-events.json"
              for year in (2022, 2023, 2024, 2025)] + [
                  REPORT_DIR / "snmf-2026-jan-daily-occurrence-events.json"]
SNMF_NO_FIRE = REPORT_DIR / "fire-snmf-national-no-fire-report-audit.json"
INPE_CACHE = PRIVATE / "inpe-41-trail-positive-days-2018-2025.json"
GFA_ARCHIVE = PRIVATE / "global-fire-atlas-2026-04/SHP_ignitions.zip"
GFA_MANIFEST = GFA_ARCHIVE.parent / "download-manifest.json"
OUT = REPORT_DIR / "fire-unified-all-41-route-event-catalog.json"
OUT_MD = REPORT_DIR / "fire-unified-all-41-route-event-catalog.md"
ROUTE_RADIUS_KM = 10.0
KM_PER_DEG = 111.32


def route_lines() -> tuple[dict[str, list[list[float]]], dict[str, str]]:
    lines, sources = {}, {}
    for path in union.ROUTE_FILES:
        for route_id, route in json.loads(path.read_text(encoding="utf-8")).items():
            points = route.get("points") or []
            if len(points) < 2:
                continue
            lines[route_id] = [[float(p[0]), float(p[1])] for p in points]
            sources[route_id] = route.get("source_url", "")
    return lines, sources


def point_line_distance_km(lat: float, lon: float, points: list[list[float]]) -> float:
    cosine = math.cos(math.radians(lat))
    best = math.inf
    for (lat1, lon1), (lat2, lon2) in zip(points, points[1:]):
        ax, ay = (lon1 - lon) * KM_PER_DEG * cosine, (lat1 - lat) * KM_PER_DEG
        bx, by = (lon2 - lon) * KM_PER_DEG * cosine, (lat2 - lat) * KM_PER_DEG
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        t = 0 if length2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length2))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def add_snmf_records(lines: dict[str, list[list[float]]]) -> tuple[list[dict], dict]:
    records_by_key = {}
    screened, coordinate_rows = 0, 0
    for path in SNMF_FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        for event in data["deduplicated_events"]:
            screened += 1
            lat, lon = event.get("latitude"), event.get("longitude")
            if lat is None or lon is None:
                continue
            coordinate_rows += 1
            try:
                day = date.fromisoformat(event["reported_start_date"]).isoformat()
                lat, lon = float(lat), float(lon)
            except (KeyError, TypeError, ValueError):
                continue
            for route, points in lines.items():
                distance = point_line_distance_km(lat, lon, points)
                if distance > ROUTE_RADIUS_KM:
                    continue
                identity = (route, event.get("province", "").casefold(), day,
                            round(lat, 4), round(lon, 4))
                digest = hashlib.sha256(repr(identity).encode()).hexdigest()[:16]
                record = records_by_key.setdefault(identity, {
                    "record_id": f"SNMF:{digest}", "source": "SNMF_daily_reports",
                    "source_family": "OFFICIAL_INCIDENT_REPORT", "route": route,
                    "start_date": day, "end_date": day, "latitude": lat, "longitude": lon,
                    "route_distance_km": round(distance, 3), "source_record_count": 0,
                    "source_record_ids": [], "incident_names": [], "report_dates": [],
                    "province": event.get("province"), "status": event.get("status"),
                    "evidence_type": "officially_reported_fire_incident",
                    "time_precision": "reported_start_date_only"})
                record["source_record_count"] += 1
                record["source_record_ids"].append(
                    f"{path.name}:{event.get('report_date', '')}:{event.get('source_page', '')}")
                name = event.get("incident_name")
                if name and name not in record["incident_names"]:
                    record["incident_names"].append(name)
                report_day = event.get("report_date")
                if report_day and report_day not in record["report_dates"]:
                    record["report_dates"].append(report_day)
    return list(records_by_key.values()), {"deduplicated_national_rows_screened": screened,
        "rows_with_coordinates": coordinate_rows, "route_incident_records": len(records_by_key)}


def add_inpe_records(lines: dict[str, list[list[float]]]) -> tuple[list[dict], dict]:
    if not INPE_CACHE.is_file():
        raise FileNotFoundError(f"Run source acquisition first; missing {INPE_CACHE}")
    cache = json.loads(INPE_CACHE.read_text(encoding="utf-8"))
    source_hashes = {str(year): sha256(union.INPE_DIR / f"focos_ams_ref_{year}.zip")
                     for year in range(2018, 2026)}
    expected = {year: item["sha256"] for year, item in cache["summary"]["annual_archives"].items()}
    if source_hashes != expected:
        raise ValueError("INPE yearly archive hash mismatch against route-day cache")
    detections = []
    for row in cache["route_days"]:
        route = row["route"]
        if route not in lines:
            continue
        for index, coordinate in enumerate(row["coordinates"]):
            lat, lon = coordinate
            distance = point_line_distance_km(lat, lon, lines[route])
            if distance <= ROUTE_RADIUS_KM:
                detections.append({"route_sector": route, "date": row["date"],
                    "latitude": lat, "longitude": lon, "distance_km": distance,
                    "detection_id": f"{row['date']}:{lat:.4f}:{lon:.4f}:{index}"})
    records = base.cluster_inpe(detections)
    return records, {"route_day_cache_sha256": sha256(INPE_CACHE),
        "annual_archive_sha256": source_hashes,
        "route_day_detections": len(detections),
        "clustered_route_events": len(records)}


def add_gfa_records(lines: dict[str, list[list[float]]]) -> tuple[list[dict], dict]:
    source_manifest = json.loads(GFA_MANIFEST.read_text(encoding="utf-8"))
    if source_manifest.get("sha256") != sha256(GFA_ARCHIVE):
        raise ValueError("Global Fire Atlas archive hash mismatch")
    route_geometry = [{"name": route, "route_coordinates": points}
                      for route, points in lines.items()]
    prepared = gfa.route_bounds(route_geometry)
    records, counts = [], {}
    with __import__("zipfile").ZipFile(GFA_ARCHIVE) as archive:
        for year in gfa.YEARS:
            prefix = f"GFA_v20260408_ignitions_{year}"
            if prefix + ".dbf" not in archive.namelist() or prefix + ".shp" not in archive.namelist():
                counts[str(year)] = 0
                continue
            count, hits = gfa.read_year(archive, year, prepared)
            counts[str(year)] = count
            for hit in hits:
                records.append({"record_id": f"GFA:{hit['fire_id']}:{hit['route']}",
                    "source": "Global_Fire_Atlas",
                    "source_family": "MODIS_DERIVED_FIRE_ATLAS",
                    "route": hit["route"], "start_date": hit["start_date"],
                    "end_date": hit["end_date"] or hit["start_date"],
                    "latitude": hit["latitude"], "longitude": hit["longitude"],
                    "route_distance_km": hit["distance_to_full_route_km"],
                    "source_record_count": 1, "source_record_ids": [hit["fire_id"]],
                    "size_ha": hit.get("size_ha"), "duration_days": hit.get("duration_days"),
                    "evidence_type": "atlas_ignition_point_and_fire_season",
                    "time_precision": "daily_inferred_start_date"})
    return records, {"archive_sha256": sha256(GFA_ARCHIVE),
        "source_rows_by_year": counts, "route_event_records": len(records)}


def main() -> None:
    lines, route_sources = route_lines()
    weather = union.load_weather()
    weather_routes = {route for route, _ in weather}
    if set(lines) != weather_routes:
        raise ValueError(f"Route geometry/weather mismatch: geometry={len(lines)}, weather={len(weather_routes)}")
    snmf, snmf_summary = add_snmf_records(lines)
    inpe, inpe_summary = add_inpe_records(lines)
    gfa_records, gfa_summary = add_gfa_records(lines)
    records = snmf + inpe + gfa_records
    events, possible = base.link_records(records)
    no_fire = json.loads(SNMF_NO_FIRE.read_text(encoding="utf-8"))
    counts = Counter(record["source_family"] for record in records)
    evidence_counts = Counter(event["evidence_class"] for event in events)
    input_paths = [*union.ROUTE_FILES, *SNMF_FILES, SNMF_NO_FIRE, INPE_CACHE,
        GFA_ARCHIVE, GFA_MANIFEST, *union.WEATHER_ARCHIVES, *union.WEATHER_MANIFESTS]
    result = {"schema_version": 1,
        "experiment_id": "argentina-all-41-trails-unified-fire-event-evidence",
        "scope": {"routes": len(lines), "route_ids": sorted(lines),
            "route_geometry_source": [path.relative_to(ROOT).as_posix() for path in union.ROUTE_FILES],
            "route_buffer_km": ROUTE_RADIUS_KM,
            "temporal_scope": "INPE 2018-2025; SNMF 2022-2026-01; GFA 2022-2026",
            "source_link_rule": f"Unique reciprocal nearest cross-source links on same route, within 2 days and 3 km; possible links retained separately."},
        "source_record_counts": dict(counts),
        "source_acquisition": {"snmf": snmf_summary, "inpe": inpe_summary, "gfa": gfa_summary},
        "unified_event_count": len(events),
        "events_by_evidence_class": dict(sorted(evidence_counts.items())),
        "auto_merged_event_groups": sum(len(event["source_records"]) > 1 for event in events),
        "possible_links_not_merged": possible,
        "events": events,
        "negative_evidence": {"national_explicit_no_fire_report_dates":
            len(no_fire["verified_explicit_no_fire_reports"]),
            "route_day_labels_in_original_audit": len(no_fire["verified_negative_route_day_labels"]),
            "meaning": "Explicit national no-fire reports are retained as administrative evidence only; operational dataset negatives require clear MODIS QA."},
        "source_files_sha256": {path.relative_to(ROOT).as_posix(): sha256(path) for path in input_paths},
        "route_geometry_source_urls": route_sources,
        "synthetic_observations": 0, "training_ready": False,
        "limitations": ["Satellite products in the Global Fire Atlas and INPE AMS detections derive from the MODIS family; not independent corroboration.",
            "A route buffer of 10 km associates an incident with a route but does not mean it affected or threatened the trail.",
            "SNMF start dates are day-level reports; GFA dates are inferred starts; INPE dates are hotspot acquisition dates.",
            "Potential source links are not automatically merged unless the conservative reciprocal-nearest rule passes.",
            "A lack of source record is unknown, not a negative. Fire-free observed route-days are separately defined with MODIS clear QA in the joined dataset."],
        "deployment_approved": False}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    by_route = Counter(event["route"] for event in events)
    lines_md = ["# Catálogo unificado de eventos de fuego en las 41 rutas argentinas", "",
        "Catálogo con procedencia de partes SNMF, focos INPE Aqua/MODIS y Global Fire Atlas. Las rutas se asociaron usando la polilínea completa y un radio de 10 km; no es un censo de incendios ni una tabla de negativos.", "",
        f"Se procesaron {len(lines)} rutas. El catálogo contiene {len(events)} grupos de evidencia de {len(records)} registros fuente; {result['auto_merged_event_groups']} grupos reúnen más de un registro y {len(possible)} pares posibles permanecen sin fusionar.", "",
        f"Conteos fuente: {json.dumps(dict(counts), ensure_ascii=False)}. Posibles clases: {json.dumps(dict(evidence_counts), ensure_ascii=False)}.", "",
        "INPE AMS y GFA comparten la familia MODIS. Los negativos de entrenamiento no se infieren del silencio de estas fuentes; en el dataset unido solo se consideran no-detecciones con QA MODIS despejado.", "",
        "## Eventos por ruta", ""]
    lines_md.extend(f"- {route}: {count}" for route, count in sorted(by_route.items()))
    lines_md += ["", "El JSON conserva identificadores, fechas, coordenadas, distancias, enlaces posibles y SHA-256 de cada insumo. Este catálogo no es, por sí solo, un dataset listo para inferencia.", ""]
    OUT_MD.write_text("\n".join(lines_md), encoding="utf-8")
    print(json.dumps({"report": OUT.relative_to(ROOT).as_posix(),
        "route_count": len(lines), "record_counts": dict(counts),
        "event_count": len(events), "events_by_evidence_class": dict(evidence_counts),
        "routes_with_events": len(by_route), "possible_links": len(possible)},
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
