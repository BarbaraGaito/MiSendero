"""Independently rebuild the observed waveform cache from public AVRO bytes."""
from __future__ import annotations

import io
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from fastavro import reader

import fatigue_physiology_pairs as prepared
from public_sources import ROOT, digest, group_key, verify_source_snapshot

REPORT = ROOT / "docs/fatigue-80-2026-10-25/physiology-pair-verification.json"


def decode(archive, members, person):
    """Independent AVRO decoder: no preparation signal/window helpers."""
    chunks = defaultdict(list)
    for member in members:
        for record in reader(io.BytesIO(archive.read(member))):
            if re.search(r"p(\d+)$", record["enrollment"]["participantID"])[1] != person[1:]:
                raise AssertionError("Wrong source participant")
            raw = record["rawData"]
            for channel in ("bvp", "eda", "temperature", "acc_magnitude"):
                entry = raw["accelerometer" if channel == "acc_magnitude" else channel]
                frequency = float(entry["samplingFrequency"])
                start = int(entry["timestampStart"])
                if channel == "acc_magnitude":
                    p = entry["imuParams"]
                    denominator = p["digitalMax"]-p["digitalMin"]
                    if denominator == 0:
                        continue
                    axes = [np.asarray(entry[axis], dtype=float) for axis in ("x", "y", "z")]
                    calibrated = [(axis-p["digitalMin"])/denominator*(p["physicalMax"]-p["physicalMin"])+p["physicalMin"] for axis in axes]
                    values = np.sqrt(sum(axis*axis for axis in calibrated))
                else:
                    values = np.asarray(entry["values"], dtype=float)
                if frequency <= 0 or start == 0 or len(values) == 0:
                    continue
                if not .1 <= frequency <= 2000:
                    raise AssertionError("Source sample frequency changed")
                times = start+np.floor(np.arange(len(values))*1_000_000/frequency).astype(np.int64)
                chunks[channel].append((times, values))
    signals = {}
    for channel in ("bvp", "acc_magnitude", "eda", "temperature"):
        entries = chunks[channel]
        if not entries:
            signals[channel] = np.array([], dtype=np.int64), np.array([], dtype=float)
            continue
        t, v = np.concatenate([x[0] for x in entries]), np.concatenate([x[1] for x in entries])
        order = np.argsort(t, kind="stable")
        t, v = t[order], v[order]
        unique = np.r_[True, np.diff(t) != 0]
        if np.any(~unique & ~np.r_[False, np.isclose(v[1:], v[:-1], equal_nan=True)]):
            raise AssertionError("Conflicting duplicate samples")
        signals[channel] = t[unique], v[unique]
    return signals


def rebuild(signals, proof, row, band, phase):
    rate, channels = prepared.RATES[band]
    width = 1_000_000//rate
    end = row[f"{phase}_time_us"]//width*width
    beginning = end-16_000_000
    lower = max(beginning, row[f"{phase}_lower_bound_us"])
    assert (proof["end_exclusive_us"], proof["window_beginning_us"], proof["effective_lower_bound_us"]) == (end, beginning, lower)
    result = np.zeros((4, 16*rate), dtype=np.float32)
    for j, name in enumerate(channels):
        t, v = signals[name]
        valid = (t >= lower) & (t < end) & np.isfinite(v)
        selected_t, selected_v = t[valid], v[valid]
        for index in range(16*rate):
            selected = (selected_t >= beginning+index*width) & (selected_t < beginning+(index+1)*width)
            if selected.any():
                result[j, index] = selected_v[selected].mean()
                result[j+2, index] = 1
        stats = proof["channels"][name]
        assert stats["actual_samples"] == len(selected_v)
        assert stats["observed_bins"] == int(result[j+2].sum())
        assert stats["earliest_sample_us"] == (int(selected_t[0]) if len(selected_t) else None)
        assert stats["latest_sample_us"] == (int(selected_t[-1]) if len(selected_t) else None)
        if len(selected_t):
            assert selected_t.max() < end <= row[f"{phase}_time_us"]
            assert selected_t.min() >= row[f"{phase}_lower_bound_us"]
    return result


