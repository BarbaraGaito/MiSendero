"""Unlabelled fitting-only WHAMAP phone bins with explicit clock segments.

Published SI phone channels only. No f-level, activity, person, wall-clock,
date or questionnaire value becomes a signal channel or supervision target.
Clock reversals split traces; gaps remain absent; no interpolation is used.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fatigue_phone_spectral import BIN, BIN_COLUMNS, observed_bins
from fetch_whamap_sensors import DIRECTORY, PHONE_COLUMNS, README_SHA
from public_sources import digest

CACHE = DIRECTORY / "phone-10hz-cache"
EPOCH = pd.Timestamp("2000-01-01", tz="UTC")


def segments(raw):
    data = raw[["time", *PHONE_COLUMNS]].copy()
    clock = pd.to_timedelta(data["time"])
    if clock.isna().any():
        raise ValueError("An original within-file phone clock is required")
    for column in PHONE_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    repeated = int(data[PHONE_COLUMNS].eq(data[PHONE_COLUMNS].shift()).all(axis=1).sum())
    labels = clock.diff().lt(pd.Timedelta(0)).cumsum()
    result = []
    for _, indexes in data.groupby(labels, sort=False).groups.items():
        original = data.loc[indexes]
        values = original.rename(columns=dict(zip(PHONE_COLUMNS, ["ax", "ay", "az", "wx", "wy", "wz"]))).copy()
        # This fixed epoch is an indexing convenience for a relative clock,
        # not an inferred collection date, timezone or report timestamp.
        values["time"] = EPOCH+clock.loc[indexes]
        values["speed"], values["altitude"] = np.nan, np.nan
        bins = observed_bins(values)
        quality = bins.attrs["quality"]
        bins = bins[(bins.index >= values["time"].min()) & (bins.index+BIN <= values["time"].max())].copy()
        bins.attrs["quality"] = quality
        result.append(bins)
    return result, {"original_sample_rows": len(data), "identical_consecutive_export_rows": repeated,
                    "original_missing_phone_cells": int(data[PHONE_COLUMNS].isna().sum().sum()),
                    "clock_reversals": int(clock.diff().lt(pd.Timedelta(0)).sum())}


def prepare():
    receipt_path = DIRECTORY / "fitting-traces-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    inventory = json.loads((DIRECTORY / "inventory.json").read_text())
    if (not receipt["all_complete_and_verified"] or len(receipt["verified_files"]) != 32
            or receipt["signature"]["inventory_sha256"] != digest(DIRECTORY / "inventory.json")
            or inventory["readme_sha256"] != README_SHA):
        raise ValueError("Complete publisher-verified fitting-only sensor traces required")
    sources = receipt["signature"]["files"]
    if any(r["participant"] not in inventory["unlabelled_fitting_people"] or r["participant"] in inventory["reserved_people"] for r in sources):
        raise ValueError("A reserved source participant entered phone preparation")
    CACHE.mkdir(exist_ok=True)
    code_sha, policy_sha = digest(Path(__file__)), digest(Path(__file__).with_name("fatigue_phone_spectral.py"))
    reports = []
    for source in sources:
        raw_path = DIRECTORY / source["local_path"]
        if raw_path.stat().st_size != source["bytes"] or digest(raw_path) != source["published_sha256"]:
            raise ValueError("Original public phone source changed")
        stem = source["participant"]+"-"+source["filename"]+"."+code_sha[:12]
        metadata_path = CACHE / (stem+".json")
        signature = {"source": source, "extractor_code_sha256": code_sha, "quality_policy_code_sha256": policy_sha}
        if metadata_path.exists():
            report = json.loads(metadata_path.read_text())
            if any(report.get(k) != v for k, v in signature.items()):
                raise ValueError("Frozen phone source cache metadata changed")
            for part in report["segments"]:
                path = CACHE / part["file"]
                if digest(path) != part["sha256"]:
                    raise ValueError("Data-only phone cache changed")
                with np.load(path, allow_pickle=False) as data:
                    if data["values"].shape != (len(data["relative_time_ns"]), len(BIN_COLUMNS)) or data["columns"].tolist() != BIN_COLUMNS:
                        raise ValueError("Unexpected unlabelled phone cache schema")
        else:
            raw = pd.read_csv(raw_path, usecols=["time", *PHONE_COLUMNS])
            parts, quality = segments(raw)
            entries = []
            for i, part in enumerate(parts):
                path = CACHE / (stem+f".segment-{i}.npz")
                relative = part.index.as_unit("ns").asi8-EPOCH.value
                np.savez_compressed(path, relative_time_ns=relative, values=part[BIN_COLUMNS].to_numpy(float), columns=np.asarray(BIN_COLUMNS))
                entries.append({"file": path.name, "sha256": digest(path), "observed_bins": len(part), "quality": part.attrs["quality"]})
            report = {**signature, "export_quality": quality, "segments": entries, "f_level_read": False, "native_borg_supervision_rows": 0}
            metadata_path.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        reports.append(report)
        print(f"Fitting phone caches {len(reports)}/32 verified", flush=True)
    evidence = {"version": 1, "receipt_sha256": digest(receipt_path), "inventory_sha256": digest(DIRECTORY / "inventory.json"),
                "extractor_code_sha256": code_sha, "quality_policy_code_sha256": policy_sha,
                "bin_duration_ms": 100, "columns": BIN_COLUMNS, "trace_count": 32, "source_participants": 8,
                "reserved_source_people_used": False, "native_borg_supervision_rows": 0, "f_level_used": False,
                "source_export_rows": sum(r["export_quality"]["original_sample_rows"] for r in reports),
                "identical_consecutive_export_rows": sum(r["export_quality"]["identical_consecutive_export_rows"] for r in reports),
                "clock_reversals": sum(r["export_quality"]["clock_reversals"] for r in reports),
                "observed_bins": sum(p["observed_bins"] for r in reports for p in r["segments"]),
                "files": reports, "gap_interpolation": False,
                "timestamp_policy": "Explicit relative within-file clock in ns. A constant epoch is only an indexing device; no date/timezone or Borg response alignment inferred. Clock reversals split independent segments.",
                "sampling_note": "The source exporter often repeats phone values. Raw exported rows are not claimed to be independent phone updates or additional questionnaire reports. Cache contains observed complete 100 ms bins only."}
    path = DIRECTORY / "phone-bins-provenance.json"
    if path.exists() and json.loads(path.read_text()) != evidence:
        raise ValueError("Preserve the frozen unlabelled bin snapshot before changing preparation")
    path.write_text(json.dumps(evidence, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(f"Prepared unlabelled phone bins: {evidence['observed_bins']} observed bins, {evidence['source_export_rows']} original export rows, zero Borg targets", flush=True)


if __name__ == "__main__":
    prepare()
