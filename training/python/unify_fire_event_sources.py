"""Build a conservative, source-preserving route fire-event catalog.

This creates a harmonized event-evidence catalog, not a model-ready
fire/no-fire panel. It links observations only when route, date, and location
agree; it never infers a negative from a missing detection.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
import math
from pathlib import Path

from environmental_sources import ROOT, sha256

REPORT_DIR = ROOT / "docs/environmental-models-2026-10-22"
DATA_DIR = ROOT / "training/data/environmental"
GEOMETRY = DATA_DIR / "private/fire-route-geometries.json"
SNMF_FILES = [REPORT_DIR / f"snmf-{year}-daily-occurrence-events.json"
              for year in (2022, 2023, 2024, 2025)] + [
                  REPORT_DIR / "snmf-2026-jan-daily-occurrence-events.json"]
INPE = REPORT_DIR / "fire-inpe-reference-detections-route-coverage-2018-2025.json"
GFA = REPORT_DIR / "fire-global-fire-atlas-route-ignitions-2022-2026.json"
NO_FIRE = REPORT_DIR / "fire-snmf-national-no-fire-report-audit.json"
OUT = REPORT_DIR / "fire-unified-route-event-catalog.json"
OUT_MD = REPORT_DIR / "fire-unified-route-event-catalog.md"
ROUTE_RADIUS_KM = 10.0
AUTO_LINK_RADIUS_KM = 3.0
POSSIBLE_LINK_RADIUS_KM = 10.0
DATE_TOLERANCE_DAYS = 2
KM_PER_DEGREE = 111.32


def point_distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def point_line_distance_km(point: tuple[float, float], coordinates: list[list[float]]) -> float:
    lat, lon = point
    cosine = math.cos(math.radians(lat))
    best = math.inf
    for (lat1, lon1), (lat2, lon2) in zip(coordinates, coordinates[1:]):
        ax, ay = (lon1 - lon) * KM_PER_DEGREE * cosine, (lat1 - lat) * KM_PER_DEGREE
        bx, by = (lon2 - lon) * KM_PER_DEGREE * cosine, (lat2 - lat) * KM_PER_DEGREE
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        t = 0 if length_sq == 0 else max(0, min(1, -(ax * dx + ay * dy) / length_sq))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def cluster_inpe(points: list[dict]) -> list[dict]:
    """Collapse near-duplicate Aqua/MODIS points into route/day fire clusters."""
    by_route: dict[str, list[dict]] = defaultdict(list)
    for point in points:
        if float(point["distance_km"]) <= ROUTE_RADIUS_KM:
            by_route[point["route_sector"]].append(point)
    clusters = []
    for route, rows in sorted(by_route.items()):
        rows.sort(key=lambda row: (row["date"], row["latitude"], row["longitude"], row["detection_id"]))
        parent = list(range(len(rows)))

        def find(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(first, second):
            a, b = find(first), find(second)
            if a != b:
                parent[b] = a

        for index, row in enumerate(rows):
            day = date.fromisoformat(row["date"])
            for previous in range(index - 1, -1, -1):
                other = rows[previous]
                day_gap = (day - date.fromisoformat(other["date"])).days
                if day_gap > DATE_TOLERANCE_DAYS:
                    break
                if point_distance_km((row["latitude"], row["longitude"]),
                                     (other["latitude"], other["longitude"])) <= AUTO_LINK_RADIUS_KM:
                    union(index, previous)
        groups: dict[int, list[dict]] = defaultdict(list)
        for index, row in enumerate(rows):
            groups[find(index)].append(row)
        for group in groups.values():
            lat = sum(float(row["latitude"]) for row in group) / len(group)
            lon = sum(float(row["longitude"]) for row in group) / len(group)
            clusters.append({
                "record_id": "INPE:" + hashlib.sha256("|".join(sorted(r["detection_id"] for r in group)).encode()).hexdigest()[:16],
                "source": "INPE_AMS_AQUA_MODIS",
                "source_family": "AQUA_MODIS_ACTIVE_FIRE",
                "route": route,
                "start_date": min(r["date"] for r in group),
                "end_date": max(r["date"] for r in group),
                "latitude": round(lat, 6), "longitude": round(lon, 6),
                "route_distance_km": round(min(float(r["distance_km"]) for r in group), 3),
                "source_record_count": len(group),
                "source_record_ids": sorted(r["detection_id"] for r in group),
                "evidence_type": "active_fire_satellite_detections",
                "time_precision": "detection_timestamp_available_in_source_records",
            })
    return clusters


def build_source_records() -> tuple[list[dict], dict]:
    geometry_data = load_json(GEOMETRY)["fire_route_geometries"]
    routes = {item["name"]: item["route_coordinates"] for item in geometry_data}
    records = []
    snmf_records: dict[tuple, dict] = {}
    snmf_record_count = 0
    snmf_near_route_count = 0
    for path in SNMF_FILES:
        data = load_json(path)
        for event in data["deduplicated_events"]:
            snmf_record_count += 1
            if event.get("latitude") is None or event.get("longitude") is None:
                continue
            point = (float(event["latitude"]), float(event["longitude"]))
            try:
                start = date.fromisoformat(event["reported_start_date"])
            except (TypeError, ValueError):
                continue
            for route, coordinates in routes.items():
                distance = point_line_distance_km(point, coordinates)
                if distance > ROUTE_RADIUS_KM:
                    continue
                # The extractor can truncate one incident's name differently
                # across daily reports. Start date and exact reported point
                # provide a more stable key; keep every name/report as lineage.
                key = (route, event.get("province", "").casefold(), start.isoformat(),
                       round(point[0], 4), round(point[1], 4))
                identifier = hashlib.sha256(repr(key).encode()).hexdigest()[:16]
                record = snmf_records.setdefault(key, {
                    "record_id": f"SNMF:{identifier}",
                    "source": "SNMF_daily_reports",
                    "source_family": "OFFICIAL_INCIDENT_REPORT",
                    "route": route, "start_date": start.isoformat(),
                    "end_date": start.isoformat(), "latitude": point[0], "longitude": point[1],
                    "route_distance_km": round(distance, 3), "source_record_count": 0,
                    "source_record_ids": [], "incident_names": [], "report_dates": [],
                    "province": event.get("province"), "status": event.get("status"),
                    "evidence_type": "officially_reported_fire_incident",
                    "time_precision": "reported_start_date_only",
                })
                record["source_record_count"] += 1
                record["source_record_ids"].append(identifier + ":" + str(event.get("report_date", "")))
                if event.get("incident_name") and event["incident_name"] not in record["incident_names"]:
                    record["incident_names"].append(event["incident_name"])
                if event.get("report_date") and event["report_date"] not in record["report_dates"]:
                    record["report_dates"].append(event["report_date"])

    records.extend(snmf_records.values())
    snmf_near_route_count = len(snmf_records)

    gfa_data = load_json(GFA)
    for event in gfa_data["route_event_records"]:
        records.append({
            "record_id": f"GFA:{event['fire_id']}",
            "source": "Global_Fire_Atlas",
            "source_family": "MODIS_DERIVED_FIRE_ATLAS",
            "route": event["route"], "start_date": event["start_date"],
            "end_date": event["end_date"], "latitude": event["latitude"],
            "longitude": event["longitude"],
            "route_distance_km": event["distance_to_full_route_km"],
            "source_record_count": 1, "source_record_ids": [event["fire_id"]],
            "size_ha": event.get("size_ha"), "duration_days": event.get("duration_days"),
            "evidence_type": "atlas_ignition_point_and_fire_season",
            "time_precision": "daily_inferred_start_date",
        })

    inpe_data = load_json(INPE)
    inpe_records = cluster_inpe(inpe_data["nearby_detections"])
    records.extend(inpe_records)
    stats = {
        "snmf_national_deduplicated_event_rows_screened": snmf_record_count,
        "snmf_route_event_records_within_10km": sum(r["source"] == "SNMF_daily_reports" for r in records),
        "gfa_route_event_records_within_10km": len(gfa_data["route_event_records"]),
        "inpe_route_points_within_10km": sum(float(row["distance_km"]) <= ROUTE_RADIUS_KM for row in inpe_data["nearby_detections"]),
        "inpe_route_clusters_within_10km": len(inpe_records),
        "snmf_route_keys_deduplicated": len(snmf_records),
        "snmf_route_events_with_valid_coordinates": snmf_near_route_count,
    }
    return records, stats


def link_records(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Merge only unique, close cross-source pairs; expose looser matches separately."""
    pairs, possible = [], []
    by_route: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        by_route[record["route"]].append(index)
    for indices in by_route.values():
        ordered = sorted(indices, key=lambda i: records[i]["start_date"])
        for pos, first in enumerate(ordered):
            a = records[first]
            for second in ordered[pos + 1:]:
                b = records[second]
                gap = (date.fromisoformat(b["start_date"]) - date.fromisoformat(a["start_date"])).days
                if gap > DATE_TOLERANCE_DAYS:
                    break
                if a["source_family"] == b["source_family"]:
                    continue
                distance = point_distance_km((a["latitude"], a["longitude"]),
                                             (b["latitude"], b["longitude"]))
                if distance <= POSSIBLE_LINK_RADIUS_KM:
                    pair = {"record_ids": sorted([a["record_id"], b["record_id"]]),
                            "route": a["route"], "date_gap_days": gap,
                            "distance_km": round(distance, 3)}
                    possible.append(pair)
                    if distance <= AUTO_LINK_RADIUS_KM:
                        pairs.append((first, second, pair))

    # Auto-link only reciprocal unique nearest matches within each source pair.
    nearest: dict[tuple[int, str], tuple[int, float]] = {}
    ties: set[tuple[int, str]] = set()
    for first, second, pair in pairs:
        distance = pair["distance_km"]
        for index, other in ((first, second), (second, first)):
            key = (index, records[other]["source_family"])
            current = nearest.get(key)
            if current is None or distance < current[1] - 1e-9:
                nearest[key] = (other, distance)
                ties.discard(key)
            elif abs(distance - current[1]) <= 1e-9:
                ties.add(key)
    parent = list(range(len(records)))
    families = [{records[i]["source_family"]} for i in range(len(records))]

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    auto_links = []
    for first, second, pair in pairs:
        first_key = (first, records[second]["source_family"])
        second_key = (second, records[first]["source_family"])
        if first_key in ties or second_key in ties:
            continue
        if nearest.get(first_key, (None,))[0] != second or nearest.get(second_key, (None,))[0] != first:
            continue
        a, b = find(first), find(second)
        if a == b or families[a] & families[b]:
            continue
        parent[b] = a
        families[a] |= families[b]
        auto_links.append(pair)

    groups: dict[int, list[dict]] = defaultdict(list)
    for index, record in enumerate(records):
        groups[find(index)].append(record)
    events = []
    for members in groups.values():
        source_families = sorted({r["source_family"] for r in members})
        lat = sum(float(r["latitude"]) for r in members) / len(members)
        lon = sum(float(r["longitude"]) for r in members) / len(members)
        start = min(r["start_date"] for r in members)
        end = max(r["end_date"] for r in members)
        identifiers = sorted(r["record_id"] for r in members)
        snmf = "OFFICIAL_INCIDENT_REPORT" in source_families
        satellite = any(f in source_families for f in (
            "AQUA_MODIS_ACTIVE_FIRE", "MODIS_DERIVED_FIRE_ATLAS"))
        if snmf and satellite:
            evidence_class = "official_report_plus_satellite_corroboration"
        elif len(source_families) > 1:
            evidence_class = "multiple_products_same_satellite_family"
        elif snmf:
            evidence_class = "official_report_only"
        else:
            evidence_class = "satellite_positive_candidate_only"
        event_id = "EVT:" + hashlib.sha256("|".join(identifiers).encode()).hexdigest()[:20]
        events.append({
            "event_id": event_id, "route": members[0]["route"],
            "start_date": start, "end_date": end,
            "latitude_mean": round(lat, 6), "longitude_mean": round(lon, 6),
            "source_families": source_families, "evidence_class": evidence_class,
            "source_record_count": len(members), "source_records": members,
        })
    events.sort(key=lambda item: (item["start_date"], item["route"], item["event_id"]))
    return events, possible


