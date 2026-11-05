"""Prior Borg plus real pre-task body measurements from the original study.

No demographic ID or gender is a predictor. Age, mass and stature must be
known before inference; this remains an unapproved research input contract.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from common.grouped_fatigue_search import grouped_search
from common.privacy import assert_no_restricted_columns
from fatigue_dynamics import CONTEXT, DIRECTORY as PARENT, load_inputs as parent_inputs
from fatigue_dynamics_experiment import DynamicsClassifier, plan as dynamics_plan
from fatigue_features import RESEARCH
from fetch_geofatigue_context import DIRECTORY as RAW_DIRECTORY, METADATA_PATH
from public_sources import OUTPUT, digest, verify_source_snapshot

DIRECTORY = RESEARCH / "body-context-80-v1"
BODY_FEATURES = ["body_age_years", "body_mass_kg", "body_height_cm", "body_mass_index", "carried_mass_fraction"]


def prepare():
    verify_source_snapshot("fatigue")
    frame, _, _, manifest, _ = parent_inputs()
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    entry = next(r["dataFile"] for r in metadata["data"]["latestVersion"]["files"] if r["dataFile"]["filename"] == "demographics.tab")
    source_path = RAW_DIRECTORY / "demographics.csv"
    if source_path.stat().st_size != entry["originalFileSize"] or digest(source_path, "md5") != entry["checksum"]["value"]:
        raise ValueError("Body measurements differ from publisher checksum/size")
    body = pd.read_csv(source_path).set_index("id")
    # The original sheet spells only P0 with an uppercase P; other public
    # records use p0. Normalize case, then reject any resulting collision.
    body.index = body.index.astype(str).str.lower()
    if len(body) != 40 or not body.index.is_unique or body[["age", "weight", "height"]].isna().any().any():
        raise ValueError("Ambiguous or missing original body measurements")
    canonical = json.loads((OUTPUT / "fatigue/provenance.json").read_text(encoding="utf-8"))
    additions = []
    for row in canonical["lineage"]:
        participant = "p" + re.search(r"/p(\d+)-", row["lineage"]["member"])[1]
        values = body.loc[participant]
        age, mass, height = [float(values[c]) for c in ("age", "weight", "height")]
        if not 18 <= age <= 100 or not 30 <= mass <= 250 or not 100 <= height <= 250:
            raise ValueError("Pre-task measurement units/range differ from published schema")
        additions.append(dict(zip(BODY_FEATURES, (age, mass, height, mass / (height / 100) ** 2, 9.1 / mass))))
    combined = pd.concat([frame.drop(columns=["label", "row_key", "group_key"]), pd.DataFrame(additions), frame[["label"]]], axis=1)
    assert_no_restricted_columns(combined, "body-context-80-v1")
    if combined["label"].tolist() != frame["label"].tolist() or len(combined) != 666:
        raise ValueError("Original native targets or cohort changed")
    DIRECTORY.mkdir(exist_ok=True)
    if (DIRECTORY / "dataset.csv").exists():
        raise ValueError("Body context already prepared; preserve its snapshot")
    combined.to_csv(DIRECTORY / "dataset.csv", index=False)
    updated = {**manifest, "parent_dataset_sha256": manifest["dataset_sha256"], "dataset_sha256": digest(DIRECTORY / "dataset.csv"),
               "feature_code_sha256": digest(Path(__file__)), "body_features": BODY_FEATURES,
               "body_source_sha256": digest(source_path), "body_source_published_md5": entry["checksum"]["value"],
               "body_source_metadata_sha256": digest(METADATA_PATH), "body_source_dataverse_id": entry["id"],
               "body_identifier_normalization": "Case only: original P0 corresponds to p0; uniqueness checked after normalization.",
               "body_units_source": "https://github.com/UbiSensingAILab/GeoFatigue/blob/main/geofatigue/loaders/metadata.py",
               "body_input_contract": "Actual pre-task age (years), mass (kg), stature (cm); 9.1 kg is the observed fixed study load. No IDs or gender as predictors. Not a sensor-only model.",
               "features": [c for c in combined if c != "label"]}
    (DIRECTORY / "provenance.json").write_text(json.dumps(updated, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("Prepared five pre-task body-context predictors for all 666 unchanged native responses", flush=True)


def load_inputs():
    manifest = json.loads((DIRECTORY / "provenance.json").read_text(encoding="utf-8"))
    if digest(DIRECTORY / "dataset.csv") != manifest["dataset_sha256"] or digest(Path(__file__)) != manifest["feature_code_sha256"]:
        raise ValueError("Body-context source snapshot/code changed")
    frame = pd.read_csv(DIRECTORY / "dataset.csv", dtype={"label": str})
    frame = pd.concat([frame, pd.DataFrame({"row_key": [r["row_key"] for r in manifest["lineage"]], "group_key": [r["group_key"] for r in manifest["lineage"]]})], axis=1)
    protocol = json.loads((OUTPUT / "fatigue/metrics.json").read_text(encoding="utf-8"))["evaluation_protocol"]
    train, test = [frame[frame["row_key"].isin(protocol[key])].copy() for key in ("train_row_keys", "test_row_keys")]
    if len(train) != 487 or len(test) != 179 or set(train["group_key"]) & set(test["group_key"]):
        raise ValueError("Body-context participant holdout changed")
    return frame, train, test, manifest, protocol


def plan(manifest):
    prior = manifest["calibration_features"] + CONTEXT
    compact = next(c["features"] for c in dynamics_plan(manifest) if c["feature_set"] == "compact_dynamics")
    physiology = ["hr_last", "hr_delta_baseline", "hr_ratio_baseline", "hr_change_after_prior", "hr_recent_slope",
                  "eda_delta_baseline", "eda_recent_slope", "acceleration_history_mean", "met_history_mean", "screening_sleep_hours"]
    sets = {"body_prior_context": prior + BODY_FEATURES,
            "body_dynamics": compact + BODY_FEATURES,
            "body_physiology": compact + BODY_FEATURES + physiology}
    configs = [
        *[("mlp", {"hidden_layer_sizes": shape, "solver": "lbfgs", "alpha": alpha, "max_iter": 1500}) for shape in ([8], [16, 8], [32, 16]) for alpha in (1., 10., 100.)],
        *[("svm", {"C": c, "gamma": "scale"}) for c in (.1, 1., 10.)],
        *[("logistic", {"C": c, "max_iter": 3000}) for c in (.01, .1, 1.)],
        *[("random_forest", {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": leaf, "max_features": 1.}) for leaf in (2, 5)],
        *[("extra_trees", {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": leaf, "max_features": 1.}) for leaf in (2, 5)],
        *[("xgboost", {"n_estimators": 250, "max_depth": depth, "learning_rate": .05, "reg_lambda": 10, "min_child_weight": 5}) for depth in (2, 3)],
    ]
    return [{"id": f"body-{i:03d}", "feature_set": name, "features": columns, "algorithm": algorithm, "params": params, "target_mode": mode}
            for i, (name, columns, algorithm, params, mode) in enumerate(
                (name, columns, algorithm, params, mode) for name, columns in sets.items() for algorithm, params in configs
                for mode in ("absolute_borg", "change_from_prior"))]


def select():
    if not (DIRECTORY / "provenance.json").exists():
        prepare()
    _, train, _, manifest, _ = load_inputs()
    fingerprint = {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"],
                   "grouped_search_code_sha256": digest(Path(__file__).parent / "common/grouped_fatigue_search.py"),
                   "classifier_code_sha256": digest(Path(__file__).with_name("fatigue_dynamics_experiment.py"))}
    grouped_search(DIRECTORY, train, plan(manifest), fingerprint, DynamicsClassifier)


if __name__ == "__main__":
    select()
