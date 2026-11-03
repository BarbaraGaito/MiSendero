"""Verify original SPE cells; explicitly reject unidentified HR/SPE joins."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

import walking_spe_transitions as prepared
from fatigue_dynamics import load_inputs as native_inputs
from public_sources import RAW, ROOT, digest, group_key, verify_source_snapshot


def original_table(archive, name):
    payload = archive.read(name)
    # Independent text parser; do not reuse numpy.loadtxt or the preparer.
    rows = [[float(cell) for cell in line.split()] for line in payload.decode("utf-8").splitlines() if line.strip()]
    assert rows and all(len(row) == 4 for row in rows)
    return rows, hashlib.sha256(payload).hexdigest()


def verify():
    frame, manifest = prepared.load()
    raw = prepared.source.DIRECTORY
    inventory = json.loads((raw/"inventory.json").read_text())
    receipt = json.loads((raw/"archive-receipt.json").read_text())
    assert inventory["code_sha256"] == digest(Path(prepared.source.__file__))
    assert receipt["code_sha256"] == digest(Path(__file__).with_name("fetch_walking_spe_archive.py"))
    assert receipt["inventory_sha256"] == digest(raw/"inventory.json")
    assert receipt["sha256"] == receipt["published_sha256"] == digest(raw/"All_data.zip")
    assert receipt["bytes"] == (raw/"All_data.zip").stat().st_size == 46442
    for entry in inventory["metadata"]:
        assert digest(raw/entry["path"]) == entry["sha256"]
    source, _ = json.JSONDecoder().raw_decode((raw/"page.html").read_text().split("window.INITIAL_STATE = ", 1)[1])
    snapshot = source["dataset"]["snapshot"]
    assert snapshot["version"] == 1 and not snapshot["is_confidential"] and snapshot["licence"]["short_name"] == "CC BY 4.0"
    assert "5, 10, 15, and 20 min" in snapshot["method"] and "0 to 10" in snapshot["method"]
    assert len(frame) == 156 and frame.row_key.is_unique and frame.group_key.nunique() == 1 and frame.sequence_key.nunique() == 52
    assert set(frame) == {"source_domain", "row_key", "prior_row_key", "group_key", "sequence_key", "source_condition", "nominal_elapsed_minutes", "nominal_prior_age_minutes", "prior_spe", "prior2_spe", "spe_native"}
    keyed = frame.set_index("row_key")
    lineage = {row["row_key"]: row for row in manifest["lineage"]}
    seen, conditions = [], {}
    with zipfile.ZipFile(raw/"All_data.zip") as archive:
        assert len(archive.infolist()) == 142
        for condition in prepared.CONDITIONS:
            spe, spe_sha = original_table(archive, f"SPE_{condition}.txt")
            hr, hr_sha = original_table(archive, f"HR_{condition}.txt")
            assert len(spe) == 13 and len(hr) == 12
            assert manifest["members"][f"SPE_{condition}.txt"]["sha256"] == spe_sha
            assert manifest["members"][f"HR_{condition}.txt"]["sha256"] == hr_sha
            for source_row, values in enumerate(spe):
                assert all(np.isfinite(values)) and all(0 <= v <= 10 for v in values)
                for column in (1, 2, 3):
                    member = f"SPE_{condition}.txt"
                    key = group_key(f"Walking-SPE-original-cell:{member}:{source_row}:{column}")
                    prior = group_key(f"Walking-SPE-original-cell:{member}:{source_row}:{column-1}")
                    actual, evidence = keyed.loc[key], lineage[key]
                    assert actual.spe_native == values[column] and actual.prior_spe == values[column-1]
                    assert actual.prior_row_key == prior and actual.source_condition == condition and actual.source_domain == "walking_spe"
                    if column >= 2:
                        assert actual.prior2_spe == values[column-2]
                    else:
                        assert pd.isna(actual.prior2_spe)
                    assert actual.sequence_key == group_key(f"Walking-SPE-table-sequence:{member}:{source_row}")
                    assert actual.group_key == group_key("Walking-SPE-mn3xyg2gh6-entire-source-cohort")
                    assert actual.nominal_elapsed_minutes == 5*(column+1) and actual.nominal_prior_age_minutes == 5
                    assert evidence["member"] == member and evidence["member_sha256"] == spe_sha
                    assert evidence["source_row_zero_based"] == source_row and evidence["current_column_zero_based"] == column
                    assert evidence["actual_current_spe"] == values[column] and evidence["actual_prior_spe"] == values[column-1]
                    assert not evidence["hr_row_join_performed"] and not evidence["wall_clock_report_timestamp_invented"]
                    seen.append(key)
            conditions[condition] = {"original_spe_rows": len(spe), "original_hr_rows": len(hr), "original_columns_each": 4,
                "original_spe_cells": 4*len(spe), "actual_targets_with_prior": 3*len(spe),
                "spe_range": [float(np.min(spe)), float(np.max(spe))], "hr_spe_positional_join_allowed": False}
    assert sorted(seen) == sorted(frame.row_key)
    assert manifest["synthetic_rows"] == manifest["interpolated_targets"] == manifest["assumed_onset_zeros"] == manifest["new_native_borg_targets"] == 0
    assert manifest["unique_source_participant_count_asserted"] is None and not manifest["source_person_disjoint_validation_claimed"]
    assert not manifest["sensor_outcome_join_approved"] and not manifest["native_borg_target_merge_approved"] and not manifest["model_fitting_started"]
    verify_source_snapshot("fatigue")
    native, train, test, native_manifest, _ = native_inputs()
    reports = pd.read_csv(RAW/"geofatigue/self_reported_fatigue_level.original.tab")
    metadata = json.loads((RAW/"geofatigue/session_metadata.json").read_text())
    all_people = set(reports.id)
    outside = [person for person in all_people if group_key("GeoFatigue:"+person) not in set(native.group_key)]
    assert len(all_people) == len(metadata) == native.group_key.nunique() == 40 and not outside
    assert len(native) == 666 and len(train) == 487 and len(test) == 179
    result = {"version": 1, "verification": "passed", "audit_code_sha256": digest(Path(__file__)),
        "prepared_provenance_sha256": digest(prepared.DIRECTORY/"provenance.json"), "prepared_dataset_sha256": digest(prepared.DIRECTORY/"dataset.csv"),
        "source_archive_sha256": receipt["sha256"], "source_inventory_sha256": digest(raw/"inventory.json"),
        "source_receipt_sha256": digest(raw/"archive-receipt.json"), "source": prepared.source.PAGE,
        "source_instrument_preserved": "Subjective perceived exertion,SPE0-10, kept separate from native Borg",
        "conditions": conditions, "actual_source_targets_with_genuine_prior_verified": len(seen),
        "anonymous_table_sequences": 52, "source_unique_people_claimed": None, "single_conservative_source_cohort": True,
        "source_person_disjoint_holdout_claimed": False, "source_nominal_clock_only": True,
        "spe_only_auxiliary_task_eligible": True, "hr_spe_positional_join_approved": False,
        "native_borg_target_merge_approved": False, "model_fitting_started": False, "synthetic_rows": 0,
        "original_native_cohort": {"report_people": 40, "session_metadata_people": 40, "benchmark_people": 40,
            "additional_people_outside_benchmark": 0, "raw_reports_sha256": digest(RAW/"geofatigue/self_reported_fatigue_level.original.tab"),
            "session_metadata_sha256": digest(RAW/"geofatigue/session_metadata.json"), "native_dataset_sha256": native_manifest["dataset_sha256"],
            "original_training_cases": 487, "original_test_cases": 179, "test_outcomes_analyzed": False},
        "limitation": "Published sample size15 differs from available HR12/SPE13 rows; no identity key links sensor and response rows or participant rows across conditions. Do not fill missing rows, join by position, infer people from numerical similarity or claim an independent source-person validation. Only within-original-SPE-row chronology is used."}
    output = ROOT/"docs/fatigue-80-2026-10-25/walking-spe-eligibility.json"
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False), flush=True)
    return result


if __name__ == "__main__":
    verify()
