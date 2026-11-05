"""Checksum one small fitting-person CSV before considering source transfer."""
from __future__ import annotations

import csv
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from fetch_runner_fatigue_metadata import DIRECTORY
from public_sources import digest


def inspect():
    inventory_path = DIRECTORY / "inventory.json"
    inventory = json.loads(inventory_path.read_text())
    records = [f for f in inventory["files"] if f["participant"] in inventory["fit_participants"]
               and f["protocol_segment"] in ("F", "NF")]
    record = min(records, key=lambda f: (f["bytes"], f["filename"]))
    if record["bytes"] > 2_000_000 or not record["url"].startswith("https://zenodo.org/"):
        raise ValueError("Inspect an unexpected probe size or public host")
    folder = DIRECTORY / "schema-probe"
    folder.mkdir(exist_ok=True)
    path = folder / record["filename"]
    if not path.exists():
        request = urllib.request.Request(record["url"], headers={"User-Agent": "MiSendero public signal schema audit"})
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = response.read(record["bytes"]+1)
        if len(payload) != record["bytes"] or "md5:"+hashlib.md5(payload).hexdigest() != record["published_checksum"]:
            raise ValueError("Public CSV size or checksum differs from Zenodo")
        path.write_bytes(payload)
    payload = path.read_bytes()
    if len(payload) != record["bytes"] or "md5:"+hashlib.md5(payload).hexdigest() != record["published_checksum"]:
        raise ValueError("Previously downloaded schema probe changed")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        first_rows = [next(reader) for _ in range(4)]
    frame = pd.read_csv(path)
    clocks = {}
    for column in ("System_Timestamp_Plot_Zeroed", "Timestamp", "System_Timestamp_Plot", "System_Timestamp"):
        value = pd.to_numeric(frame[column], errors="coerce").to_numpy(float)
        step = np.diff(value)
        positive = step[np.isfinite(step) & (step > 0)]
        clocks[column] = {"finite_rows": int(np.isfinite(value).sum()),
            "positive_steps": len(positive), "equal_adjacent_steps": int((step == 0).sum()),
            "reverse_steps": int((step < 0).sum()),
            "positive_step_median_native_units": float(np.median(positive)) if len(positive) else None,
            "positive_step_min_native_units": float(positive.min()) if len(positive) else None,
            "positive_step_max_native_units": float(positive.max()) if len(positive) else None}
    receipt_path = DIRECTORY / "schema-probe.json"
    inspected_at = json.loads(receipt_path.read_text())["inspected_at"] if receipt_path.exists() else datetime.now(timezone.utc).isoformat()
    result = {"version": 1, "inspected_at": inspected_at,
        "inspection_code_sha256": digest(Path(__file__)),
        "inventory_sha256": digest(inventory_path), "source_record": record,
        "csv_sha256": digest(path), "local_path": str(path), "first_four_csv_rows": first_rows,
        "observed_rows": len(frame), "observed_columns": frame.columns.tolist(), "clock_diagnostics": clocks,
        "reserved_people_downloaded": False, "used_for_training": False,
        "new_native_borg_targets": 0,
        "note": "This is one fitting-person schema probe, not a prepared training dataset. Protocol F/NF labels are not Borg scores. Verify units, actual clocks and missing-data semantics before transferring signal representations."}
    receipt_path.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    inspect()
