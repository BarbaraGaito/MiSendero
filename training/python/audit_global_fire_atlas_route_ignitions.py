#!/usr/bin/env python3
"""Screen Global Fire Atlas daily ignition points near Argentine trail lines.

The source archive is read directly; no global shapefiles are extracted. This
is a positive-event coverage screen, not a fire-forecast precision evaluation.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

from environmental_sources import ROOT


ARCHIVE = ROOT / "training/data/environmental/private/global-fire-atlas-2026-04/SHP_ignitions.zip"
GEOMETRY = ROOT / "training/data/environmental/private/fire-route-geometries.json"
REPORT_DIR = ROOT / "docs/environmental-models-2026-10-22"
OUTPUT_JSON = REPORT_DIR / "fire-global-fire-atlas-route-ignitions-2022-2026.json"
OUTPUT_MD = REPORT_DIR / "fire-global-fire-atlas-route-ignitions-2022-2026.md"
INPE_CROSSCHECK = REPORT_DIR / "fire-inpe-reference-detections-route-coverage-2018-2025.json"
SNMF_EVENTS = REPORT_DIR / "fire-viirs-daily-l3-snmf-event-audit-2023-2025.json"
YEARS = (2022, 2023, 2024, 2025, 2026)
RADIUS_KM = 10.0
DATE_TOLERANCE_DAYS = 2
KM_PER_DEGREE = 111.32


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def field_defs(dbf) -> tuple[int, int, list[tuple[str, int]]]:
    header = dbf.read(32)
    count = struct.unpack("<I", header[4:8])[0]
    header_len, record_len = struct.unpack("<HH", header[8:12])
    fields: list[tuple[str, int]] = []
    while dbf.tell() < header_len:
        first = dbf.read(1)
        if first == b"\x0d":
            break
        descriptor = first + dbf.read(31)
        if len(descriptor) != 32:
            raise RuntimeError("Truncated DBF field descriptor.")
        name = descriptor[:11].split(b"\0", 1)[0].decode("ascii")
        fields.append((name, descriptor[16]))
    dbf.seek(header_len)
    return count, record_len, fields


def point_line_distance_km(lat: float, lon: float, coordinates: list[list[float]]) -> float:
    """Local equirectangular point-to-polyline distance (lat,lon coordinates)."""
    cosine = math.cos(math.radians(lat))
    px = py = 0.0
    best = float("inf")
    for (lat1, lon1), (lat2, lon2) in zip(coordinates, coordinates[1:]):
        ax = (lon1 - lon) * KM_PER_DEGREE * cosine
        ay = (lat1 - lat) * KM_PER_DEGREE
        bx = (lon2 - lon) * KM_PER_DEGREE * cosine
        by = (lat2 - lat) * KM_PER_DEGREE
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        t = 0.0 if length_sq == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length_sq))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def point_distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    haversine = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(haversine))


def route_bounds(routes: list[dict]) -> list[dict]:
    output = []
    for route in routes:
        coords = route["route_coordinates"]
        lats = [point[0] for point in coords]
        lons = [point[1] for point in coords]
        lat_pad = RADIUS_KM / KM_PER_DEGREE
        min_cos = math.cos(math.radians(max(abs(min(lats)), abs(max(lats))) + lat_pad))
        lon_pad = RADIUS_KM / (KM_PER_DEGREE * max(min_cos, 0.01))
        output.append({
            "name": route["name"],
            "coordinates": coords,
            "min_lat": min(lats) - lat_pad,
            "max_lat": max(lats) + lat_pad,
            "min_lon": min(lons) - lon_pad,
            "max_lon": max(lons) + lon_pad,
        })
    return output


def read_year(archive: zipfile.ZipFile, year: int, routes: list[dict]) -> tuple[int, list[dict]]:
    prefix = f"GFA_v20260408_ignitions_{year}"
    dbf = archive.open(prefix + ".dbf")
    shp = archive.open(prefix + ".shp")
    expected_count, record_len, fields = field_defs(dbf)
    field_offsets: dict[str, tuple[int, int]] = {}
    offset = 1  # DBF deletion flag
    for name, width in fields:
        field_offsets[name] = (offset, width)
        offset += width
    for required in ("start_date", "size"):
        if required not in field_offsets:
            raise RuntimeError(f"Missing required DBF field {required} in {year} archive.")
    shape_header = shp.read(100)
    if len(shape_header) != 100 or struct.unpack("<i", shape_header[32:36])[0] != 1:
        raise RuntimeError(f"Unexpected point shapefile header for {year}.")

    candidates: list[dict] = []
    for index in range(expected_count):
        row = dbf.read(record_len)
        record_header = shp.read(8)
        if len(row) != record_len or len(record_header) != 8:
            raise RuntimeError(f"Truncated shapefile pair for {year}, row {index}.")
        _record_number, content_words = struct.unpack(">ii", record_header)
        content_bytes = content_words * 2
        content = shp.read(content_bytes)
        if len(content) != content_bytes or content_bytes < 20:
            raise RuntimeError(f"Invalid point geometry for {year}, row {index}.")
        shape_type, lon, lat = struct.unpack("<idd", content[:20])
        if shape_type != 1 or row[0:1] == b"*":
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        possible_routes = [
            route for route in routes
            if route["min_lat"] <= lat <= route["max_lat"]
            and route["min_lon"] <= lon <= route["max_lon"]
        ]
        if not possible_routes:
            continue
        decoded = {
            name: row[start:start + width].decode("ascii", "replace").strip()
            for name, (start, width) in field_offsets.items()
        }
        raw_date = decoded["start_date"]
        try:
            start_date = date.fromisoformat(raw_date[:10]).isoformat()
        except ValueError:
            continue
        try:
            size_km2 = float(decoded["size"])
        except ValueError:
            size_km2 = None
        for route in possible_routes:
            distance = point_line_distance_km(lat, lon, route["coordinates"])
            if distance <= RADIUS_KM:
                candidates.append({
                    "fire_season": year,
                    "fire_id": decoded.get("fire_ID", ""),
                    "route": route["name"],
                    "start_date": start_date,
                    "end_date": decoded.get("end_date", "")[:10],
                    "latitude": lat,
                    "longitude": lon,
                    "distance_to_full_route_km": round(distance, 3),
                    "size_km2": size_km2,
                    "size_ha": round(size_km2 * 100, 2) if size_km2 is not None else None,
                    "duration_days": decoded.get("duration"),
                    "landcover": decoded.get("landcover"),
                })
    dbf.close()
    shp.close()
    return expected_count, candidates


def main() -> None:
    source_manifest = json.loads((ARCHIVE.parent / "download-manifest.json").read_text(encoding="utf-8"))
    geometry_data = json.loads(GEOMETRY.read_text(encoding="utf-8"))
    inpe_audit = json.loads(INPE_CROSSCHECK.read_text(encoding="utf-8"))
    snmf_audit = json.loads(SNMF_EVENTS.read_text(encoding="utf-8"))
    routes = route_bounds(geometry_data["fire_route_geometries"])
    all_hits: list[dict] = []
    counts_by_year: dict[str, int] = {}
    archive_members: list[str] = []
    with zipfile.ZipFile(ARCHIVE) as archive:
        for year in YEARS:
            prefix = f"GFA_v20260408_ignitions_{year}"
            if prefix + ".dbf" not in archive.namelist() or prefix + ".shp" not in archive.namelist():
                continue
            count, hits = read_year(archive, year, routes)
            counts_by_year[str(year)] = count
            all_hits.extend(hits)
        archive_members = [name for name in archive.namelist() if name.endswith((".dbf", ".shp"))]

    by_route = Counter(hit["route"] for hit in all_hits)
    by_year = Counter(hit["start_date"][:4] for hit in all_hits)
    inpe_detections = inpe_audit["nearby_detections"]
    snmf_events = snmf_audit["event_rows"]
    inpe_matched = 0
    snmf_matched = 0
    inpe_match_rows: list[dict] = []
    snmf_match_rows: list[dict] = []
    for hit in all_hits:
        event_date = date.fromisoformat(hit["start_date"])
        event_point = (hit["latitude"], hit["longitude"])
        inpe_matches = []
        for detection in inpe_detections:
            detection_date = date.fromisoformat(detection["date"])
            day_gap = abs((event_date - detection_date).days)
            if day_gap > DATE_TOLERANCE_DAYS:
                continue
            distance = point_distance_km(event_point, (detection["latitude"], detection["longitude"]))
            if distance <= RADIUS_KM:
                inpe_matches.append({
                    "date": detection["date"],
                    "day_gap": day_gap,
                    "distance_km": round(distance, 3),
                    "detection_id": detection.get("detection_id"),
                })
        snmf_matches = []
        for event in snmf_events:
            coordinates = event.get("incident_coordinates") or {}
            latitude, longitude = coordinates.get("latitude"), coordinates.get("longitude")
            if latitude is None or longitude is None:
                continue
            report_date = date.fromisoformat(event["reported_start_date"])
            day_gap = abs((event_date - report_date).days)
            if day_gap > DATE_TOLERANCE_DAYS:
                continue
            distance = point_distance_km(event_point, (latitude, longitude))
            if distance <= RADIUS_KM:
                snmf_matches.append({
                    "reported_start_date": event["reported_start_date"],
                    "day_gap": day_gap,
                    "distance_km": round(distance, 3),
                    "route": event.get("route"),
                    "incident_names": event.get("incident_names", []),
                })
        hit["inpe_reference_detections_within_10km_and_2days"] = sorted(
            inpe_matches, key=lambda m: (m["day_gap"], m["distance_km"])
        )
        hit["snmf_report_events_within_10km_and_2days"] = sorted(
            snmf_matches, key=lambda m: (m["day_gap"], m["distance_km"])
        )
        if inpe_matches:
            inpe_matched += 1
            inpe_match_rows.append({"date": hit["start_date"], "route": hit["route"], "fire_id": hit["fire_id"]})
        if snmf_matches:
            snmf_matched += 1
            snmf_match_rows.append({"date": hit["start_date"], "route": hit["route"], "fire_id": hit["fire_id"]})
    result = {
        "experiment_id": "global-fire-atlas-2026-daily-ignition-points-near-argentina-trails",
        "source": {
            "dataset": "Global Fire Atlas, Zenodo record 17669692, updated 2026-04-08",
            "archive_manifest": source_manifest,
            "archive_sha256": source_manifest["sha256"],
            "route_geometry_sha256": sha256(GEOMETRY),
            "inpe_reference_detection_audit": INPE_CROSSCHECK.relative_to(ROOT).as_posix(),
            "inpe_reference_detection_audit_sha256": sha256(INPE_CROSSCHECK),
            "snmf_event_audit": SNMF_EVENTS.relative_to(ROOT).as_posix(),
            "snmf_event_audit_sha256": sha256(SNMF_EVENTS),
            "calendar_years_screened_from_local_fire_season_layers": YEARS,
            "fire_season_record_counts": counts_by_year,
        },
        "protocol": {
            "spatial_unit": "ignition point within 10 km of complete route polyline",
            "distance_method": "local equirectangular projection per candidate point",
            "routes": [route["name"] for route in routes],
            "date_field": "GFA start_date, daily inferred burn/ignition date",
            "threshold_km": RADIUS_KM,
            "synthetic_observations": 0,
        },
        "summary": {
            "fire_season_layers_screened": len(counts_by_year),
            "global_ignition_records_screened": sum(counts_by_year.values()),
            "route_event_records_within_10km": len(all_hits),
            "unique_route_fire_season_ids": len({(r["route"], r["fire_season"], r["fire_id"]) for r in all_hits}),
            "unique_start_dates_with_route_event": len({r["start_date"] for r in all_hits}),
            "records_by_calendar_start_year": dict(sorted(by_year.items())),
            "records_by_route": dict(by_route.most_common()),
            "route_hits_with_size_at_least_21ha": sum(1 for r in all_hits if (r["size_ha"] or 0) >= 21),
            "gfa_events_with_nearby_inpe_detection_within_2days": inpe_matched,
            "gfa_events_with_nearby_snmf_report_within_2days": snmf_matched,
            "crosscheck_day_tolerance": DATE_TOLERANCE_DAYS,
            "crosscheck_point_distance_km": RADIUS_KM,
            "deployment_approved": False,
        },
        "positive_source_crosschecks": {
            "inpe_reference_detection_matches": inpe_match_rows,
            "snmf_report_event_matches": snmf_match_rows,
            "interpretation": "Positive-source corroboration only. The INPE archive is a separate active-fire detection product but may share satellite platforms with MODIS-derived GFA. SNMF report matches independently corroborate only those reported events; neither source supplies verified no-fire route-days.",
        },
        "route_event_records": sorted(all_hits, key=lambda r: (r["start_date"], r["route"], r["fire_id"])),
        "limitations": [
            "GFA ignitions and dates are inferred from MODIS MCD64A1 burned-area progression, not field-confirmed ignition times.",
            "The date is daily, not hourly; it cannot validate 1-hour or exact 24-hour lead-time prediction.",
            "The GFA source paper reports a minimum detectable burned area around one MODIS pixel (~21 ha); small fires may be absent.",
            "An ignition-point list is positive-only and provides no verified fire-free route-days, so it cannot estimate alert precision or false-alarm rate.",
            "The ±2-day and 10-km cross-source matching rule is exploratory and was not preregistered; match counts are descriptive, not confirmatory metrics.",
            "The route buffer screen is a candidate event-coverage test; no model was evaluated or approved for production by this script.",
            "The 2025 and 2026 local fire-season layers are incomplete in the latest product release; interpret recent-year counts as provisional.",
        ],
        "source_archive_member_count": len(archive_members),
    }
    OUTPUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Global Fire Atlas: igniciones diarias cerca de rutas argentinas",
        "",
        "Se filtraron las capas anuales de puntos GFA para las temporadas locales 2022–2026, usando los puntos y fechas del propio shapefile. El ZIP se leyó directamente, sin extraer sus 8,65 GB de contenido. El buffer es de 10 km alrededor de las polilíneas completas revisadas.",
        "",
        f"El filtro encontró **{len(all_hits)} registros evento-ruta** en **{result['summary']['unique_route_fire_season_ids']} combinaciones ruta-incendio** y **{result['summary']['unique_start_dates_with_route_event']} fechas de inicio distintas**. Las capas examinadas contienen {sum(counts_by_year.values()):,} puntos de ignición globales. No son observaciones independientes para una métrica de precisión.",
        "",
        "## Cobertura por temporada de inicio",
        "",
        "| Año de `start_date` | Registros evento-ruta |",
        "|---:|---:|",
    ]
    for year, count in sorted(by_year.items()):
        lines.append(f"| {year} | {count} |")
    lines.extend([
        "",
        "## Interpretación",
        "",
        "Este resultado agrega candidatos de eventos positivos basados en área quemada, independientes de los reportes administrativos. GFA deriva las igniciones y fechas de MCD64A1: la fecha tiene resolución diaria, no hora observada, y el producto puede omitir fuegos menores a aproximadamente un píxel MODIS. Por eso no valida predicciones con horizonte horario y no reemplaza la adjudicación de incidentes argentinos.",
        "",
        "La lista solo contiene fuegos detectados. No ofrece días-ruta verificados sin fuego; por tanto, no permite calcular precisión, tasa de falsas alarmas ni una probabilidad. Se debe deduplicar y contrastar con SNMF, perímetros oficiales y detecciones de otros sensores antes de usar los puntos como positivos de prueba.",
        "",
        f"En el cruce positivo exploratorio (regla de ±{DATE_TOLERANCE_DAYS} días y 10 km no preregistrada), **{inpe_matched}/{len(all_hits)}** registros tuvieron una detección INPE cercana y **{snmf_matched}/{len(all_hits)}** coincidieron con el subconjunto SNMF georreferenciado. Son corroboraciones descriptivas; INPE puede compartir plataformas con MODIS y los reportes SNMF usados son seleccionados, por lo que estos conteos no miden precisión ni recall general.",
        "",
        "Los años 2025 y 2026 corresponden a temporadas de fuego local y la versión 2026 advierte que las temporadas más recientes pueden estar incompletas.",
        "",
        "La salida reproducible con todos los casos, tamaños, coordenadas, fechas y hashes está en el [JSON](fire-global-fire-atlas-route-ignitions-2022-2026.json). El archivo fuente original está bajo `training/data/environmental/private/` y no se incluye en la APK.",
        "",
        "Fuente: [Global Fire Atlas 2026, Zenodo 17669692](https://zenodo.org/records/17669692); metodología: [Andela et al., 2019](https://doi.org/10.5194/essd-11-529-2019).",
    ])
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"output_json": str(OUTPUT_JSON.relative_to(ROOT)),
                      "output_md": str(OUTPUT_MD.relative_to(ROOT)),
                      "summary": result["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
