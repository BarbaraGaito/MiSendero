"""Inspect an official Borg 6-20 source without converting it to CR10 labels.

This is an eligibility audit only, not a merged training dataset. Different
scales could only be used with a separate auxiliary objective after verifying
actual reports and participant/temporal independence.
"""
import json
from pathlib import Path

import pandas as pd

from fetch_borg_candidates import DIRECTORY as METADATA_DIRECTORY
from fetch_fatigue_extra import download
from public_sources import ROOT, digest

DIRECTORY = ROOT / "training/data/raw/fatigue-research/native-borg6to20-v1"


def main():
    metadata_path = METADATA_DIRECTORY / "native-borg6to20.json"
    source = json.loads(metadata_path.read_text(encoding="utf-8"))
    if source["metadata"]["license"]["id"] != "cc-by-4.0" or source["metadata"]["access_right"] != "open":
        raise ValueError("Unexpected source access/license")
    entry = next(f for f in source["files"] if f["key"] == "Physical_fatigue(in).csv")
    if entry["size"] != 59735 or entry["checksum"] != "md5:44197b8fe1fc14e8811194c71223087d":
        raise ValueError("Source differs from inspected official metadata")
    DIRECTORY.mkdir(exist_ok=True)
    path = download(entry["links"]["self"], DIRECTORY / "Physical_fatigue.csv", maximum_bytes=1_000_000, expected_bytes=entry["size"])
    if digest(path, "md5") != entry["checksum"].split(":", 1)[1]:
        raise ValueError("Published source checksum mismatch")
    frame = pd.read_csv(path)
    observed = pd.to_numeric(frame["Borg_Test"], errors="coerce")
    values = observed.dropna()
    if not values.between(6, 20).all() or not values.eq(values.round()).all():
        raise ValueError("Published native Borg 6-20 cells differ from the inspected scale")
    report = {"source_doi": source["doi"], "metadata_sha256": digest(metadata_path), "csv_sha256": digest(path),
              "published_checksum": entry["checksum"], "rows_in_file": len(frame), "columns": frame.columns.tolist(),
              "nonempty_borg_cells": int(observed.notna().sum()), "missing_borg_cells": int(observed.isna().sum()),
              "participant_id_column_present": False, "timestamp_column_present": False,
              "native_value_counts": {str(int(k)): int(v) for k, v in values.value_counts().sort_index().items()},
              "native_scale": "Borg 6-20 (source metadata)", "cr10_labels_generated": 0, "training_merge_approved": False,
              "note": "Requires proof of actual report times and participant identities before any supervised auxiliary use; never equate these labels with Borg CR10."}
    (DIRECTORY / "audit.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
