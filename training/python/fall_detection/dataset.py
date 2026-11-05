"""Load and audit UniMiB SHAR `full_data.mat` (continuous records, not the pre-windowed files).

Nothing is generated or imputed: a record that cannot be used is excluded and listed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
import scipy.io as sio

from .config import ADL_ACTIVITIES, FALL_ACTIVITIES, SAMPLE_RATE_HZ, STANDARD_GRAVITY

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "training/data/raw/unimib-shar"
ARCHIVE = RAW / "UniMiB-SHAR.zip"
FULL_DATA = RAW / "extracted/UniMiB-SHAR/data/full_data.mat"
SOURCE_URL = "https://www.sal.disco.unimib.it/technologies/unimib-shar/"
ARCHIVE_URL = "https://www.dropbox.com/s/x2fpfqj0bpf8ep6/UniMiB-SHAR.zip"


@dataclass
class Record:
    participant: int        # 0..29, anonymous
    activity: str
    kind: str               # "fall" | "adl"
    trial: int              # 0-based within participant+activity
    segment: int            # contiguous run inside the trial (posture-change trials hold 5 separate repetitions)
    pocket: str             # "right" | "left" (from the dataset readme trial rule)
    xyz_g: np.ndarray       # (n, 3) acceleration including gravity, in g


def _pocket(trial: int, trials: int) -> str:
    # readme: 2 trials -> [right, left]; 6 trials -> first three right, last three left
    if trials == 2:
        return "right" if trial == 0 else "left"
    if trials == 6:
        return "right" if trial < 3 else "left"
    raise ValueError(f"unexpected trial count {trials}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_records() -> tuple[list[Record], dict]:
    """Return usable records and an audit of everything excluded or corrected."""
    full = sio.loadmat(FULL_DATA)["full_data"]
    records: list[Record] = []
    excluded: list[dict] = []
    participants = full.shape[0]
    demographics = []
    splices = 0
    for person in range(participants):
        activities = full[person, 0][0, 0]
        demographics.append({"sex": str(full[person, 1][0]).strip(), "age": int(full[person, 2][0, 0])})
        for activity in activities.dtype.names:
            cell = activities[activity]
            cell = cell[0, 0] if cell.shape == (1, 1) else cell
            trials = list(cell.ravel())
            kind = "fall" if activity in FALL_ACTIVITIES else "adl"
            if activity not in FALL_ACTIVITIES + ADL_ACTIVITIES:
                raise ValueError(f"unknown activity {activity}")
            for trial, raw in enumerate(trials):
                raw = np.asarray(raw, dtype=np.float64)
                if raw.shape[0] != 6:
                    raise ValueError("record must have 6 rows (x, y, z, time ns, time s, magnitude)")
                if np.isnan(raw[:3]).any():
                    # Only the valid prefix would be real data; one trial has NaN to the end of the record.
                    valid = int(np.argmax(np.isnan(raw[:3]).any(axis=0)))
                    excluded.append({"participant": person, "activity": activity, "trial": trial,
                                     "reason": "NaN accelerometer samples", "samples": int(raw.shape[1]),
                                     "valid_prefix_samples": valid})
                    continue
                steps = np.diff(raw[4])
                # Short gaps never occur; the posture-change trials contain ~4 s jumps between repetitions.
                cuts = np.where(np.abs(steps - 1 / SAMPLE_RATE_HZ) > 1e-6)[0] + 1
                if (steps[np.abs(steps - 1 / SAMPLE_RATE_HZ) > 1e-6] < 0.5).any():
                    raise ValueError("unexpected sub-second timestamp irregularity")
                for segment, indices in enumerate(np.split(np.arange(raw.shape[1]), cuts)):
                    records.append(Record(person, activity, kind, trial, segment, _pocket(trial, len(trials)),
                                          raw[:3, indices].T / STANDARD_GRAVITY))
                    if segment:
                        splices += 1
    return records, {"participants": participants, "demographics": demographics, "excluded_records": excluded,
                     "recording_gaps_split": splices}


def summarize(records: list[Record], audit: dict) -> dict:
    groups = {"fall": [r for r in records if r.kind == "fall"], "adl": [r for r in records if r.kind == "adl"]}
    ages = [d["age"] for d in audit["demographics"]]
    return {
        "source": SOURCE_URL, "archive_url": ARCHIVE_URL,
        "archive_sha256": sha256(ARCHIVE) if ARCHIVE.exists() else None,
        "archive_bytes": ARCHIVE.stat().st_size if ARCHIVE.exists() else None,
        "participants": audit["participants"], "age_range": [min(ages), max(ages)],
        "sex_counts": {s: sum(d["sex"] == s for d in audit["demographics"]) for s in sorted({d["sex"] for d in audit["demographics"]})},
        "usable_segments": len(records), "recording_gaps_split": audit["recording_gaps_split"],
        "usable_trials": len({(r.participant, r.activity, r.trial) for r in records}),
        "usable_fall_segments": len(groups["fall"]), "usable_adl_segments": len(groups["adl"]),
        "excluded_records": audit["excluded_records"],
        "segments_per_activity": {a: sum(r.activity == a for r in records) for a in ADL_ACTIVITIES + FALL_ACTIVITIES},
        "total_recorded_minutes": {k: round(sum(len(r.xyz_g) for r in v) / SAMPLE_RATE_HZ / 60, 2) for k, v in groups.items()},
        "units": "m/s^2 in the original files (gravity included, Android device axes); converted to g by /9.80665",
        "sampling": "uniform 50 Hz (20 ms) verified for every usable record",
        "phone_position": "trouser pocket only: right pocket and left pocket trials; no backpack/hand/chest data",
    }


if __name__ == "__main__":
    recs, aud = load_records()
    print(json.dumps(summarize(recs, aud), indent=2, ensure_ascii=False))
