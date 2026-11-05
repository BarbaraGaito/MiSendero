"""Evaluate end-of-hike Borg RPE from earlier checkpoint heart rate.

Real, public hiking data are downloaded into memory. The source workbook is not
saved because it contains demographic details unnecessary for this benchmark.
This is not an evaluation of fatigue or a real-time fatigue alert.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path

import numpy as np
import openpyxl
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/fatigue-trekking-evaluation-2026-10-22/hardmin-hiking-results.json"
SOURCE_URL = ("https://hardmin.heal-link.gr/dataset/e07a237f-9f16-4977-a181-ee6d0d1a3f22/"
              "resource/bfe8ca78-2615-4260-8e6a-1794a167af10/download/rmf_hiking_poles.xlsx")
SOURCE_SHA256 = "4f4d4139a8e6da30d5e071317b9afc000f2234f73714add69e885ef2f3bc828e"
SUBJECT = re.compile(r"Subject ([1-9][0-9]*)\Z")


def workbook() -> openpyxl.Workbook:
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "MiSendero-thesis-audit/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError(f"HARDMIN source changed: {digest}")
    return openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)


def subject_rows(sheet: openpyxl.worksheet.worksheet.Worksheet) -> dict[str, tuple]:
    rows = {}
    for row in list(sheet.iter_rows(values_only=True))[1:]:
        match = SUBJECT.fullmatch(str(row[0]).strip()) if row[0] is not None else None
        if not match:
            continue
        person = match.group(1)
        if person in rows:
            raise ValueError(f"Duplicate subject in {sheet.title}")
        rows[person] = row
    return rows


def get_observations(book: openpyxl.Workbook) -> list[dict]:
    observations = []
    for condition in ("np", "wp"):
        hr = subject_rows(book[f"HR-{condition}"])
        outcome = subject_rows(book[f"2070-{condition}"])
        if set(hr) != set(outcome) or set(hr) != {str(n) for n in range(1, 18)}:
            raise ValueError(f"Unexpected participants in condition {condition}")
        for person in sorted(hr, key=int):
            # 1060 m baseline and three checkpoints precede the 2070 m finish.
            values = hr[person][1:5]
            if not all(isinstance(value, (int, float)) and 30 <= value <= 240 for value in values):
                raise ValueError(f"Missing or invalid checkpoint heart rate: {person}/{condition}")
            raw_rpe = outcome[person][12]
            if str(raw_rpe).strip() not in {str(n) for n in range(6, 21)}:
                raise ValueError(f"Missing or invalid Borg 6-20 RPE: {person}/{condition}")
            observations.append({"person": person, "condition": condition,
                                 "hr": [float(value) for value in values], "rpe": int(raw_rpe)})
    return sorted(observations, key=lambda row: (int(row["person"]), row["condition"]))


def scores(y: np.ndarray, prediction: np.ndarray) -> dict:
    error = np.abs(y - prediction)
    return {"observations": len(y), "exact_accuracy": float(np.mean(error == 0)),
            "within_one_accuracy": float(np.mean(error <= 1)),
            "mae_borg_6_20_points": float(np.mean(error)),
            "errors_three_or_more": int(np.sum(error >= 3))}


def bootstrap(predictions: list[dict], repetitions: int = 10000) -> dict:
    by_person = {person: [row for row in predictions if row["person"] == person]
                 for person in sorted({row["person"] for row in predictions}, key=int)}
    people = list(by_person)
    rng = np.random.default_rng(42)
    differences = []
    for _ in range(repetitions):
        sample = [row for person in rng.choice(people, size=len(people), replace=True)
                  for row in by_person[person]]
        differences.append(float(np.mean([abs(row["predicted"] - row["observed"])
                                          - abs(row["baseline"] - row["observed"])
                                          for row in sample])))
    return {"unit": "participant", "resamples": repetitions, "seed": 42,
            "mae_model_minus_baseline_95pct": [float(v) for v in np.quantile(differences, [.025, .975])]}


def evaluate(observations: list[dict]) -> dict:
    people = sorted({row["person"] for row in observations}, key=int)
    x = np.array([row["hr"] for row in observations], dtype=float)
    y = np.array([row["rpe"] for row in observations], dtype=int)
    predicted = np.zeros(len(y), dtype=int)
    baseline = np.zeros(len(y), dtype=int)
    for person in people:
        train = np.array([row["person"] != person for row in observations])
        test = ~train
        model = make_pipeline(StandardScaler(), Ridge(alpha=10.0))
        model.fit(x[train], y[train])
        predicted[test] = np.clip(np.rint(model.predict(x[test])), 6, 20).astype(int)
        counts = Counter(y[train])
        most_common = min(counts, key=lambda rating: (-counts[rating], rating))
        baseline[test] = most_common
    rows = [{"person": row["person"], "condition": row["condition"],
             "observed": int(y[i]), "predicted": int(predicted[i]), "baseline": int(baseline[i])}
            for i, row in enumerate(observations)]
    return {"source": "https://doi.org/10.26255/heal.mjhj-gsm4",
            "source_article": "https://doi.org/10.3390/app16031593",
            "source_license": "CC-BY-SA-4.0 (HARDMIN public catalog)",
            "source_file_sha256": SOURCE_SHA256,
            "task": "End-of-hike Borg RPE 6-20 predicted from heart rate at trailhead and three earlier checkpoints",
            "design": "Same 6.4 km uphill trail, each of 17 people with/without poles; leave-one-person-out, both visits held out together",
            "features": ["HR at 1060 m", "HR checkpoint 1", "HR checkpoint 2", "HR checkpoint 3"],
            "model": "StandardScaler + Ridge(alpha=10), fixed before evaluation, rounded to original scale",
            "limitations": "Endpoint exertion, not fatigue; no label during the hike; one route; small group; does not evaluate existing GeoFatigue model",
            "people": len(people), "visits": len(observations),
            "label_counts": dict(sorted(Counter(y.tolist()).items())),
            "model_scores": scores(y, predicted), "training_mode_baseline": scores(y, baseline),
            "uncertainty": bootstrap(rows), "predictions": rows}


def respiratory_measure_audit(book: openpyxl.Workbook, observations: list[dict]) -> dict:
    """Describe measured MVV12 change; never relabel it as overall fatigue."""
    before = {condition: subject_rows(book[f"1060-{condition}"]) for condition in ("np", "wp")}
    after = {condition: subject_rows(book[f"2070-{condition}"]) for condition in ("np", "wp")}
    values = []
    for row in observations:
        person, condition = row["person"], row["condition"]
        start, finish = before[condition][person][11], after[condition][person][11]
        if not isinstance(start, (int, float)) or not isinstance(finish, (int, float)) or start <= 0:
            raise ValueError(f"Invalid measured MVV12 pair: {person}/{condition}")
        values.append(100 * (finish - start) / start)
    y = np.array(values)
    x = np.array([row["hr"] for row in observations])
    prediction = np.zeros(len(y))
    baseline = np.zeros(len(y))
    for person in sorted({row["person"] for row in observations}, key=int):
        train = np.array([row["person"] != person for row in observations])
        test = ~train
        model = make_pipeline(StandardScaler(), Ridge(alpha=10.0))
        model.fit(x[train], y[train])
        prediction[test] = model.predict(x[test])
        baseline[test] = np.mean(y[train])
    return {"measure": "MVV12 percentage change from measured 1060 m baseline to post-hike 2070 m; not a fatigue diagnosis",
            "visits": len(y), "median_change_percent": float(np.median(y)),
            "range_change_percent": [float(np.min(y)), float(np.max(y))],
            "observed_declines": int(np.sum(y < 0)), "observed_increases": int(np.sum(y > 0)),
            "exploratory_model_mae_percentage_points": float(np.mean(np.abs(y - prediction))),
            "training_mean_baseline_mae_percentage_points": float(np.mean(np.abs(y - baseline))),
            "interpretation": "No prespecified validated threshold or sufficient confirmed fatigue cases; cannot score fatigue detection."}


def main() -> None:
    book = workbook()
    try:
        observations = get_observations(book)
        result = evaluate(observations)
        result["respiratory_measure_audit"] = respiratory_measure_audit(book, observations)
    finally:
        book.close()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("people", "visits", "model_scores", "training_mode_baseline", "uncertainty")}, indent=2))


if __name__ == "__main__":
    main()