def verify():
    verify_source_snapshot("fatigue")
    arrays, manifest = prepared.load()
    rows = manifest["lineage"]
    expected_rows, cohort = prepared.input_rows()
    assert cohort == manifest["cohort"]
    reports = pd.read_csv(prepared.REPORTS)
    reports["time"] = pd.to_datetime(reports.time, utc=True)
    reports["time_us"] = reports.time.dt.as_unit("ns").astype("int64")//1000
    sessions = json.loads(prepared.SESSIONS.read_text(encoding="utf-8"))
    assert len(rows) == 722 and len(arrays["row_keys"]) == 722
    assert set(arrays) == {"row_keys", "fast_current", "fast_prior", "slow_current", "slow_prior"}
    grouped = defaultdict(list)
    for index, (row, expected) in enumerate(zip(rows, expected_rows, strict=True)):
        assert {key: row[key] for key in expected} == expected
        assert group_key("GeoFatigue:"+row["participant"]) == row["group_key"]
        current = reports[reports.id.eq(row["participant"]) & reports.time_us.eq(row["current_time_us"])]
        assert len(current) == 1
        matching = [s for s in sessions[row["participant"]] if prepared.microseconds(s["start_time"]) <= row["current_time_us"] <= prepared.microseconds(s["end_time"])]
        assert len(matching) == 1
        session = matching[0]
        assert row["prior_lower_bound_us"] == prepared.microseconds(session["start_time"])
        tasks = [t for t in session["tasks"] if prepared.microseconds(t["start_time"]) <= row["current_time_us"] <= prepared.microseconds(t["end_time"])]
        assert len(tasks) == 1 and row["current_lower_bound_us"] == prepared.microseconds(tasks[0]["start_time"])
        eligible = reports[reports.id.eq(row["participant"]) &
            (reports.time_us >= max(row["prior_lower_bound_us"], row["current_time_us"]-900_000_000)) &
            (reports.time_us <= row["current_time_us"]-60_000_000)].sort_values("time_us")
        assert len(eligible) and int(eligible.iloc[-1].time_us) == row["prior_time_us"]
        assert float(eligible.iloc[-1].borg_scale) == row["prior_observed_borg"]
        assert 1 <= row["prior_age_minutes"] <= 15
        grouped[tuple(row["source_prefixes"])].append((index, row))
    checked = 0
    with zipfile.ZipFile(prepared.ARCHIVE) as archive:
        for number, (prefixes, group) in enumerate(sorted(grouped.items()), 1):
            members = sorted(name for name in archive.namelist() if name.endswith(".avro") and any(name.startswith(prefix+"/raw_data/") for prefix in prefixes))
            assert members
            signals = decode(archive, members, group[0][1]["participant"])
            for index, row in group:
                assert row["raw_members"] == members
                for band in prepared.RATES:
                    for phase in ("current", "prior"):
                        name = f"{band}_{phase}"
                        expected = rebuild(signals, row["windows"][name], row, band, phase)
                        # Independent arithmetic order in acceleration may differ at float rounding.
                        np.testing.assert_allclose(arrays[name][index, :2], expected[:2], rtol=2e-7, atol=1e-7)
                        np.testing.assert_array_equal(arrays[name][index, 2:], expected[2:])
                        assert not arrays[name][index, :2][expected[2:] == 0].any()
                        checked += 1
            print(f"Independently rebuilt physiological session {number}/{len(grouped)}", flush=True)
    result = {"version": 1, "verification": "passed", "audit_code_sha256": digest(Path(__file__)),
              "preparation_code_sha256": digest(Path(prepared.__file__)),
              "provenance_sha256": digest(prepared.DIRECTORY/"provenance.json"),
              "windows_sha256": manifest["windows_sha256"], "cohort": cohort,
              "actual_raw_windows_independently_rebuilt": checked, "actual_report_references_verified": len(rows),
              "cross_midnight_sessions_combined": sum(len(prefixes) > 1 for prefixes in grouped),
              "source_sessions": len(grouped), "current_targets_in_tensors": False,
              "new_supervision_rows": 0, "missing_cases_dropped": 0, "interpolated_bins": 0,
              "model_fitting_started": False, "test_predictions_evaluated": False,
              "coverage": manifest["observed_bin_coverage"]}
    REPORT.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result), flush=True)
    return result


if __name__ == "__main__":
    verify()
