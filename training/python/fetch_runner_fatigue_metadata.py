"""Inventory a public runner IMU source without treating F/NF as Borg."""
from __future__ import annotations

import json
import re
import urllib.request

import numpy as np
from sklearn.model_selection import GroupShuffleSplit

from public_sources import RAW, digest

DIRECTORY = RAW / "runners-fatigue-v1"
URL = "https://zenodo.org/api/records/11114096"


def inventory():
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "record-11114096.json"
    if not path.exists():
        request = urllib.request.Request(URL, headers={"User-Agent": "MiSendero public fatigue data audit", "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = response.read(2_000_001)
        if len(payload) > 2_000_000 or str(json.loads(payload).get("id")) != "11114096":
            raise ValueError("Unexpected or oversized public metadata response")
        path.write_bytes(payload)
    record = json.loads(path.read_text())
    files, people = [], set()
    for entry in record["files"]:
        matched = re.fullmatch(r"(\d{3})_(F|NF|BeepTest)\.csv", entry["key"])
        if not matched or not re.fullmatch(r"md5:[0-9a-f]{32}", entry["checksum"]):
            raise ValueError("Inspect changed filenames or checksum schema before use")
        people.add(matched[1])
        files.append({"filename": entry["key"], "participant": matched[1], "protocol_segment": matched[2],
                      "bytes": entry["size"], "published_checksum": entry["checksum"], "url": entry["links"]["self"]})
    people = np.asarray(sorted(people))
    if len(people) != 19 or len(files) != 57:
        raise ValueError("Inspect a changed original runner cohort")
    fitting, held = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=42).split(people, groups=people))
    result = {"version": 1, "record_id": 11114096, "record_url": URL, "record_sha256": digest(path),
        "title": record["metadata"]["title"], "license": record["metadata"].get("license"),
        "participants": len(people), "fit_participants": people[fitting].tolist(), "reserved_participants": people[held].tolist(),
        "files": files, "total_published_bytes": sum(f["bytes"] for f in files),
        "waveforms_downloaded": False, "used_for_training": False, "new_native_borg_targets": 0,
        "label_interpretation": "F/NF designate protocol-defined fatigued/nonfatigued running segments, not native Borg scores. BeepTest is a separate induction segment. No numeric Borg values may be inferred from these filenames.",
        "potential_use": "Separate source-only representation learning, subject to signal-unit and schema inspection. No native Borg target merge, and no reserved runner participants in population fitting."}
    output = DIRECTORY / "inventory.json"
    if output.exists() and json.loads(output.read_text()) != result:
        raise ValueError("Preserve the earlier source inventory before any version change")
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "files"}, indent=2))
    return result


if __name__ == "__main__":
    inventory()
