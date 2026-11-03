"""Combine actual public source pairs without merging unlike instruments.

Worker/STS keep their Borg/HR fields; walking keeps SPE/nominal protocol time
and has no attached HR. The latter is one conservative source cohort rather
than fabricated participant identities or a claimed person-level holdout.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import fatigue_worker_survey_priors as previous
import walking_spe_transitions as walking
from fatigue_features import RESEARCH
from public_sources import ROOT, digest

DIRECTORY = RESEARCH/"combined-walking-source-pairs-80-v1"
DOCS = ROOT/"docs/fatigue-80-2026-10-25"


def dependencies():
    return {name: digest(path) for name, path in {
        "combination_code": Path(__file__), "previous_preparation_code": Path(previous.__file__),
        "walking_preparation_code": Path(walking.__file__),
        "previous_provenance": previous.DIRECTORY/"provenance.json",
        "walking_provenance": walking.DIRECTORY/"provenance.json",
        "previous_source_audit": DOCS/"worker-survey-prior-verification.json",
        "walking_source_audit": DOCS/"walking-spe-eligibility.json",
        "real_public_data_policy": DOCS/"public-real-data-policy.json"}.items()}


def originals():
    borg, provenance = previous.load()
    spe, spe_provenance = walking.load()
    walking.source_tables()  # Recheck original archive and metadata hashes.
    audit = json.loads((DOCS/"walking-spe-eligibility.json").read_text())
    if audit["prepared_dataset_sha256"] != spe_provenance["dataset_sha256"] or not audit["spe_only_auxiliary_task_eligible"]:
        raise ValueError("Actual walking source eligibility changed")
    if audit["audit_code_sha256"] != digest(Path(__file__).with_name("audit_walking_spe_eligibility.py")):
        raise ValueError("Original source-cell audit changed")
    if len(borg) != 302 or len(spe) != 156 or set(spe.source_domain) != {"walking_spe"}:
        raise ValueError("Actual source pair counts changed")
    for name, split in provenance["external_splits"].items():
        part = borg[borg.source_domain.eq(name)]
        if set(part.group_key) & set(split["test_groups"]) or set(part.row_key) & set(split["test_row_keys"]):
            raise ValueError("Reserved Worker/STS reports entered source fitting")
    if set(borg.row_key) & set(spe.row_key) or set(borg.group_key) & set(spe.group_key):
        raise ValueError("Distinct source namespaces collide")
    if "hr_last" in spe or "hr_history_mean" in spe or spe.group_key.nunique() != 1:
        raise ValueError("Unidentified sensors or invented participant groups entered walking inputs")
    return borg, spe


def prepare():
    if (DIRECTORY/"provenance.json").exists() or (DIRECTORY/"dataset.csv").exists():
        raise ValueError("Preserve the frozen real-source combination before changing it")
    borg, spe = originals()
    frame = pd.concat([borg, spe], ignore_index=True, sort=False)
    if len(frame) != 458 or not frame.row_key.is_unique:
        raise ValueError("Combined source reports are missing or duplicated")
    DIRECTORY.mkdir(exist_ok=True)
    frame.to_csv(DIRECTORY/"dataset.csv", index=False)
    result = {"version": 1, "dataset_sha256": digest(DIRECTORY/"dataset.csv"), "dependencies_sha256": dependencies(),
        "actual_source_targets": 458, "source_counts": frame.groupby("source_domain").size().astype(int).to_dict(),
        "walking_hr_cells_attached": 0, "walking_participant_identity_invented": False,
        "walking_source_cohort_clusters": 1, "walking_person_disjoint_holdout_claimed": False,
        "source_instruments": {"worker": "Actual original Borg CR10", "sts": "Actual original continuous Borg CR10",
            "walking_spe": "Actual original SPE0-10; separate outcome, not relabeled as native Borg"},
        "source_feature_policy": {"worker": ["prior_borg", "hr_last", "hr_history_mean"],
            "sts": ["prior_borg", "hr_last", "hr_history_mean"],
            "walking_spe": ["prior_spe", "prior2_spe", "nominal_elapsed_minutes"]},
        "policy": "Union of original public rows only; no target pooling across unlike instruments. Unmeasured/inapplicable union fields stay missing. Walking contains no guessed HR or participant identities; its four conditions may have separate SPE heads within one conservative cohort. Nominal published protocol minutes are not invented wall-clock report timestamps. Source forward-pass representations may be native inputs, never new observed Borg labels. Original native487/179 cohorts remain unchanged.",
        "native_target_merge": False, "new_native_borg_targets": 0, "synthetic_rows": 0, "interpolated_targets": 0,
        "model_fitting_started_at_preparation": False}
    (DIRECTORY/"provenance.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"actual_combined_source_targets": len(frame), "counts": result["source_counts"], "native_targets_added": 0}), flush=True)


def load():
    manifest = json.loads((DIRECTORY/"provenance.json").read_text())
    if manifest["dependencies_sha256"] != dependencies() or manifest["dataset_sha256"] != digest(DIRECTORY/"dataset.csv"):
        raise ValueError("Frozen real-source data, code, audits or policy changed")
    borg, spe = originals()
    expected = pd.concat([borg, spe], ignore_index=True, sort=False)
    frame = pd.read_csv(DIRECTORY/"dataset.csv")
    pd.testing.assert_frame_equal(frame, expected, check_dtype=False, rtol=0, atol=1e-12)
    if frame[frame.source_domain.eq("walking_spe")][["hr_last", "hr_history_mean", "borg_native"]].notna().any().any():
        raise ValueError("Walking rows received invented sensors or native Borg labels")
    return frame, manifest


if __name__ == "__main__":
    prepare()
