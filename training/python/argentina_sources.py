"""Original APN publications and IGN raster measurements for Argentine trails.

Published route estimates remain estimates. No labels are reconstructed from
distance, time or terrain; APN and OSM retain separate prediction tasks.
"""
from __future__ import annotations

import json
import math
import re
import zipfile
from contextlib import ExitStack

import numpy as np
import pandas as pd
import rasterio
from bs4 import BeautifulSoup
from scipy.ndimage import median_filter

from public_sources import OUTPUT, RAW, file_evidence, group_key, haversine


def catalog():
    return json.loads((OUTPUT / "source_catalog.json").read_text(encoding="utf-8"))["argentina"]


def normalized_text(tag):
    return " ".join(tag.get_text(" ", strip=True).split())


# Python 3.11+: possessive quantifiers avoid repartitioning numbers/whitespace.
# Numeric boundaries prevent searches from restarting inside the same number.
DISTANCE = re.compile(r"(?<![\d.,])(?P<value>\d++(?:[.,]\d++)?)\s*+(?P<unit>km|mts?|metros?|m)\b", re.I)
DURATION = re.compile(r"(?<!\d)(?P<value>\d++(?::\d{2}|[.,]\d++)?)\s*+(?P<unit>horas?|hs?|minutos?|min)\b", re.I)
DIFFICULTY = re.compile(r"\bDificultad\s*+:?\s*+(baja|media(?:\s*+[-/]\s*+alta)?|alta)\b", re.I)


def distance_km(text):
    values = list(DISTANCE.finditer(text))
    if len(values) != 1:
        raise ValueError("Distance missing or multiple published alternatives")
    item = values[0]
    value = float(item["value"].replace(",", "."))
    return value if item["unit"].lower() == "km" else value / 1000


def duration_minutes(text):
    values = list(DURATION.finditer(text))
    if not values:
        raise ValueError("No explicit published duration")
    total = 0.0
    units = set()
    for item in values:
        hours = item["unit"].lower().startswith("h")
        if hours in units:
            raise ValueError("Multiple alternative durations")
        units.add(hours)
        if ":" in item["value"]:
            if not hours:
                raise ValueError("Ambiguous minute notation")
            hour, minute = map(int, item["value"].split(":"))
            if minute >= 60:
                raise ValueError("Invalid published hour notation")
            total += hour * 60 + minute
        else:
            total += float(item["value"].replace(",", ".")) * (60 if hours else 1)
    return total


def basis(text):
    value = text.casefold()
    if "ida y vuelta" in value:
        return "round_trip"
    if "(ida)" in value or "hasta la cumbre" in value:
        return "one_way"
    if "(total)" in value:
        return "total"
    return "unspecified"


