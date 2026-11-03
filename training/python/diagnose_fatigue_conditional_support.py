"""Describe impossible-delta mass using saved fitting-only OOF sources.

This diagnostic discards current outcomes before probability calculations.
It never fits a model, selects a recipe, or evaluates reserved participants.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.model_selection import GroupKFold

import fatigue_conditional_borg as conditional
from public_sources import digest


def diagnose():
    selection_path = conditional.DIRECTORY / "selection.json"
    selection = json.loads(selection_path.read_text())
    _, training, _, _, _, _, _, inputs, _ = conditional.load_inputs()
    signature = conditional.fingerprint(inputs)
    if (selection["status"] != "complete" or selection["train_row_keys"] != training["row_key"].tolist()
            or any(selection.get(k) != v for k, v in signature.items())):
        raise ValueError("Conditional study is incomplete or its frozen inputs changed")
    # Outcome columns are discarded before the diagnostic calculations.
    training = training.drop(columns="label")
    folds = list(GroupKFold(n_splits=5).split(training, groups=training["group_key"]))
    results = {}
    for initialization in ("core", "view"):
        mass = np.full(len(training), np.nan)
        outside = np.zeros(len(training), dtype=bool)
        source_hashes = []
        for number, (fit, val) in enumerate(folds):
            path = conditional.DIRECTORY / "sources" / f"{initialization}-fold-{number}.joblib"
            descriptor = json.loads(path.with_suffix(".json").read_text())
            if descriptor["signature"] != signature or descriptor["model_sha256"] != digest(path):
                raise ValueError("Saved source state or lineage changed")
            source = joblib.load(path)
            if source["fit_row_keys"] != training.iloc[fit]["row_key"].tolist():
                raise ValueError("Source has different fitting participants/queries")
            features = training.iloc[val][source["features"]]
            prior = features["prior_borg"].to_numpy(int)
            probabilities = source["classifier"].predict_proba(source["preprocessor"].transform(features))
            destinations = prior[:, None] + source["classifier"].classes_.astype(int)[None, :]
            invalid = (destinations < 0) | (destinations > 10)
            np.testing.assert_allclose(probabilities.sum(axis=1), 1., rtol=0, atol=1e-12)
            mass[val] = np.where(invalid, probabilities, 0.).sum(axis=1)
            outside[val] = invalid[np.arange(len(val)), probabilities.argmax(axis=1)]
            source_hashes.append(descriptor["model_sha256"])
        if not np.isfinite(mass).all():
            raise ValueError("Incomplete original OOF feature diagnostic")
        point = next(r for r in selection["results"] if r["candidate"]["initialization"] == initialization
                     and r["candidate"]["mode"] == "point_control")
        condition = next(r for r in selection["results"] if r["candidate"]["initialization"] == initialization
                         and r["candidate"]["mode"] == "condition_only")
        results[initialization] = {
            "original_training_queries": len(training),
            "source_model_sha256": source_hashes,
            "invalid_destination_probability_mass_mean": float(mass.mean()),
            "invalid_destination_probability_mass_p95": float(np.quantile(mass, .95)),
            "invalid_destination_probability_mass_max": float(mass.max()),
            "unclipped_delta_argmax_outside_native_range": int(outside.sum()),
            "condition_only_changed_point_decisions": int(np.count_nonzero(
                np.asarray(point["oof_predictions"]) != np.asarray(condition["oof_predictions"]))),
        }
    return {
        "version": 1, "selection_sha256": digest(selection_path),
        "diagnostic_code_sha256": digest(Path(__file__)),
        "current_training_outcomes_used_for_calculations": False,
        "reserved_test_outcomes_used": False, "model_accuracy": None,
        "used_as_goal_score": False, "model_weights_changed": False,
        "sources": results,
        "scope": "Ten fixed fitting-only MLP source states on the original 487 OOF feature rows. "
                 "This only describes impossible-destination probability mass before fine-tuning; "
                 "it does not establish a data-wide performance bound or assess the reserved test.",
    }


if __name__ == "__main__":
    result = diagnose()
    path = conditional.DIRECTORY / "support-diagnostic.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
