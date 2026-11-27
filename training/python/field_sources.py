"""Pinned observations for the scoped prototype; no synthetic targets or rows."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from public_sources import ROOT, RAW, OUTPUT, digest, geofatigue, group_key, verify_source_snapshot

BOOS_SHA = "a4ab34ac465809f0010b1310fda44c497fd4ccf2e7cbf79bc5b8bad0d1b4e11a"
BOOS_URL = "https://journals.plos.org/plosone/article/file?id=10.1371%2Fjournal.pone.0197147.s001&type=supplementary"
FEATURES = {
    "fatigue": ["hr", "prior_borg", "prior_age_minutes", "prior2_borg", "prior2_age_minutes"],
    "ams": ["hr", "spo2", "altitude_m"],
}
SCOPES = {
    "fatigue": "Estimación orientativa Borg 0–10 con autorreporte previo de 1–15 min y un minuto completo de pulso; datos de tareas con carga de GeoFatigue, no validación general de trekking.",
    "ams": "Estimación orientativa de síntomas compatibles con AMS en el próximo control de ascenso, desde un control matinal en reposo; cohorte Boos de trekking en Nepal. No diagnóstico ni predicción continua durante la marcha.",
}


def source_borg_history(reports, sessions, participant, now):
    """Only actual earlier reports in this session; never a current/future answer."""
    matches = [s for s in sessions[participant]
               if pd.Timestamp(s["start_time"]) <= now <= pd.Timestamp(s["end_time"])]
    if len(matches) != 1:
        raise ValueError("Ambiguous fatigue session")
    earlier = reports[(reports["id"] == participant)
                      & (reports["time"] >= pd.Timestamp(matches[0]["start_time"]))
                      & (reports["time"] >= now - pd.Timedelta(minutes=15))
                      & (reports["time"] <= now - pd.Timedelta(minutes=1))].sort_values("time")
    result = {"prior_borg": np.nan, "prior_age_minutes": np.nan,
              "prior2_borg": np.nan, "prior2_age_minutes": np.nan}
    for index, (_, row) in enumerate(earlier.iloc[::-1].head(2).iterrows()):
        prefix = "prior" if index == 0 else "prior2"
        result[prefix + "_borg"] = float(row["borg_scale"])
        result[prefix + "_age_minutes"] = (now - row["time"]).total_seconds() / 60
    return result


def fatigue_dataset():
    verify_source_snapshot("fatigue")
    frame, source = geofatigue()
    reports = pd.read_csv(RAW / "geofatigue/self_reported_fatigue_level.original.tab")
    reports["time"] = pd.to_datetime(reports["time"], utc=True)
    if reports.duplicated(["id", "time"]).any():
        raise ValueError("Ambiguous original Borg responses")
    sessions = json.loads((RAW / "geofatigue/session_metadata.json").read_text(encoding="utf-8"))
    rows = []
    for _, row in frame.iterrows():
        participant = "p" + re.search(r"/p(\d+)-", row["lineage"]["member"])[1]
        now = pd.Timestamp(row["lineage"]["label_time"])
        history = source_borg_history(reports, sessions, participant, now)
        if not np.isfinite(history["prior_borg"]):
            raise ValueError("Canonical observation lacks the required real previous Borg")
        rows.append({"hr": row["hr"], **history, "label": row["label"],
                     "person": row["group_key"], "split_group": row["group_key"],
                     "row_key": row["row_key"]})
    result = pd.DataFrame(rows)
    historical = json.loads((OUTPUT / "fatigue/metrics.json").read_text(encoding="utf-8"))["evaluation_protocol"]
    if set(result.row_key) != set(historical["train_row_keys"] + historical["test_row_keys"]):
        raise ValueError("Historical fatigue denominator or identities changed")
    result["partition"] = np.where(result.row_key.isin(historical["test_row_keys"]), "test", "train")
    return result, {"source": source, "raw_sha256": source["raw_files"],
                    "historical_test_reused": True, "synthetic_rows": 0,
                    "pulse_window": "last completed measured minute ending at/before the response, within the previous two minutes"}


def number(value):
    try:
        result = float(value.strip())
        return result if np.isfinite(result) else None
    except (ValueError, AttributeError):
        return None


def boos_dataset(raw):
    if hashlib.sha256(raw).hexdigest() != BOOS_SHA:
        raise ValueError("Boos public snapshot changed; audit a new version explicitly")
    data = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    expected = {0: "subject no", 1: "Altitude", 2: "Trek Team", 6: "altitude",
                21: "heart rate", 22: "SPO2", 25: "LLS", 26: "HEADACHE", 40: "AMS AT NEXT ALTITUDE"}
    if any(data[0][index].strip() != name for index, name in expected.items()):
        raise ValueError("Positional source schema changed; duplicate column names must not be collapsed")
    visits = [row for row in data[1:] if number(row[0]) is not None and number(row[1]) is not None]
    keys = Counter((number(r[0]), number(r[1])) for r in visits)
    lookup = {(number(r[0]), number(r[1])): r for r in visits if keys[number(r[0]), number(r[1])] == 1}
    audit = {"raw_person_visit_rows": len(visits), "participants": len({r[0] for r in visits}),
             "ambiguous_keys": sum(count > 1 for count in keys.values()),
             "exclusions": Counter(), "published_future_comparisons": 0,
             "published_future_disagreements": 0}
    rows = []
    for row in visits:
        key = (number(row[0]), number(row[1]))
        next_key = (key[0], key[1] + 1)
        if keys[key] != 1 or keys.get(next_key, 0) > 1:
            audit["exclusions"]["ambiguous_identity"] += 1
            continue
        following = lookup.get(next_key)
        if following is None:
            audit["exclusions"]["no_next_visit"] += 1
            continue
        if number(row[40]) is not None and number(following[36]) is not None:
            audit["published_future_comparisons"] += 1
            audit["published_future_disagreements"] += int(number(row[40]) != number(following[36]))
        values = [number(row[i]) for i in (21, 22, 6)]
        future_altitude, score, headache = (number(following[i]) for i in (6, 25, 26))
        if any(v is None for v in [*values, future_altitude, score, headache]):
            audit["exclusions"]["missing_measured_value_or_outcome"] += 1
            continue
        hr, spo2, altitude = values
        # Define a high-altitude ascending-stage task, not symptoms at low altitude.
        if future_altitude < 2500 or future_altitude <= altitude:
            audit["exclusions"]["outside_ascending_high_altitude_task"] += 1
            continue
        if not (30 <= hr <= 240 and 50 <= spo2 <= 100 and 0 <= score <= 15 and 0 <= headache <= 3):
            raise ValueError("Source observation outside its declared units")
        # Published LLS criterion applied to independently observed NEXT symptoms.
        # No HR/SpO2-derived labels, and no ambiguous precomputed future column.
        label = "AMS+" if score >= 3 and headache > 0 else "AMS-"
        rows.append({"hr": hr, "spo2": spo2, "altitude_m": altitude, "label": label,
                     "person": group_key(f"Boos:{key[0]}"), "split_group": group_key("Boos-team:" + row[2]),
                     "row_key": group_key(f"Boos:{key[0]}:{key[1]}"),
                     "future_score": score, "future_headache": headache,
                     "source_visit": key[1], "outcome_visit": next_key[1]})
    frame = pd.DataFrame(rows)
    if frame.empty or frame.row_key.duplicated().any() or (frame.groupby("person").split_group.nunique() > 1).any():
        raise ValueError("Ambiguous participant, team or observation")
    return frame, {"source": BOOS_URL, "sha256": BOOS_SHA, "license": "CC BY (PLOS article and supplement)",
                    "outcome": "next observed visit LLS >=3 with headache >0; questionnaire criterion, not independent physician diagnosis",
                    "synthetic_rows": 0, "audit": audit, "historical_test_reused": False}


def load_boos():
    destination = ROOT / "training/data/raw/field-ai/boos-2018.csv"
    cache = ROOT / "training/data/raw/fatigue-research/dataset-search-2026-11-27-v1/boos-trekking-2018.csv"
    if destination.exists():
        raw = destination.read_bytes()
    elif cache.exists():
        raw = cache.read_bytes()
    else:
        with urlopen(Request(BOOS_URL, headers={"User-Agent": "MiSendero-public-source-audit/1.0"}), timeout=30) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Public supplement exceeds its bounded download")
    if hashlib.sha256(raw).hexdigest() != BOOS_SHA:
        raise ValueError("Boos checksum mismatch")
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    return boos_dataset(raw)
