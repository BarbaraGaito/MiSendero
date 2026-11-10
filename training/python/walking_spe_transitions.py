"""Observed within-table SPE transitions; no inferred cross-file identities.

HR has 12 rows whereas SPE has 13; positional sensor/outcome joins are not
permitted. The entire source is one conservative cohort cluster. Table-row
identifiers refer only to published sequences, never claimed participant IDs.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

import fetch_walking_spe as source
from fatigue_features import RESEARCH
from public_sources import digest, group_key

DIRECTORY = RESEARCH/"walking-spe-transitions-80-v1"
CONDITIONS = ("BW_00", "BW_20", "DW_00", "DW_20")


def source_tables():
    raw = source.DIRECTORY
    inventory = json.loads((raw/"inventory.json").read_text())
    receipt = json.loads((raw/"archive-receipt.json").read_text())
    assert inventory["code_sha256"] == digest(Path(source.__file__))
    assert receipt["code_sha256"] == digest(Path(__file__).with_name("fetch_walking_spe_archive.py"))
    assert receipt["inventory_sha256"] == digest(raw/"inventory.json")
    assert receipt["sha256"] == receipt["published_sha256"] == digest(raw/"All_data.zip")
    assert receipt["bytes"] == (raw/"All_data.zip").stat().st_size == 46442
    for row in inventory["metadata"]:
        assert row["sha256"] == digest(raw/row["path"])
    html = (raw/"page.html").read_text(encoding="utf-8")
    state, _ = json.JSONDecoder().raw_decode(html.split("window.INITIAL_STATE = ", 1)[1])
    metadata = state["dataset"]["snapshot"]
    assert metadata["version"] == 1 and metadata["licence"]["short_name"] == "CC BY 4.0"
    assert "5, 10, 15, and 20 min" in metadata["method"] and "0 to 10" in metadata["method"]
    spe, hr, members = {}, {}, {}
    with zipfile.ZipFile(raw/"All_data.zip") as archive:
        assert len(archive.infolist()) == 142
        for condition in CONDITIONS:
            for modality, target in (("SPE", spe), ("HR", hr)):
                name = f"{modality}_{condition}.txt"
                payload = archive.read(name)
                target[condition] = np.loadtxt(io.BytesIO(payload))
                members[name] = {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
            assert spe[condition].shape == (13, 4) and hr[condition].shape == (12, 4)
            assert np.isfinite(spe[condition]).all() and ((0 <= spe[condition]) & (spe[condition] <= 10)).all()
            assert np.isfinite(hr[condition]).all()
    return spe, hr, members, metadata


def prepare():
    if (DIRECTORY/"provenance.json").exists() or (DIRECTORY/"dataset.csv").exists():
        raise ValueError("Preserve frozen SPE input snapshot; use a new version for changes")
    spe, hr, members, metadata = source_tables()
    rows, lineage = [], []
    cluster = group_key("Walking-SPE-mn3xyg2gh6-entire-source-cohort")
    for condition, values in spe.items():
        member = f"SPE_{condition}.txt"
        for source_row in range(len(values)):
            sequence = group_key(f"Walking-SPE-table-sequence:{member}:{source_row}")
            for column in (1, 2, 3):
                current_key = group_key(f"Walking-SPE-original-cell:{member}:{source_row}:{column}")
                prior_key = group_key(f"Walking-SPE-original-cell:{member}:{source_row}:{column-1}")
                now, previous = float(values[source_row, column]), float(values[source_row, column-1])
                rows.append({"source_domain": "walking_spe", "row_key": current_key, "prior_row_key": prior_key,
                    "group_key": cluster, "sequence_key": sequence, "source_condition": condition,
                    "nominal_elapsed_minutes": 5*(column+1), "nominal_prior_age_minutes": 5,
                    "prior_spe": previous, "prior2_spe": float(values[source_row, column-2]) if column >= 2 else np.nan,
                    "spe_native": now})
                lineage.append({"row_key": current_key, "prior_row_key": prior_key, "group_key": cluster,
                    "sequence_key": sequence, "member": member, "member_sha256": members[member]["sha256"],
                    "source_row_zero_based": source_row, "current_column_zero_based": column,
                    "prior_column_zero_based": column-1, "actual_current_spe": now, "actual_prior_spe": previous,
                    "nominal_current_minute": 5*(column+1), "nominal_prior_minute": 5*column,
                    "wall_clock_report_timestamp_invented": False, "hr_row_join_performed": False})
    frame = pd.DataFrame(rows)
    assert len(frame) == 156 and frame.row_key.is_unique and frame.sequence_key.nunique() == 52
    assert frame.group_key.nunique() == 1
    DIRECTORY.mkdir(exist_ok=True)
    frame.to_csv(DIRECTORY/"dataset.csv", index=False)
    result = {"version": 1, "source": source.PAGE, "doi": metadata["doi"], "license": metadata["licence"],
        "preparation_code_sha256": digest(Path(__file__)), "dataset_sha256": digest(DIRECTORY/"dataset.csv"),
        "source_inventory_sha256": digest(source.DIRECTORY/"inventory.json"),
        "source_receipt_sha256": digest(source.DIRECTORY/"archive-receipt.json"), "members": members,
        "actual_spe_cells_in_original_tables": 208, "actual_current_targets_with_prior": 156,
        "anonymous_within_condition_sequences": 52, "unique_source_participant_count_asserted": None,
        "cohort_size_stated_by_publisher": 15, "spe_rows_per_condition": 13, "hr_rows_per_condition": 12,
        "conservative_source_clusters": 1, "source_person_disjoint_validation_claimed": False,
        "source_holdout": "No person-level source split can be asserted without row identity metadata. Treat the entire source as one auxiliary fitting cohort; make no independent source-generalization claim. Original native person-disjoint folds and179 test stay fixed.",
        "sensor_outcome_join_approved": False, "native_borg_target_merge_approved": False,
        "source_instrument": "Publisher-defined subjective perceived exertion (SPE),0-10; preserve as a separate source outcome, not automatically relabeled as GeoFatigue Borg.",
        "nominal_clock_policy": "Original four columns are reported acquisition points5,10,15,20min. Their five-minute separation is nominal published protocol time; no absolute report clock, onset zero or intervening measurements are fabricated.",
        "potential_use": "Separate SPE-only auxiliary head or teacher using genuine earlier SPE/nominal time. No HR, EDA, motion or temperature is attached to a row without an explicit identity mapping.",
        "model_fitting_started": False, "synthetic_rows": 0, "interpolated_targets": 0, "assumed_onset_zeros": 0,
        "new_native_borg_targets": 0, "lineage": lineage}
    (DIRECTORY/"provenance.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"actual_source_targets_with_real_prior": len(frame), "anonymous_sequences": 52,
        "spe_rows": 13, "hr_rows": 12, "sensor_join_approved": False, "native_target_merge_approved": False}), flush=True)


def load():
    manifest = json.loads((DIRECTORY/"provenance.json").read_text())
    assert manifest["preparation_code_sha256"] == digest(Path(__file__))
    assert manifest["dataset_sha256"] == digest(DIRECTORY/"dataset.csv")
    assert manifest["source_receipt_sha256"] == digest(source.DIRECTORY/"archive-receipt.json")
    assert manifest["source_inventory_sha256"] == digest(source.DIRECTORY/"inventory.json")
    return pd.read_csv(DIRECTORY/"dataset.csv"), manifest


if __name__ == "__main__":
    prepare()
