"""Combine audited fitting reports while retaining their study/outcome context."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fatigue_features import RESEARCH
from fatigue_source_teachers import external_inputs
from public_sources import digest
from sixmwt_fatigue import ACC_FEATURES, load as load_sixmwt

DIRECTORY = RESEARCH / "joint-sources-80-v1"
SENSOR_FEATURES = ["hr_last", "hr_history_mean", *ACC_FEATURES]
PARENTS = {"worker": "worker-v1", "sts": "sts-v1", "oxbioz_post_trial": "oxbioz-v1", "sixmwt_post_test": "sixmwt-v1"}


def combine(sources, splits):
    rows, counts = [], {}
    for name, frame in sources.items():
        split = splits[name]
        if (frame["row_key"].tolist() != split["train_row_keys"]
                or set(frame["row_key"]) & set(split["test_row_keys"])
                or set(frame["group_key"]) & set(split["test_groups"])):
            raise ValueError("An external reserved response/person entered the combined fitting table")
        target = frame["borg_native"].to_numpy(float)
        if not np.isfinite(target).all() or np.any((target < 0) | (target > 10)):
            raise ValueError("Original native CR10 outcomes required; no scale conversion or filling")
        measurements = frame.reindex(columns=SENSOR_FEATURES).copy()
        measurements["borg_native"] = target
        measurements["source_domain"] = name
        measurements["row_key"], measurements["group_key"] = frame["row_key"].to_numpy(), frame["group_key"].to_numpy()
        rows.append(measurements)
        counts[name] = {"reports": len(frame), "participants": frame["group_key"].nunique(),
                        "fractional_native_reports": int(np.any(target != np.rint(target))) and int((target != np.rint(target)).sum()),
                        "actually_available_features": [c for c in SENSOR_FEATURES if c in frame and frame[c].notna().any()]}
    result = pd.concat(rows, ignore_index=True)
    if not result["row_key"].is_unique:
        raise ValueError("Combined fitting table duplicates original reports")
    domains_per_person = result.groupby("group_key")["source_domain"].nunique()
    if not domains_per_person.eq(1).all():
        raise ValueError("Source participant namespaces collide")
    return result, counts


def prepare():
    sources, splits = external_inputs()
    sixmwt, _, six_manifest = load_sixmwt()
    sources["sixmwt_post_test"], splits["sixmwt_post_test"] = sixmwt, six_manifest["split"]
    combined, counts = combine(sources, splits)
    expected = {"worker": 253, "sts": 187, "oxbioz_post_trial": 32, "sixmwt_post_test": 48}
    if {name: value["reports"] for name, value in counts.items()} != expected or len(combined) != 520:
        raise ValueError("Audited original source fitting counts changed")
    parent_paths = {}
    for name in sources:
        path = RESEARCH / PARENTS[name] / "provenance.json"
        if not path.exists() and name == "oxbioz_post_trial":
            from oxbioz_fatigue import DIRECTORY as OX_DIRECTORY
            path = OX_DIRECTORY / "provenance.json"
        parent_paths[name] = path
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "dataset.csv"
    if path.exists():
        raise ValueError("Preserve the frozen combined dataset before preparing another version")
    combined.to_csv(path, index=False)
    helpers = ("fatigue_source_teachers.py", "fatigue_auxiliary_transfer.py", "sixmwt_fatigue.py")
    evidence = {"version": 1, "feature_code_sha256": digest(Path(__file__)), "dataset_sha256": digest(path),
                "source_provenance": {name: {"path": path.relative_to(RESEARCH).as_posix(), "sha256": digest(path)} for name, path in parent_paths.items()},
                "dependency_code_sha256": {name: digest(Path(__file__).with_name(name)) for name in helpers},
                "external_splits": splits, "domains": counts, "actual_reports": 520, "participants": combined["group_key"].nunique(),
                "sensor_features": SENSOR_FEATURES, "synthetic_rows": 0, "interpolated_targets": 0, "assumed_zero_targets": 0,
                "missing_sensor_values_filled_in_snapshot": False, "native_fractional_reports_preserved": True,
                "new_geofatigue_validation_or_test_cases": 0, "native_momentary_target_merge": False,
                "policy": "Only the original fitting participants of each external study are combined. Native continuous CR10 values, including actual STS half points, stay unchanged. Study/outcome context remains explicit and routes separate auxiliary regression heads. Only sensor units already audited as compatible are shared; absent measurements remain NaN. Original GeoFatigue classification targets and evaluation cases remain separate."}
    (DIRECTORY / "provenance.json").write_text(json.dumps(evidence, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(f"Combined {len(combined)} actual external fitting reports / {evidence['participants']} source participants; original Borg test unchanged", flush=True)
    print(json.dumps(counts, indent=2), flush=True)


def load():
    evidence = json.loads((DIRECTORY / "provenance.json").read_text(encoding="utf-8"))
    if digest(Path(__file__)) != evidence["feature_code_sha256"] or digest(DIRECTORY / "dataset.csv") != evidence["dataset_sha256"]:
        raise ValueError("Frozen combined source table/preparation changed")
    for entry in evidence["source_provenance"].values():
        if digest(RESEARCH / entry["path"]) != entry["sha256"]:
            raise ValueError("Combined source audit changed")
    for name, sha in evidence["dependency_code_sha256"].items():
        if digest(Path(__file__).with_name(name)) != sha:
            raise ValueError("Combined source loader dependency changed")
    frame = pd.read_csv(DIRECTORY / "dataset.csv")
    if len(frame) != 520 or not frame["row_key"].is_unique or set(frame["source_domain"]) != set(evidence["domains"]):
        raise ValueError("Combined source reports changed")
    for name, split in evidence["external_splits"].items():
        actual = frame[frame["source_domain"].eq(name)]
        if (actual["row_key"].tolist() != split["train_row_keys"] or set(actual["row_key"]) & set(split["test_row_keys"])
                or set(actual["group_key"]) & set(split["test_groups"])):
            raise ValueError("Reserved external labels/participants entered the joint table")
    return frame, evidence


if __name__ == "__main__":
    prepare()
