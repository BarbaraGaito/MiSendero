"""Inventory and probe public WHAMAP phone signals for unlabelled transfer.

No videos, no native-Borg target merge and no execution of downloaded code.
The unknown mapping of f-level 0-4 stays excluded from Borg supervision.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from fetch_fatigue_extra import download
from fetch_gait_candidates import DIRECTORY as METADATA_DIRECTORY
from public_sources import ROOT, digest

DIRECTORY = ROOT / "training/data/raw/fatigue-research/whamap-sensors-v1"
PHONE_COLUMNS = [f"phone_accel{axis}" for axis in "XYZ"]+[f"phone_gyro{axis}" for axis in "XYZ"]
README_SHA = "5848ce67c2aec612995fc76dede71c5ede0eb454faf051e2b375e982bb916ab9"


def inventory():
    page = (METADATA_DIRECTORY / "whamap-page.html").read_text(encoding="utf-8")
    state, _ = json.JSONDecoder().raw_decode(page.split("window.INITIAL_STATE = ", 1)[1])
    source = state["dataset"]["snapshot"]
    if source["version"] != 1 or source["is_confidential"] or source["licence"]["short_name"] != "CC BY 4.0":
        raise ValueError("Expected public WHAMAP version 1 under CC BY 4.0")
    if digest(METADATA_DIRECTORY / "whamap-README.md") != README_SHA:
        raise ValueError("Original WHAMAP unit/protocol README changed")
    folders = json.loads((METADATA_DIRECTORY / "whamap-folders.json").read_text())
    people = sorted((f for f in folders if re.fullmatch(r"subject_\d{2}", f["name"])), key=lambda x: x["name"])
    if len(people) != 10:
        raise ValueError("Inspect a changed WHAMAP cohort before fetching data")
    DIRECTORY.mkdir(exist_ok=True)
    metadata_directory = DIRECTORY / "metadata"
    metadata_directory.mkdir(exist_ok=True)
    records, metadata_records = [], []
    for person in people:
        path = metadata_directory / (person["name"]+".json")
        url = "https://data.mendeley.com/public-api/datasets/8zt9g9g64c/files?"+urllib.parse.urlencode(
            {"folder_id": person["id"], "version": 1, "$start": 0, "$limit": 1000})
        if not path.exists():
            request = urllib.request.Request(url, headers={"User-Agent": "MiSendero public sensor eligibility audit",
                "Accept": "application/vnd.mendeley-public-dataset.1+json"})
            with urllib.request.urlopen(request, timeout=40) as response:
                payload = response.read(2_000_001)
            if len(payload) > 2_000_000:
                raise ValueError("Public file metadata exceeds 2 MB")
            json.loads(payload)
            path.write_bytes(payload)
        files = json.loads(path.read_text())
        if not isinstance(files, list) or len(files) > 12:
            raise ValueError("Inspect an unexpected number of subject files")
        metadata_records.append({"participant": person["name"], "url": url, "path": path.relative_to(DIRECTORY).as_posix(), "sha256": digest(path)})
        for entry in files:
            name = entry["filename"]
            if not name.lower().endswith(".csv"):
                continue
            content = entry["content_details"]
            if Path(name).name != name or "/" in name or "\\" in name or not re.fullmatch(r"[0-9a-f]{64}", content["sha256_hash"]):
                raise ValueError("Unexpected source data filename/checksum")
            if not content["download_url"].startswith("https://data.mendeley.com/public-files/datasets/8zt9g9g64c/"):
                raise ValueError("Source CSV download URL leaves the inspected public dataset")
            records.append({"participant": person["name"], "filename": name, "source_file_id": entry["id"],
                            "bytes": content["size"], "published_sha256": content["sha256_hash"], "url": content["download_url"],
                            "local_path": person["name"]+"/"+name})
        print(f"WHAMAP metadata {len(metadata_records)}/10 verified", flush=True)
    if not records or len(records) > 120:
        raise ValueError("Unexpected phone trace inventory")
    fit, held = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=42).split(people, groups=[p["name"] for p in people]))
    result = {"version": 1, "source": "https://data.mendeley.com/datasets/8zt9g9g64c/1", "doi": source["doi"], "license": source["licence"],
              "readme_sha256": README_SHA, "source_page_sha256": digest(METADATA_DIRECTORY / "whamap-page.html"),
              "folder_metadata_sha256": digest(METADATA_DIRECTORY / "whamap-folders.json"), "subject_metadata": metadata_records,
              "files": records, "total_csv_bytes": sum(r["bytes"] for r in records),
              "unlabelled_fitting_people": [people[i]["name"] for i in fit], "reserved_people": [people[i]["name"] for i in held],
              "native_borg_target_merge": False, "f_level_used_as_borg_target": False, "videos_downloaded": 0,
              "policy": "Phone signals are candidates for unlabelled pretraining only. Native f-level-to-CR10 mapping remains unestablished; no copied trace cell becomes an independent questionnaire response. Reserve two whole external participants before any model fitting."}
    path = DIRECTORY / "inventory.json"
    if path.exists() and json.loads(path.read_text()) != result:
        raise ValueError("Preserve the frozen WHAMAP inventory before accepting changed source metadata")
    path.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    return result


def probe(record):
    choices = [r for r in record["files"] if r["participant"] in record["unlabelled_fitting_people"]
               and "walking" in r["filename"].lower() and "_b" not in r["filename"].lower()]
    if not choices:
        raise ValueError("No fitting-person walking CSV available for a bounded probe")
    source = sorted(choices, key=lambda r: (r["participant"], r["filename"]))[0]
    if source["bytes"] > 50_000_000:
        raise ValueError("Inspect a walking probe larger than 50 MB before downloading it")
    path = download(source["url"], DIRECTORY / source["local_path"], maximum_bytes=source["bytes"],
                    expected_bytes=source["bytes"], sha256=source["published_sha256"])
    header = pd.read_csv(path, nrows=0).columns.tolist()
    if not set(["time", *PHONE_COLUMNS]) <= set(header):
        print("Original trace column names:", header, flush=True)
        raise ValueError("Inspect original phone column names before preparing any tensors")
    frame = pd.read_csv(path, usecols=["time", *PHONE_COLUMNS])
    for name in PHONE_COLUMNS:
        frame[name] = pd.to_numeric(frame[name], errors="coerce")
    times = pd.to_timedelta(frame["time"])
    delta = times.diff().dt.total_seconds()
    acceleration = np.linalg.norm(frame[PHONE_COLUMNS[:3]].to_numpy(float), axis=1)
    gyro = np.linalg.norm(frame[PHONE_COLUMNS[3:]].to_numpy(float), axis=1)
    summary = {"mode": "one_fitting_person_schema_probe", "retrieved_at": datetime.now(timezone.utc).isoformat(),
               "inventory_sha256": digest(DIRECTORY / "inventory.json"), "source": source,
               "actual_sha256": digest(path), "rows": len(frame), "columns_in_original": len(header),
               "phone_missing_cells": int(frame[PHONE_COLUMNS].isna().sum().sum()),
               "phone_identical_consecutive_rows": int(frame[PHONE_COLUMNS].eq(frame[PHONE_COLUMNS].shift()).all(axis=1).sum()),
               "nonpositive_timestamp_steps": int(delta.le(0).sum()), "large_gaps_over_100ms": int(delta.gt(.1).sum()),
               "positive_dt_median_seconds": float(delta[delta > 0].median()),
               "acceleration_norm_quantiles": np.nanquantile(acceleration, [0, .5, .99, 1.]).tolist(),
               "gyro_norm_quantiles": np.nanquantile(gyro, [0, .5, .99, 1.]).tolist(),
               "native_borg_targets_used": 0, "f_level_read_for_training": False, "reserved_people_read": False,
               "timestamp_policy": "Clock strings only within each source file; no date/timezone or cross-study report alignment inferred."}
    (DIRECTORY / "probe.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("source",)}, indent=2), flush=True)


def fitting_traces(record):
    selected = [r for r in record["files"] if r["participant"] in record["unlabelled_fitting_people"]
                and re.fullmatch(r"(?:walking|uphill)(?:_B)?\.csv", r["filename"], flags=re.IGNORECASE)]
    if len(selected) != 32 or sum(r["bytes"] for r in selected) != 718190042:
        raise ValueError("Inspect a changed eight-person walking/uphill download plan")
    signature = {"inventory_sha256": digest(DIRECTORY / "inventory.json"), "files": selected,
                 "fitting_people": record["unlabelled_fitting_people"], "reserved_people": record["reserved_people"]}
    receipt_path = DIRECTORY / "fitting-traces-receipt.json"
    receipt = {"version": 1, "download_started_at": datetime.now(timezone.utc).isoformat(), "signature": signature,
               "verified_files": [], "all_complete_and_verified": False, "native_borg_targets_used": 0,
               "f_level_used_as_borg_target": False, "reserved_people_downloaded": False, "videos_downloaded": 0}
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt["signature"] != signature:
            raise ValueError("Frozen unlabelled fitting trace download plan changed")

    def fetch(source):
        path = (DIRECTORY / source["local_path"]).resolve()
        if not path.is_relative_to(DIRECTORY.resolve()):
            raise ValueError("Public source filename escapes its dedicated raw directory")
        result = download(source["url"], path, maximum_bytes=source["bytes"], expected_bytes=source["bytes"], sha256=source["published_sha256"])
        return {"local_path": source["local_path"], "bytes": result.stat().st_size, "sha256": digest(result)}

    if receipt["all_complete_and_verified"]:
        for source in selected:
            path = DIRECTORY / source["local_path"]
            if path.stat().st_size != source["bytes"] or digest(path) != source["published_sha256"]:
                raise ValueError("A previously verified public fitting trace changed")
        print("All 32 fitting-only traces already verified; preserving the frozen receipt", flush=True)
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch, source) for source in selected]
        for future in concurrent.futures.as_completed(futures):
            entry = future.result()
            receipt["verified_files"] = [r for r in receipt["verified_files"] if r["local_path"] != entry["local_path"]]+[entry]
            receipt["verified_files"].sort(key=lambda r: r["local_path"])
            receipt["all_complete_and_verified"] = len(receipt["verified_files"]) == len(selected)
            receipt_path.write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
            print(f"Unlabelled phone traces {len(receipt['verified_files'])}/32 verified: {entry['local_path']}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--fitting-traces", action="store_true")
    args = parser.parse_args()
    record = inventory()
    print(f"WHAMAP inventory: {len(record['files'])} CSV files / {record['total_csv_bytes']} bytes, 8 fitting and 2 reserved people", flush=True)
    if args.probe:
        probe(record)
    if args.fitting_traces:
        fitting_traces(record)
