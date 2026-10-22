"""Evaluate WHAMAP's native session labels with phone-only signals.

This is a research audit of the original WHAMAP protocol, not a validation of
fatigue detection during trekking. The first 2 MiB of every original CSV are
read from Mendeley without saving raw observations in the project tree.
"""

from __future__ import annotations

import hashlib
import io
import json
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/fatigue-trekking-evaluation-2026-10-22/whamap-phone-results.json"
BASE = "https://data.mendeley.com/public-api/datasets/8zt9g9g64c/"
HEADERS = {"Accept": "application/vnd.mendeley-public-dataset.1+json", "User-Agent": "MiSendero-thesis-audit/1.0"}
PHONE_COLUMNS = [f"phone_{sensor}{axis}" for sensor in ("accel", "gyro") for axis in "XYZ"]
PREFIX_BYTES = 2 * 1024 * 1024


def read_json(url: str) -> object:
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=45) as response:
        return json.load(response)


def files() -> list[tuple[str, dict]]:
    folders = read_json(BASE + "folders/1")
    selected = []
    for folder in folders:
        if not folder["name"].startswith("subject_"):
            continue
        url = BASE + f"files?folder_id={folder['id']}&version=1&%24start=0&%24limit=1000"
        for item in read_json(url):
            if item["filename"] in {"walking.csv", "walking_B.csv", "uphill.csv", "uphill_B.csv"}:
                selected.append((folder["name"], item))
    if len(selected) != 40 or len({subject for subject, _ in selected}) != 10:
        raise ValueError("Expected four walking/uphill files for each of ten participants")
    return sorted(selected, key=lambda pair: (pair[0], pair[1]["filename"]))


def features(subject: str, item: dict) -> dict:
    details = item["content_details"]
    url = details["download_url"]
    request = urllib.request.Request(url, headers={**HEADERS, "Range": f"bytes=0-{PREFIX_BYTES - 1}"})
    with urllib.request.urlopen(request, timeout=45) as response:
        if response.status != 206 or response.headers.get("Content-Range", "").split("/")[-1] != str(details["size"]):
            raise ValueError(f"Missing partial-content response: {subject}/{item['filename']}")
        raw = response.read()
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) != PREFIX_BYTES:
        raise ValueError(f"Unexpected prefix size: {subject}/{item['filename']}")
    raw = raw[:raw.rfind(b"\n") + 1]
    cols = ["user-id", "activity_type", "f-level", *PHONE_COLUMNS]
    frame = pd.read_csv(io.BytesIO(raw), usecols=cols, dtype={"user-id": str})
    if frame.empty or frame["user-id"].nunique() != 1 or frame["user-id"].iloc[0].zfill(2) != subject[-2:]:
        raise ValueError(f"Participant mismatch: {subject}/{item['filename']}")
    activity = item["filename"].split("_")[0].split(".")[0]
    if frame["activity_type"].nunique() != 1 or frame["activity_type"].iloc[0] != activity:
        raise ValueError(f"Activity mismatch: {subject}/{item['filename']}")
    if frame["f-level"].nunique() != 1:
        raise ValueError(f"Fatigue label varies within recording: {subject}/{item['filename']}")
    label = int(frame["f-level"].iloc[0])
    if label not in range(5):
        raise ValueError(f"Unexpected native label: {label}")
    signals = frame[PHONE_COLUMNS].to_numpy(dtype=np.float64)
    valid = np.isfinite(signals).all(axis=1)
    if int(valid.sum()) < 500:
        return {"participant": subject, "recording": item["filename"], "f_level": label,
                "total_samples": len(frame), "valid_samples": int(valid.sum()),
                "exclusion": "fewer than 500 complete phone samples in the prefix"}
    signals = signals[valid]
    accel = np.linalg.norm(signals[:, :3], axis=1)
    gyro = np.linalg.norm(signals[:, 3:], axis=1)
    values = []
    for magnitude in (accel, gyro):
        values.extend([float(np.mean(magnitude)), float(np.std(magnitude)),
                       float(np.quantile(magnitude, 0.5)), float(np.quantile(magnitude, 0.9))])
    return {"participant": subject, "recording": item["filename"], "activity": activity,
            "block": "second" if "_B" in item["filename"] else "first",
            "f_level": label, "total_samples": len(frame), "valid_samples": int(valid.sum()),
            "source_sha256": details["sha256_hash"],
            "downloaded_prefix_sha256": digest, "features": values}


def metrics(rows: list[dict], predictions: list[int], truth_key: str = "f_level") -> dict:
    y = np.array([row[truth_key] for row in rows], dtype=int)
    p = np.array(predictions, dtype=int)
    if len(y) != len(p):
        raise ValueError("Prediction count mismatch")
    return {"recordings": len(y), "exact_accuracy": float(np.mean(y == p)),
            "within_one_accuracy": float(np.mean(np.abs(y - p) <= 1)),
            "mae_native_level": float(np.mean(np.abs(y - p)))}