def parse_apn_page(path, park, exclusions):
    """Accept only explicit individual walking labels and numeric summaries."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    article = soup.select_one("article.content_format")
    if article is None:
        raise ValueError(f"Missing original APN article in {path.name}")
    walking = park == "tierra_del_fuego"
    heading = ""
    seen, records, discarded = set(), [], []
    for tag in article.find_all(["h3", "h4", "h5", "p", "li"]):
        text = normalized_text(tag)
        if tag.name.startswith("h"):
            if tag.name in {"h3", "h4"} and park != "tierra_del_fuego":
                walking = "senderismo" in text.casefold()
            heading = text
            continue
        if not walking or (tag.name == "li" and tag.find("p")):
            continue
        label = DIFFICULTY.search(text)
        if not label or text in seen:
            continue
        seen.add(text)
        # Only a structured fact summary is accepted. Descriptive references
        # such as "sendero de dificultad baja" are never independent records.
        if "Distancia:" in text:
            name = heading
            distance_text = text.split("Distancia:", 1)[1].split("Duraci", 1)[0]
            duration_text = re.split(r"Duraci.n:\s*", text, maxsplit=1)[-1].split("Desnivel", 1)[0]
        else:
            prefix = text[:label.start()].rstrip(" /|")
            first = DISTANCE.search(prefix) or DURATION.search(prefix)
            # Los Alerces publishes the time before the distance.
            first_numeric = re.search(r"\d", prefix)
            name = prefix[:first_numeric.start()].strip(" .") if first_numeric and prefix[:first_numeric.start()].strip(" .") else heading
            pieces = [piece.strip() for piece in re.split(r"[/|]", prefix)]
            distance_text = " / ".join(piece for piece in pieces if DISTANCE.search(piece))
            duration_text = " / ".join(piece for piece in pieces if DURATION.search(piece))
            if not first or not any(sep in text[:label.start()] for sep in ("/", "|")):
                continue
        reason = exclusions.get(name)
        if not reason and "a caballo" in duration_text.casefold():
            reason = "Published duration is for horseback travel, not walking"
        try:
            if reason:
                raise ValueError(reason)
            distance, duration = distance_km(distance_text), duration_minutes(duration_text)
            if distance <= 0 or duration <= 0:
                raise ValueError("Non-positive published route estimate")
        except ValueError as error:
            discarded.append({"name": name, "reason": str(error), "evidence": text})
            continue
        distance_basis = basis(distance_text)
        duration_basis = basis(duration_text)
        # Normalize typography only: media/alta and media-alta are the same
        # compound label. Never collapse a compound label into media or alta.
        native = "".join(label[1].casefold().split()).replace("/", "-")
        records.append({
            "published_distance_km": distance,
            "published_duration_minutes": duration,
            **{f"distance_basis_{value}": float(distance_basis == value)
               for value in ("one_way", "round_trip", "total", "unspecified")},
            **{f"duration_basis_{value}": float(duration_basis == value)
               for value in ("one_way", "round_trip", "total", "unspecified")},
            "label": native, "group_key": group_key("APN-park:" + park),
            "row_key": group_key("APN-route:" + park + ":" + name.casefold()),
            "lineage": {"park": park, "name": name, "snapshot": path.name,
                        "published_label": label[1], "distance_basis": distance_basis,
                        "duration_basis": duration_basis, "evidence": text},
        })
    keys = [record["row_key"] for record in records]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate APN route: review original before accepting it")
    return records, discarded


def apn_route_difficulty():
    entries = catalog()["apn"]["pages"]
    rows, exclusions = [], []
    for entry in entries:
        records, discarded = parse_apn_page(RAW / entry["path"], entry["park"], entry.get("exclude_routes", {}))
        rows.extend(records)
        exclusions.extend({"park": entry["park"], **item} for item in discarded)
    return pd.DataFrame(rows), {
        "source": "Administración de Parques Nacionales / fichas oficiales de senderos argentinos",
        "url": "https://www.argentina.gob.ar/parquesnacionales",
        "version": "Original HTML snapshots, 2026-10-14", "license": "CC-BY-4.0 (Argentina.gob.ar terms, except otherwise stated)",
        "scope": "Dificultad publicada por APN para recorridos completos. Distancias y duraciones son estimaciones publicadas, no tiempos medidos de caminantes. Evaluación con parques completos separados; no certifica seguridad ni generalización nacional.",
        "label_definition": "Individual APN difficulty retained; case/separator normalization only, including the native media-alta compound class. No conversion to sac_scale or labels computed from features.",
        "transformations": "Parse explicit summary units; retain one-way/round-trip/total/unspecified basis separately without doubling values. Exclude missing/ambiguous values, conflicting source facts and horseback durations. Names and park identifiers are provenance only.",
        "raw_files": [file_evidence(RAW / entry["path"]) for entry in entries],
        "excluded_records": exclusions,
        "geographic_holdout": catalog()["evaluation"]["apn_route_difficulty"],
    }


class IgnElevationAtlas:
    """Read original HFA raster cells from the official ZIPs, without fill values."""
    def __init__(self, entries=None):
        self.entries = entries if entries is not None else catalog()["ign"]["tiles"]
        self.stack = ExitStack()
        self.datasets = []

    def __enter__(self):
        try:
            for entry in sorted(self.entries, key=lambda item: item["path"]):
                path = RAW / entry["path"]
                with zipfile.ZipFile(path) as archive:
                    images = [name for name in archive.namelist() if name.lower().endswith(".img")]
                if len(images) != 1:
                    raise ValueError("Expected one original IGN elevation raster per tile")
                ds = self.stack.enter_context(rasterio.open("zip://" + path.resolve().as_posix() + "!" + images[0]))
                if ds.crs != rasterio.crs.CRS.from_epsg(4326) or ds.count != 1 or ds.driver != "HFA":
                    raise ValueError("Unexpected original IGN raster schema/CRS")
                self.datasets.append((entry["path"], ds))
            return self
        except BaseException:
            self.stack.close()
            raise

    def __exit__(self, *args):
        self.stack.close()

    def sample(self, points):
        values = np.full(len(points), np.nan)
        used = set()
        for name, ds in self.datasets:
            b = ds.bounds
            indices = [i for i, (lat, lon) in enumerate(points)
                       if not np.isfinite(values[i]) and b.left <= lon < b.right and b.bottom < lat <= b.top]
            if not indices:
                continue
            samples = ds.sample([(points[i][1], points[i][0]) for i in indices], masked=True)
            for i, reading in zip(indices, samples):
                if not np.ma.is_masked(reading[0]) and np.isfinite(reading[0]) and reading[0] != ds.nodata:
                    values[i] = float(reading[0])
                    used.add(name)
        if not np.isfinite(values).all():
            raise ValueError("IGN coverage missing/nodata; never fabricate or impute elevation")
        return values, sorted(used)


def terrain_features(points, atlas):
    distances = np.asarray([0.0] + [haversine(a, b) for a, b in zip(points, points[1:])]).cumsum()
    distance = distances[-1]
    if distance <= 0:
        raise ValueError("Zero-length route")
    # Uniform chainage avoids counting more elevation noise on denser OSM nodes.
    # These are sampling locations, never new training observations or labels.
    chainage = np.linspace(0, distance, max(2, math.ceil(distance / 60) + 1))
    lat = np.interp(chainage, distances, [p[0] for p in points])
    lon = np.interp(chainage, distances, [p[1] for p in points])
    elevation, tiles = atlas.sample(list(zip(lat, lon)))
    profile = median_filter(elevation, size=3, mode="nearest")
    delta = np.diff(profile)
    return {
        "dem_elevation_min_m": float(profile.min()), "dem_elevation_max_m": float(profile.max()),
        "dem_ascent_m": float(np.maximum(delta, 0).sum()), "dem_descent_m": float(np.maximum(-delta, 0).sum()),
        "dem_mean_abs_grade_pct": float(np.abs(delta).sum() / distance * 100),
        "dem_max_abs_grade_pct": float((np.abs(delta) / np.diff(chainage)).max() * 100),
    }, {"ign_tiles": tiles, "dem_sampling_points": len(chainage)}
