"""Inspect actual fitting likelihood and missing delta classes; no new fits."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import GroupKFold

import fatigue_physiology_pair_learning as study
from public_sources import ROOT, digest


def diagnose():
    inputs = study.load_inputs()
    _, train, test, extra, _, _, _ = inputs
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    assert selection["status"] == "complete"
    native = train.set_index("row_key")
    additional = extra.set_index("row_key")
    observed = pd.concat([native, additional])
    assert observed.index.is_unique and len(train) == 487 and len(test) == 179
    delta = observed.label.str.removeprefix("Borg ").astype(int)-observed.prior_borg.astype(int)
    visits = {"original": [], "extra": []}
    folds = []
    for number, (fit, val) in enumerate(GroupKFold(n_splits=5).split(train, groups=train.group_key)):
        cache_path = study.DIRECTORY/"bases"/f"fold-{number}.joblib"
        metadata = json.loads(cache_path.with_suffix(".json").read_text())
        assert metadata["cache_sha256"] == digest(cache_path)
        cache = joblib.load(cache_path)
        memberships = {}
        for inner in cache["inner_folds"]:
            known = set(delta.loc[inner["fit_row_keys"]].tolist())
            for key in inner["validation_row_keys"]+inner["extra_validation_row_keys"]:
                assert key not in memberships
                memberships[key] = int(delta.loc[key]) in known
        details = {}
        for cohort, row_key, logit_key in (("original", "fit_row_keys", "fit_logits"), ("extra", "extra_row_keys", "extra_logits")):
            keys = cache[row_key]
            target = torch.tensor(delta.loc[keys].to_numpy()+10, dtype=torch.long)
            log_probability = torch.log_softmax(cache[logit_key], dim=1)
            losses = -log_probability[torch.arange(len(keys)), target].numpy()
            missing = np.asarray([not memberships[key] for key in keys], dtype=bool)
            for key, loss, absent in zip(keys, losses, missing, strict=True):
                visits[cohort].append({"row_key": key, "native_delta": int(delta.loc[key]), "base_nll": float(loss), "target_class_absent_from_inner_original_fit": bool(absent)})
            details[cohort] = {"actual_report_visits": len(keys), "target_class_absent_from_inner_fit": int(missing.sum()),
                "base_mean_nll": float(losses.mean()), "fraction_base_nll_from_absent_classes": float(losses[missing].sum()/losses.sum())}
        folds.append({"outer_fold": number, "offset_cache_sha256": metadata["cache_sha256"], "cohorts": details})
    duration = []
    results = selection["results"][2:]
    for row in results:
        c = row["candidate"]
        if c["epochs"] != 80:
            continue
        longer = next(r for r in results if r["candidate"]["epochs"] == 200
            and r["candidate"]["waveform_view"] == c["waveform_view"]
            and r["candidate"]["include_extra_actual_reports"] == c["include_extra_actual_reports"])
        duration.append({"waveform_view": c["waveform_view"], "extra_actual_reports": c["include_extra_actual_reports"],
            "short_candidate": c["id"], "long_candidate": longer["candidate"]["id"],
            "cv_80_epochs": row["accuracy_mean"], "cv_200_epochs": longer["accuracy_mean"],
            "mean_fitting_nll_80_epochs": float(np.mean([f["loss_endpoints"][-1]["classification"] for f in row["folds"]])),
            "mean_fitting_nll_200_epochs": float(np.mean([f["loss_endpoints"][-1]["classification"] for f in longer["folds"]]))})
    result = {"version": 1, "diagnostic_code_sha256": digest(Path(__file__)), "selection_sha256": digest(selection_path),
        "new_fits": 0, "test_responses_inspected": False, "extra_actual_fitting_reports": len(extra),
        "folds": folds, "duration_comparisons": duration,
        "all_longer_fits_lower_training_nll_and_lower_cv": all(r["mean_fitting_nll_200_epochs"] < r["mean_fitting_nll_80_epochs"] and r["cv_200_epochs"] < r["cv_80_epochs"] for r in duration),
        "interpretation": "Longer fitting lowers actual fitting likelihood loss while all matched held-person accuracies deteriorate, consistent with overfitting. Baseline delta classes absent from an inner original-only fit receive a fixed -30 logit; additional actual questionnaires may expose this limitation. This diagnostic changes no targets, folds, metric or model and does not prove that an alternative will improve accuracy.",
        "visit_totals": {name: {"actual_report_visits_across_outer_fits": len(values), "unique_actual_reports": len({r["row_key"] for r in values}),
            "visits_with_target_class_absent_from_inner_fit": sum(r["target_class_absent_from_inner_original_fit"] for r in values),
            "unique_reports_with_target_class_absent_at_least_once": len({r["row_key"] for r in values if r["target_class_absent_from_inner_original_fit"]})} for name, values in visits.items()},
        "scope": "Fitting visits repeat because each real report belongs to four outer fitting partitions; these counts are not additional observations or augmented training cases. Only the original 487 and actual extra fitting-person reports are inspected; original179 test labels remain untouched."}
    path = ROOT/"docs/fatigue-80-2026-10-25/physiology-offset-diagnostic.json"
    path.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False))
    return result


if __name__ == "__main__":
    diagnose()