def evaluate(rows: list[dict]) -> dict:
    people = sorted({row["participant"] for row in rows})
    y = np.array([row["f_level"] for row in rows], dtype=int)
    x = np.array([row["features"] for row in rows], dtype=float)
    phone_pred = np.zeros(len(rows), dtype=int)
    majority_pred = np.zeros(len(rows), dtype=int)
    protocol_pred = np.zeros(len(rows), dtype=int)
    for person in people:
        train = np.array([row["participant"] != person for row in rows])
        test = ~train
        model = make_pipeline(StandardScaler(), Ridge(alpha=10.0))
        model.fit(x[train], y[train])
        phone_pred[test] = np.clip(np.rint(model.predict(x[test])), 0, 4).astype(int)
        counts = Counter(y[train])
        majority = min(counts, key=lambda level: (-counts[level], level))
        majority_pred[test] = majority
        for index in np.flatnonzero(test):
            match = [j for j, row in enumerate(rows) if train[j]
                     and row["activity"] == rows[index]["activity"]
                     and row["block"] == rows[index]["block"]]
            group_counts = Counter(y[match])
            protocol_pred[index] = min(group_counts, key=lambda level: (-group_counts[level], level))
    out = {"phone_ridge": metrics(rows, phone_pred.tolist()),
           "majority_baseline": metrics(rows, majority_pred.tolist()),
           "activity_block_baseline": metrics(rows, protocol_pred.tolist()),
           "by_activity": {activity: {
               name: metrics([rows[i] for i in ids], predictions[ids].tolist())
               for name, predictions in (("phone_ridge", phone_pred), ("majority_baseline", majority_pred),
                                         ("activity_block_baseline", protocol_pred))}
               for activity in ("walking", "uphill")
               for ids in [[i for i, row in enumerate(rows) if row["activity"] == activity]]},
           "predictions": [{"participant": row["participant"], "recording": row["recording"],
                            "observed": row["f_level"], "phone_ridge": int(phone_pred[i]),
                            "majority_baseline": int(majority_pred[i]),
                            "activity_block_baseline": int(protocol_pred[i])}
                           for i, row in enumerate(rows)]}
    return out


def participant_bootstrap(predictions: list[dict], replicates: int = 10_000) -> dict:
    people = sorted({row["participant"] for row in predictions})
    by_person = {person: [row for row in predictions if row["participant"] == person] for person in people}
    rng = np.random.default_rng(42)
    accuracy_differences = []
    mae_differences = []
    for _ in range(replicates):
        sample = [row for person in rng.choice(people, size=len(people), replace=True)
                  for row in by_person[person]]
        accuracy_differences.append(float(np.mean([
            (row["phone_ridge"] == row["observed"])
            - (row["activity_block_baseline"] == row["observed"])
            for row in sample])))
        mae_differences.append(float(np.mean([
            abs(row["phone_ridge"] - row["observed"])
            - abs(row["activity_block_baseline"] - row["observed"])
            for row in sample])))
    return {"resamples": replicates, "unit": "participant", "seed": 42,
            "phone_minus_protocol_exact_accuracy_95pct": [float(v) for v in np.quantile(accuracy_differences, [.025, .975])],
            "phone_minus_protocol_mae_95pct": [float(v) for v in np.quantile(mae_differences, [.025, .975])]}


def main() -> None:
    rows = []
    excluded = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(features, subject, item): (subject, item["filename"])
                   for subject, item in files()}
        for future in as_completed(futures):
            row = future.result()
            if "exclusion" in row:
                excluded.append(row)
                print(f"EXCLUDED {row['participant']}/{row['recording']}: {row['valid_samples']} complete phone samples", flush=True)
            else:
                rows.append(row)
                print(f"{row['participant']}/{row['recording']}: level {row['f_level']}, {row['valid_samples']}/{row['total_samples']} complete phone samples", flush=True)
    rows.sort(key=lambda row: (row["participant"], row["recording"]))
    if len({row["participant"] for row in rows}) < 5 or len(rows) < 20:
        raise ValueError("Insufficient distinct participants/recordings with complete phone signals")
    results = evaluate(rows)
    report = {"source": "https://doi.org/10.17632/8zt9g9g64c.1", "source_version": 1,
              "scope": "Native WHAMAP f-level per recording; first 2 MiB (approximately initial 30-40 seconds) of each controlled walking/uphill trace; phone-only input; no trekking accuracy claim",
              "validation": "Leave-one-participant-out; four complete recordings kept together per person",
              "model": "StandardScaler + Ridge(alpha=10); fixed before scoring, rounded to native level 0-4",
              "feature_definition": "For phone acceleration and gyroscope vector magnitudes: mean, standard deviation, median, 90th percentile over the downloaded prefix",
              "source_integrity": "HTTP 206 and Content-Range total checked against repository size; source full-file SHA-256 listed but not independently verified in this evaluation",
              "labels_are_constant_in_downloaded_prefix": True,
              "sample_counts_are_sensor_rows_not_independent_fatigue_labels": True,
              "label_counts": dict(sorted(Counter(row["f_level"] for row in rows).items())),
              "excluded_recordings": excluded,
              "records": [{k: v for k, v in row.items() if k != "features"} for row in rows],
              "participant_bootstrap": participant_bootstrap(results["predictions"]),
              **results}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("phone_ridge", "majority_baseline", "activity_block_baseline")}, indent=2))


if __name__ == "__main__":
    main()