def main() -> None:
    source_records, source_counts = build_source_records()
    events, possible_links = link_records(source_records)
    no_fire = load_json(NO_FIRE)
    inputs = [GEOMETRY, *SNMF_FILES, INPE, GFA, NO_FIRE]
    summary = Counter(event["evidence_class"] for event in events)
    result = {
        "schema_version": 1,
        "experiment_id": "argentina-trails-unified-fire-event-evidence-catalog",
        "created_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "scope": {"geography": "the eight Argentine trail geometries in fire-route-geometries.json",
                  "route_buffer_km": ROUTE_RADIUS_KM,
                  "source_link_rule": f"Automatic merge only for a unique one-to-one cross-source pair on the same route, within {DATE_TOLERANCE_DAYS} calendar days and {AUTO_LINK_RADIUS_KM} km; looser matches are retained as possible links."},
        "source_counts": source_counts,
        "unified_event_count": len(events),
        "event_counts_by_evidence_class": dict(sorted(summary.items())),
        "auto_merged_cross_source_event_groups": sum(len(event["source_records"]) > 1 for event in events),
        "auto_merged_cross_source_pairs": sum(max(0, len(event["source_records"]) - 1) for event in events),
        "possible_cross_source_links_not_merged": possible_links,
        "events": events,
        "negative_evidence": {
            "source": "SNMF explicit national no-fire reports only",
            "report_days": len(no_fire["verified_explicit_no_fire_reports"]),
            "route_day_records": len(no_fire["verified_negative_route_day_labels"]),
            "meaning": "The official report explicitly said there were no nationally reported fires that day. It does not prove no unreported physical fire, and must not be treated as a verified satellite-clear route pixel.",
            "input_audit": NO_FIRE.relative_to(ROOT).as_posix(),
        },
        "source_files_sha256": {path.relative_to(ROOT).as_posix(): sha256(path) for path in inputs},
        "synthetic_observations": 0,
        "training_ready": False,
        "deployment_approved": False,
        "limitations": [
            "INPE AMS reference detections and Global Fire Atlas both derive from MODIS-family observations; their agreement is not independent sensor confirmation.",
            "SNMF report dates are incident start-date reports, often without an exact ignition time; satellite daily products have different temporal precision.",
            "Only source observations within 10 km of the documented trail polylines are included; this does not mean the fire affected or threatened the trail.",
            "Possible source matches beyond the strict unique-link rule are listed, not merged, to avoid combining nearby separate incidents.",
            "Positive event evidence and explicit no-fire report evidence do not form a complete route-time panel. Unknown coverage remains unknown.",
            "Weather forecast covariates have not been joined to these events in this catalog. Issue time and valid time must be aligned before creating forecast examples.",
        ],
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    by_route = Counter(event["route"] for event in events)
    lines = [
        "# Catálogo unificado de evidencia de incendios cerca de senderos argentinos",
        "",
        "Este artefacto integra evidencia positiva de partes SNMF, detecciones activas INPE/AQUA-MODIS y eventos del Global Fire Atlas. El resultado es un catálogo común con procedencia; todavía no es un dataset listo para entrenar ni para afirmar precisión.",
        "",
        "## Reglas de unificación",
        "",
        f"- Se filtran puntos a no más de {ROUTE_RADIUS_KM:g} km de las polilíneas completas de los ocho senderos argentinos.",
        f"- Las detecciones INPE próximas se agrupan si son de la misma ruta, están separadas por hasta {DATE_TOLERANCE_DAYS} días y sus coordenadas distan hasta {AUTO_LINK_RADIUS_KM:g} km.",
        f"- Dos fuentes distintas se fusionan solo si el par es único en ambos sentidos y cumple esa misma tolerancia temporal y espacial. Las coincidencias posibles hasta {POSSIBLE_LINK_RADIUS_KM:g} km se muestran aparte.",
        "- Cada evento conserva los registros e identificadores fuente. El acuerdo INPE–Global Fire Atlas se marca como productos de la familia MODIS, no como corroboración independiente.",
        "- No se inventan negativos: solo se mantiene por separado la evidencia de partes SNMF con frase explícita de ausencia nacional.",
        "",
        "## Resultado",
        "",
        f"El catálogo contiene **{len(events)} grupos de evidencia**, a partir de {source_counts['snmf_route_event_records_within_10km']} registros de incidente SNMF cerca de ruta, {source_counts['gfa_route_event_records_within_10km']} eventos GFA y {source_counts['inpe_route_clusters_within_10km']} grupos espaciales de detecciones INPE. Se formaron {result['auto_merged_cross_source_event_groups']} grupos con más de una fuente ({result['auto_merged_cross_source_pairs']} vínculos únicos); quedaron {len(possible_links)} coincidencias posibles sin fusionar.",
        "",
        "Hay 32 días con parte nacional explícito sin incendios reportados (256 pares día-sector), pero esos registros no significan ausencia física certificada ni completan toda la serie.",
        "",
        "## Eventos por sendero",
        "",
    ]
    lines.extend(f"- {route}: {count}" for route, count in sorted(by_route.items()))
    lines += ["", "## Límite para el modelo", "",
              "El catálogo unifica cuándo y dónde las fuentes aportan evidencia de fuego. No une automáticamente esos eventos con pronósticos meteorológicos: para construir ejemplos de predicción hay que asociar cada evento a un pronóstico archivado antes de su fecha, y asociar cada negativo a cobertura observable. Por eso `training_ready` sigue en `false`; la precisión del modelo no se modifica ni se recalcula con este catálogo.",
              "", "El JSON reproducible incluye hashes de entradas, reglas, eventos, posibles coincidencias y procedencia completa.", ""]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"output": str(OUT.relative_to(ROOT)), "events": len(events),
                      "source_counts": source_counts,
                      "evidence_classes": dict(summary),
                      "auto_merged_cross_source_event_groups": result["auto_merged_cross_source_event_groups"],
                      "auto_merged_cross_source_pairs": result["auto_merged_cross_source_pairs"],
                      "possible_links_not_merged": len(possible_links),
                      "training_ready": False}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
