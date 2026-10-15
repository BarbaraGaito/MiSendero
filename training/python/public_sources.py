"""Audited public-source adapters. No simulated context or sensor-derived targets.

Native labels are retained: modified Borg ratings, observed MOR_AMS+ outcome,
and mapper-published sac_scale. These datasets are research benchmarks; their
tasks/features must not be silently substituted for the old mobile models.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "training/data/raw/public_audit"
OUTPUT = ROOT / "training/data/public"


def digest(path: Path, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def group_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def verify_source_snapshot(model: str) -> None:
    receipt = json.loads((OUTPUT / "sources.lock.json").read_text(encoding="utf-8"))
    if digest(OUTPUT / "source_catalog.json") != receipt["catalog_sha256"]:
        raise ValueError("Source catalog changed without an audit")
    prefixes = {"fatigue": ("geofatigue/", "geofatigue.json"),
                "physio_risk": ("11505046/", "11505046.json"),
                "route_difficulty": ("osm/", "ign/"),
                "apn_route_difficulty": ("apn/",)}[model]
    expected = [entry for entry in receipt["files"] if entry["path"].startswith(prefixes)]
    if not expected:
        raise ValueError("No pinned public source snapshot for model")
    for entry in expected:
        path = (RAW / entry["path"]).resolve()
        if not path.is_relative_to(RAW.resolve()):
            raise ValueError("Source path escapes raw directory")
        if not path.exists() or digest(path) != entry["sha256"]:
            raise ValueError(f"Missing or changed public source snapshot: {entry['path']}")
    if model == "route_difficulty":
        declared = {entry["path"] for entry in expected if entry["path"].startswith("osm/")}
        actual = {p.relative_to(RAW).as_posix() for p in (RAW / "osm").glob("map_*.xml")}
        if actual != declared:
            raise ValueError("Unexpected OSM snapshot; audit it before updating sources.lock.json")


def checked_zenodo(record: str, filename: str) -> Path:
    metadata = json.loads((OUTPUT / "source_catalog.json").read_text(encoding="utf-8"))["zenodo"][record]
    if metadata["metadata"].get("license", {}).get("id") != "cc-by-4.0":
        raise ValueError(f"Unexpected license for Zenodo {record}")
    entry = next(f for f in metadata["files"] if f["key"] == filename)
    path = RAW / record / filename
    algorithm, expected = entry["checksum"].split(":", 1)
    if digest(path, algorithm) != expected:
        raise ValueError(f"Source checksum mismatch: {path.name}")
    return path


def geofatigue() -> tuple[pd.DataFrame, dict]:
    directory = RAW / "geofatigue"
    meta = json.loads((OUTPUT / "source_catalog.json").read_text(encoding="utf-8"))["geofatigue"]
    version = meta["data"]["latestVersion"]
    files = {f["dataFile"]["filename"]: f["dataFile"] for f in version["files"]}
    archive = directory / "Physiological Data.zip"
    session_path = directory / "session_metadata.json"
    # Borealis's format=original endpoint returns the deposited CSV, not a
    # generated tabular export. Its checksum must match originalFileName.
    label_path = directory / "self_reported_fatigue_level.original.tab"
    for original, path in [("Physiological Data.zip", archive), ("session_metadata.json", session_path)]:
        checksum = files[original]["checksum"]
        if digest(path, checksum["type"].lower()) != checksum["value"]:
            raise ValueError(f"GeoFatigue checksum mismatch: {original}")
    labels = pd.read_csv(label_path)
    if not {"time", "id", "borg_scale", "task_label"} <= set(labels.columns):
        raise ValueError("Unexpected GeoFatigue label schema")
    labels["time"] = pd.to_datetime(labels["time"], utc=True)
    sessions = json.loads(session_path.read_text(encoding="utf-8"))
    observations = []
    with zipfile.ZipFile(archive) as z:
        for member in sorted(z.namelist()):
            if not member.endswith("pulse-rate.csv") or "__MACOSX" in member:
                continue
            data = pd.read_csv(io.BytesIO(z.read(member)))
            required = {"timestamp_unix", "participant_full_id", "pulse_rate_bpm"}
            if not required <= set(data.columns):
                raise ValueError(f"Unexpected pulse-rate schema: {member}")
            for full_id, part in data.groupby("participant_full_id"):
                match = re.search(r"(?:^|-)p(\d+)$", str(full_id))
                if not match:
                    raise ValueError("Unknown participant identifier format")
                participant = "p" + match[1]
                part = part.copy()
                part["time"] = pd.to_datetime(part["timestamp_unix"], unit="ms", utc=True)
                part["hr"] = pd.to_numeric(part["pulse_rate_bpm"], errors="coerce")
                if "missing_value_reason" in part:
                    part = part[part["missing_value_reason"].isna() | part["missing_value_reason"].eq("")]
                part = part[np.isfinite(part["hr"]) & part["hr"].between(30, 240)]
                observed = labels[labels["id"].eq(participant)]
                for session in sessions.get(participant, []):
                    for task in session["tasks"]:
                        start = pd.Timestamp(task["start_time"])
                        end = pd.Timestamp(task["end_time"])
                        task_labels = observed[observed["time"].between(start, end) & observed["task_label"].eq(task["label"])]
                        for _, label in task_labels.iterrows():
                            # Only a completed minute before the reported label.
                            # No future signal, interpolated label, or invented reading.
                            available = part[(part["time"] >= start) & (part["time"] + pd.Timedelta(minutes=1) <= label["time"])]
                            available = available[available["time"] >= label["time"] - pd.Timedelta(minutes=2)]
                            if available.empty or pd.isna(label["borg_scale"]):
                                continue
                            reading = available.sort_values("time").iloc[-1]
                            rating = float(label["borg_scale"])
                            if not 0 <= rating <= 10:
                                raise ValueError("Borg value outside the published modified scale")
                            observations.append({
                                "hr": float(reading["hr"]),
                                "elapsed_minutes": (label["time"] - start).total_seconds() / 60,
                                "label": f"Borg {rating:g}",
                                "group_key": group_key("GeoFatigue:" + participant),
                                "row_key": group_key(f"GeoFatigue:{participant}:{label['time'].isoformat()}"),
                                "lineage": {"member": member, "label_time": label["time"].isoformat(), "signal_time": reading["time"].isoformat()},
                            })
    df = pd.DataFrame(observations)
    if df.empty:
        raise ValueError("No observed Borg labels matched measured pulse-rate windows")
    df = df.drop_duplicates("row_key").reset_index(drop=True)
    info = {
        "source": "GeoFatigue / University of Calgary",
        "url": "https://doi.org/10.5683/SP3/I0KSNR",
        "version": f"{version['versionNumber']}.{version['versionMinorNumber']}",
        "license": "CC-BY-NC-SA-4.0 (deposited README; repository metadata says CC-BY-4.0; research use only pending clarification)",
        "scope": "Respuestas Borg originales durante tareas al aire libre con carga de 20 minutos. Evalúa esa tarea; falta validar caminatas y uso clínico.",
        "label_definition": "Original borg_scale response, retained verbatim as a class; no low/medium/high relabeling.",
        "transformations": "Last complete measured pulse-rate minute within two minutes before each observation; elapsed time from published task start; discard missing readings; no imputation.",
        "raw_files": [file_evidence(p) for p in (archive, label_path, session_path, directory / "README.md")],
    }
    return df, info


def altitude_risk() -> tuple[pd.DataFrame, dict]:
    path = checked_zenodo("11505046", "ResearchData.xlsx")
    raw = pd.read_excel(path, sheet_name=0)
    records = []
    for i, row in raw.iterrows():
        values = [row["Mean_HR (bpm)"], row["Mean_SpO2 (%)"], row["MOR_AMS+"]]
        if any(pd.isna(v) for v in values):
            continue
        if row["MOR_AMS+"] not in (0, 1):
            raise ValueError("Unexpected observed AMS label")
        records.append({
            "mean_hr": float(values[0]), "mean_spo2": float(values[1]),
            "label": "AMS+" if values[2] == 1 else "AMS-",
            "group_key": group_key("AMS:" + str(row["ID"])),
            "row_key": group_key(f"AMS:worksheet-row:{i+2}"),
            "lineage": {"worksheet_row": int(i+2)},
        })
    return pd.DataFrame(records), {
        "source": "Narang / PretermBirth_Hypoxia_NocturnalSpO2_AMS",
        "url": "https://zenodo.org/records/11505046", "version": "v2", "license": "CC-BY-4.0",
        "scope": "AMS observado tras exposición nocturna a hipoxia controlada equivalente a 4200 m, en 24 participantes. Evalúa ese estudio; falta validar alertas durante caminatas.",
        "label_definition": "Published MOR_AMS+ binary outcome; no HR/SpO2 threshold-derived targets.",
        "transformations": "Published Mean_HR and Mean_SpO2 retained; drop missing rows; rename binary outcomes only; no imputation or simulated trekking context.",
        "raw_files": [file_evidence(path)],
    }


def haversine(a: tuple, b: tuple) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    value = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(value)))


def route_difficulty() -> tuple[pd.DataFrame, dict]:
    from argentina_sources import IgnElevationAtlas, catalog, terrain_features
    regional_catalog = catalog()
    region_by_snapshot = {entry["path"]: entry["region"] for entry in regional_catalog["osm"]["snapshots"]}
    snapshots = sorted((RAW / "osm").glob("map_*.xml"))
    if not snapshots:
        raise ValueError("No original OSM API snapshots found")
    nodes, ways, relations, way_regions = {}, {}, [], {}
    for path in snapshots:
        region = region_by_snapshot[path.relative_to(RAW).as_posix()]
        document = ET.parse(path).getroot()
        if document.tag != "osm" or document.attrib.get("generator", "").lower().find("openstreetmap") < 0:
            raise ValueError("Expected original public OSM API response")
        for node in document.findall("node"):
            nodes[node.attrib["id"]] = (float(node.attrib["lat"]), float(node.attrib["lon"]))
        for way in document.findall("way"):
            tags = {t.attrib["k"]: t.attrib["v"] for t in way.findall("tag")}
            if tags.get("highway") == "path" and tags.get("sac_scale") in {"hiking", "mountain_hiking", "demanding_mountain_hiking", "alpine_hiking", "demanding_alpine_hiking", "difficult_alpine_hiking"}:
                if way.attrib["id"] in ways and ways[way.attrib["id"]][0].attrib["version"] != way.attrib["version"]:
                    raise ValueError("Conflicting OSM way versions across snapshots; review before accepting")
                ways[way.attrib["id"]] = (way, tags)
                way_regions.setdefault(way.attrib["id"], set()).add(region)
        relations.extend(document.findall("relation"))
    parent = {key: key for key in ways}
    def find(key):
        while key != parent[key]:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key
    def union(a, b):
        parent[find(a)] = find(b)
    names, shared_nodes = {}, {}
    for key, (way, tags) in ways.items():
        name = tags.get("name", "").casefold().strip()
        if name:
            if name in names:
                union(key, names[name])
            names[name] = key
        for node in way.findall("nd"):
            ref = node.attrib["ref"]
            if ref in shared_nodes:
                union(key, shared_nodes[ref])
            shared_nodes[ref] = key
    for relation in relations:
        members = [m.attrib["ref"] for m in relation.findall("member") if m.attrib["type"] == "way" and m.attrib["ref"] in ways]
        for member in members[1:]:
            union(members[0], member)
    # Region holdouts are stricter than connected-network holdouts. Merge
    # regions too if a name/relation/network ever spans multiple snapshots.
    region_parent = {r: r for r in region_by_snapshot.values()}
    def region_find(region):
        while region != region_parent[region]:
            region_parent[region] = region_parent[region_parent[region]]
            region = region_parent[region]
        return region
    network_regions = {}
    for key in ways:
        network_regions.setdefault(find(key), set()).update(way_regions[key])
    for regions in network_regions.values():
        first, *rest = sorted(regions)
        for region in rest:
            region_parent[region_find(region)] = region_find(first)
    records, excluded = [], []
    with IgnElevationAtlas() as atlas:
        for key, (way, tags) in sorted(ways.items()):
            refs = [n.attrib["ref"] for n in way.findall("nd")]
            if any(ref not in nodes for ref in refs) or len(refs) < 2:
                excluded.append({"public_way_id": key, "reason": "Incomplete original geometry"})
                continue  # Never shorten a way or fabricate missing geometry.
            points = [nodes[ref] for ref in refs]
            distance = sum(haversine(a, b) for a, b in zip(points, points[1:]))
            straight = haversine(points[0], points[-1])
            if distance <= 0 or straight <= 0:
                excluded.append({"public_way_id": key, "reason": "Zero length/chord; sinuosity undefined"})
                continue
            try:
                terrain, terrain_lineage = terrain_features(points, atlas)
            except ValueError as error:
                excluded.append({"public_way_id": key, "reason": str(error)})
                continue
            region = region_find(sorted(way_regions[key])[0])
            regions = sorted(r for r in region_parent if region_find(r) == region)
            records.append({
                "distance_km": distance / 1000, "sinuosity": distance / straight, **terrain,
                "label": tags["sac_scale"], "group_key": group_key("OSM-region:" + ":".join(regions)),
                "row_key": group_key("OSM-way:" + key),
                "lineage": {"public_way_id": key, "version": way.attrib["version"], "label": tags["sac_scale"],
                            "regions": regions, "network_key": group_key("OSM-network:" + find(key)), **terrain_lineage},
            })
    return pd.DataFrame(records), {
        "source": "OpenStreetMap contributors + IGN MDE-Ar v2.1 30 m / original public snapshots",
        "url": "https://www.openstreetmap.org/copyright", "version": "way versions retained in row lineage", "license": "ODbL-1.0",
        "scope": "sac_scale publicado en tramos argentinos, con geometría OSM y relieve IGN de 30 m. Test por regiones completas; faltan regiones, observaciones y validación de rutas completas y seguridad.",
        "label_definition": "Native sac_scale tag, excluding untagged ways; never calculate labels from geometry or include sac_scale/technical_score among features.",
        "transformations": "Haversine distance and path/chord ratio from complete node geometry. Nearest original IGN cells sampled at uniform chainage <=60 m; median3 elevation profile, ascent/descent and absolute grades are derived predictors, never targets. Missing geometry/elevation rejected, no imputation. Group complete regions and connected networks, equal names and shared relations together.",
        "raw_files": [file_evidence(p) for p in snapshots] + [file_evidence(RAW / entry["path"]) for entry in regional_catalog["ign"]["tiles"]] + [file_evidence(RAW / regional_catalog["ign"]["index_path"])],
        "ign_license": regional_catalog["ign"]["license"],
        "geographic_holdout": regional_catalog["evaluation"]["route_difficulty"],
        "excluded_records": excluded,
    }


def file_evidence(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path), "bytes": path.stat().st_size}


def apn_route_difficulty():
    from argentina_sources import apn_route_difficulty as adapter
    return adapter()


ADAPTERS = {"fatigue": geofatigue, "physio_risk": altitude_risk,
            "route_difficulty": route_difficulty, "apn_route_difficulty": apn_route_difficulty}


def build_public_dataset(model: str) -> tuple[pd.DataFrame, dict]:
    verify_source_snapshot(model)
    frame, source = ADAPTERS[model]()
    if frame.empty or frame["row_key"].duplicated().any():
        raise ValueError("Empty/duplicate public observations")
    features = [c for c in frame.columns if c not in {"label", "group_key", "row_key", "lineage"}]
    if not np.isfinite(frame[features].to_numpy(dtype=float)).all():
        raise ValueError("Non-finite public features")
    directory = OUTPUT / model
    directory.mkdir(parents=True, exist_ok=True)
    dataset = frame[features + ["label"]]
    dataset.to_csv(directory / "dataset.csv", index=False)
    manifest = {"schema_version": 1, "model": model, "source": source,
                "features": features, "rows": len(frame), "synthetic_base_rows": 0,
                "dataset_sha256": digest(directory / "dataset.csv"),
                "lineage": frame[["group_key", "row_key", "lineage"]].to_dict("records")}
    (directory / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return frame, manifest
