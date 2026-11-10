"""Bounded waveform correction with finite-support native probability anchors.

Only model probabilities are regularized. Targets remain actual, unmodified
integer Borg differences; there is no label smoothing or generated data.
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from torch import nn

import fatigue_physiology_pair_learning as parent
from public_sources import ROOT, digest

DIRECTORY = parent.DIRECTORY.parent/"supported-physiology-80-v1"
PREVIOUS_AUDIT = ROOT/"docs/fatigue-80-2026-10-25/physiology-learning-verification.json"
DIAGNOSTIC = ROOT/"docs/fatigue-80-2026-10-25/physiology-offset-diagnostic.json"
_RUNTIME = None


def plan():
    result = [{"id": f"supported-phys-{i:03d}", "algorithm": "previous_real_control", "parent_candidate_id": key}
              for i, key in enumerate(("phys-pair-000", "phys-pair-001", "phys-pair-008"))]
    for floor in (0., .05):
        for penalty in (1., 10.):
            for extra_weight in (.1, 1.):
                result.append({"id": f"supported-phys-{len(result):03d}", "algorithm": "bounded_supported_waveform_residual",
                    "anchor_uniform_mass": floor, "maximum_logit_correction": 3., "correction_penalty": penalty,
                    "extra_report_weight": extra_weight, "epochs": 40, "learning_rate": .003, "weight_decay": .1,
                    "random_seed": 42, "waveform_view": "current_and_prior_waveforms", "include_extra_actual_reports": True,
                    "prior_reference_scale_floor": .01, "normalized_value_clip": 20., "target_smoothing": False})
    return result


def supported_anchor(logits, mass):
    if not 0 <= mass < 1 or logits.ndim != 2 or logits.shape[1] != 21 or not torch.isfinite(logits).all():
        raise ValueError("Finite native 21-option logits and a valid probability mass are required")
    logp = torch.log_softmax(logits, dim=1)
    if mass:
        logp = torch.logaddexp(logp+math.log1p(-mass), torch.full_like(logp, math.log(mass/21)))
    return logp


def bounded_correction(raw, limit):
    if limit <= 0:
        raise ValueError("Correction limit must be positive")
    return limit*torch.tanh(raw/limit)


def fingerprint(inputs):
    return {"code_sha256": digest(Path(__file__)), "parent_signature": parent.fingerprint(inputs),
            "previous_verification_sha256": digest(PREVIOUS_AUDIT), "diagnostic_sha256": digest(DIAGNOSTIC),
            "public_real_data_policy_sha256": digest(parent.source.POLICY), "worker_processes": 2}


def load_inputs():
    inputs = parent.load_inputs()
    previous = json.loads(PREVIOUS_AUDIT.read_text())
    if previous["selection_sha256"] != digest(parent.DIRECTORY/"selection.json") or previous["verification_code_sha256"] != digest(Path(__file__).with_name("audit_fatigue_physiology_pair_learning.py")):
        raise ValueError("The independently verified parent waveform study changed")
    diagnostic = json.loads(DIAGNOSTIC.read_text())
    if diagnostic["selection_sha256"] != previous["selection_sha256"] or not diagnostic["all_longer_fits_lower_training_nll_and_lower_cv"]:
        raise ValueError("The evidence motivating bounded regularization changed")
    return inputs


class SupportedPhysiologyBorg:
    def __init__(self, candidate):
        self.candidate = candidate

    def fit(self, frame, extra, native_windows, extra_windows, specification, cached, observer=None):
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        if not set(extra.group_key) <= set(frame.group_key) or set(extra.row_key) & set(frame.row_key):
            raise ValueError("Additional targets must be distinct actual fitting-person reports")
        if cached["fit_row_keys"] != frame.row_key.tolist() or cached["extra_row_keys"] != extra.row_key.tolist():
            raise ValueError("Nested original/extra offsets belong to another fitting cohort")
        self.base = cached["base"]
        self.base.model.requires_grad_(False)
        self.input_features = list(specification["features"])
        fitting = pd.concat([frame, extra], ignore_index=True)
        windows = {name: np.concatenate([native_windows[name], extra_windows[name]], axis=0) for name in native_windows}
        if len(fitting) != len(windows["fast_current"]):
            raise ValueError("Real windows and unchanged report targets are misaligned")
        raw_offsets = torch.cat((cached["fit_logits"], cached["extra_logits"]), dim=0)
        offsets = supported_anchor(raw_offsets, self.candidate["anchor_uniform_mass"]).detach()
        context = parent.base_features(self.base, fitting)[0].float()
        current, prior = fitting.label.str.removeprefix("Borg ").to_numpy(int), fitting.prior_borg.to_numpy(int)
        target = torch.tensor(current-prior+10, dtype=torch.long)
        weight = torch.ones(len(fitting), dtype=torch.float64)
        weight[len(frame):] = self.candidate["extra_report_weight"]
        if observer is not None:
            observer(fitting[self.input_features].copy(), {name: value.copy() for name, value in windows.items()},
                     current.copy(), prior.copy(), weight.numpy().copy())
        normalized = parent.normalize_windows(windows, self.candidate)
        torch.manual_seed(self.candidate["random_seed"])
        self.network = parent.WaveformResidual(context.shape[1], paired=True)
        optimizer = torch.optim.AdamW(self.network.parameters(), lr=self.candidate["learning_rate"], weight_decay=self.candidate["weight_decay"])
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, self.candidate["epochs"]), eta_min=.0003)
        self.loss_endpoints = []
        for epoch in range(self.candidate["epochs"]):
            optimizer.zero_grad(set_to_none=True)
            correction = bounded_correction(self.network(normalized, context, offsets), self.candidate["maximum_logit_correction"])
            losses = nn.functional.cross_entropy(offsets+correction, target, reduction="none")
            classification = (losses*weight).sum()/weight.sum()
            penalty = self.candidate["correction_penalty"]*(correction.square().mean(dim=1)*weight).sum()/weight.sum()
            loss = classification+penalty
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite finite-support weighted native likelihood")
            loss.backward()
            if any(p.grad is not None and not torch.isfinite(p.grad).all() for p in self.network.parameters()):
                raise ValueError("Nonfinite supported-physiology gradient")
            nn.utils.clip_grad_norm_(self.network.parameters(), 5.)
            optimizer.step()
            scheduler.step()
            if epoch in (0, self.candidate["epochs"]-1):
                self.loss_endpoints.append({"classification": float(classification.detach()), "original_mean_nll": float(losses[:len(frame)].mean().detach()),
                    "extra_mean_nll": float(losses[len(frame):].mean().detach()), "penalty": float(penalty.detach()), "total": float(loss.detach())})
        self.network.requires_grad_(False).eval()
        for parameter in self.network.parameters():
            parameter.grad = None
        self.training_summary = {"original_native_targets": len(frame), "additional_actual_targets": len(extra),
            "total_actual_targets": len(fitting), "original_weight_sum": float(len(frame)),
            "extra_weight_sum": float(len(extra)*self.candidate["extra_report_weight"]),
            "unchanged_integer_targets": True, "label_smoothing": False, "synthetic_examples": 0,
            "artificial_input_masks": 0, "missing_native_cases_dropped": 0, "inner_participant_folds": 3}
        return self

    def predict(self, frame, windows):
        with torch.no_grad():
            context, raw_offsets = parent.base_features(self.base, frame)
            offsets = supported_anchor(raw_offsets, self.candidate["anchor_uniform_mass"])
            correction = bounded_correction(self.network(parent.normalize_windows(windows, self.candidate), context.float(), offsets), self.candidate["maximum_logit_correction"])
            logits = offsets+correction
            if not torch.isfinite(logits).all():
                raise ValueError("Nonfinite supported native output")
            order = torch.tensor(self.base.model.priority)
            delta = order[logits[:, order].argmax(dim=1)].numpy()-10
        predicted = np.clip(delta+frame.prior_borg.to_numpy(int), 0, 10)
        return np.asarray([f"Borg {value}" for value in predicted])


def worker_initialize():
    global _RUNTIME
    inputs = load_inputs()
    _RUNTIME = inputs, fingerprint(inputs)


def compute_fold(job):
    number, fit, val = job
    inputs, signature = _RUNTIME
    _, train, _, extra, arrays, lookup, manifest = inputs
    fitting, validation = train.iloc[fit], train.iloc[val]
    eligible = extra[extra.group_key.isin(set(fitting.group_key))]
    if set(validation.group_key) & (set(fitting.group_key)|set(eligible.group_key)):
        raise ValueError("Original/extra fitting observations leaked held-out people")
    cache_path = parent.DIRECTORY/"bases"/f"fold-{number}.joblib"
    metadata = json.loads(cache_path.with_suffix(".json").read_text())
    if metadata["signature"] != signature["parent_signature"] or metadata["cache_sha256"] != digest(cache_path):
        raise ValueError("Independently verified parent nested offsets changed")
    cached = joblib.load(cache_path)
    if metadata["fit_row_keys"] != fitting.row_key.tolist() or metadata["validation_row_keys"] != validation.row_key.tolist() or metadata["extra_eligible_row_keys"] != eligible.row_key.tolist():
        raise ValueError("Parent nested offsets have different original/extra membership")
    native_windows = parent.select_windows(arrays, lookup, fitting.row_key)
    extra_windows = parent.select_windows(arrays, lookup, eligible.row_key)
    held_windows = parent.select_windows(arrays, lookup, validation.row_key)
    identity = {"signature": signature, "fold_number": number, "fit_row_keys": fitting.row_key.tolist(),
                "validation_row_keys": validation.row_key.tolist(), "extra_eligible_row_keys": eligible.row_key.tolist(),
                "nested_offset_cache_sha256": metadata["cache_sha256"]}
    for c in plan()[3:]:
        path = DIRECTORY/"folds"/f"{c['id']}-fold-{number}.json"
        row_identity = {**identity, "candidate": c}
        if path.exists():
            saved = json.loads(path.read_text())
            if any(saved.get(k) != v for k, v in row_identity.items()):
                raise ValueError("Frozen finite-support native recipe changed")
        else:
            model = SupportedPhysiologyBorg(c).fit(fitting, eligible, native_windows, extra_windows, parent.core_candidate(manifest), cached)
            saved = {**row_identity, "predicted": model.predict(validation, held_windows).tolist(),
                     "training_summary": model.training_summary, "loss_endpoints": model.loss_endpoints}
            path.write_text(json.dumps(saved, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        print(f"Finite-support physiological recipe {c['id']} fold {number+1}/5 complete", flush=True)
    return number


def save(report):
    path = DIRECTORY/"selection.json"
    payload = json.dumps(report, indent=2, allow_nan=False)+"\n"
    path.with_suffix(".tmp").write_text(payload, encoding="utf-8")
    path.write_text(payload, encoding="utf-8")


def select():
    inputs = load_inputs()
    _, train, test, _, _, _, _ = inputs
    signature = fingerprint(inputs)
    DIRECTORY.mkdir(exist_ok=True)
    (DIRECTORY/"folds").mkdir(exist_ok=True)
    report = {**signature, "version": 1, "status": "running", "plan": plan(), "results": [],
        "train_row_keys": train.row_key.tolist(), "evaluation_denominator": len(train), "test_denominator": len(test),
        "target_accuracy": .8, "minimum_cv_for_new_test_evaluation": .65, "test_used_for_selection": False,
        "previous_benchmark_results_are_published": True, "synthetic_examples": 0,
        "policy": "Only native model probabilities receive a finite prior mass; integer target classes and actual current/previous Borg remain unchanged. Fixed bounded correction, regularization and reduced extra-report weight address previously diagnosed fitting instability/context shift. No synthetic labels/examples, artificial sensor masks, target smoothing, altered denominator or validation stopping. Original 487/179 participant cohorts retained. Extra 56 actual reports are fitting-person-only. Offsets are unchanged independently verified original-only three-inner-person-fold estimates. Original test requires a frozen CV>=.65 recipe."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        previous = json.loads(path.read_text())
        if any(previous.get(k) != v for k, v in signature.items()) or previous["plan"] != plan() or previous["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen supported-physiology search changed")
        report = previous
    else:
        save(report)
    if report["status"] == "complete":
        return report
    folds = list(GroupKFold(n_splits=5).split(train, groups=train.group_key))
    with ProcessPoolExecutor(max_workers=2, initializer=worker_initialize) as pool:
        futures = [pool.submit(compute_fold, (i, fit, val)) for i, (fit, val) in enumerate(folds)]
        for future in as_completed(futures):
            print(f"Finite-support physiological fold {future.result()+1}/5 complete", flush=True)
    previous = json.loads((parent.DIRECTORY/"selection.json").read_text())
    for c in plan():
        if any(row["candidate"] == c for row in report["results"]):
            continue
        if c["algorithm"] == "previous_real_control":
            old = next(r for r in previous["results"] if r["candidate"]["id"] == c["parent_candidate_id"])
            predicted, details = np.asarray(old["oof_predictions"]), []
        else:
            predicted, details = np.empty(len(train), dtype=object), []
            for i, (_, val) in enumerate(folds):
                saved = json.loads((DIRECTORY/"folds"/f"{c['id']}-fold-{i}.json").read_text())
                predicted[val] = saved["predicted"]
                details.append(saved)
        scores = [float(accuracy_score(train.iloc[val].label, predicted[val])) for _, val in folds]
        report["results"].append({"candidate": c, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
            "pooled_oof_accuracy": float(accuracy_score(train.label, predicted)), "oof_predictions": predicted.tolist(), "folds": details})
        winner = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=winner["candidate"]["id"], best_cv_accuracy=winner["accuracy_mean"])
        save(report)
        print(f"Finite-support physiological recipe {c['id']}: CV={np.mean(scores):.6f}", flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
