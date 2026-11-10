"""Two-rate Conv1D residual learning on unchanged real physiological windows.

The optional 56 additional targets are actual original questionnaires and
belong only to the fitting people of each fold. Original 487/179 outcomes,
participant boundaries and exact Borg definitions remain fixed.
"""
from __future__ import annotations

import importlib.metadata
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from torch import nn

import fatigue_physiology_pairs as source
from fatigue_joint_transfer import base_features
from fatigue_warm_sgd import WarmPersonalBorg, core_candidate
from public_sources import ROOT, digest

DIRECTORY = source.DIRECTORY.parent / "physiology-pair-learning-80-v1"
PREVIOUS = source.DIRECTORY.parent / "prior-conditioned-joint-transfer-80-v1/selection.json"
INPUT_AUDIT = ROOT / "docs/fatigue-80-2026-10-25/physiology-pair-verification.json"
_RUNTIME = None


def plan():
    candidates = [{"id": "phys-pair-000", "algorithm": "previous_real_control", "parent_candidate_id": "prior-joint-000"},
                  {"id": "phys-pair-001", "algorithm": "previous_real_control", "parent_candidate_id": "prior-joint-001"}]
    for view in ("current_with_prior_reference", "current_and_prior_waveforms"):
        for extra in (False, True):
            for epochs in (80, 200):
                candidates.append({"id": f"phys-pair-{len(candidates):03d}", "algorithm": "real_physiology_conv1d_residual",
                    "waveform_view": view, "include_extra_actual_reports": extra, "epochs": epochs,
                    "learning_rate": .003, "weight_decay": .1, "correction_penalty": .1,
                    "random_seed": 42, "prior_reference_scale_floor": .01, "normalized_value_clip": 20.})
    return candidates


def load_inputs():
    arrays, provenance = source.load()
    audit = json.loads(INPUT_AUDIT.read_text(encoding="utf-8"))
    if audit["verification"] != "passed" or audit["provenance_sha256"] != digest(source.DIRECTORY/"provenance.json") or audit["windows_sha256"] != provenance["windows_sha256"]:
        raise ValueError("Actual waveform input audit missing or mismatched")
    frame, train, test, manifest, _ = source.native_inputs()
    extra, extra_manifest = source.extra_feedback.load()
    if provenance["cohort"]["native_dataset_sha256"] != manifest["dataset_sha256"] or provenance["cohort"]["extra_dataset_sha256"] != extra_manifest["dataset_sha256"]:
        raise ValueError("Waveform target cohort changed")
    if arrays["row_keys"].tolist() != frame.row_key.tolist()+extra.row_key.tolist():
        raise ValueError("Waveform inputs and actual current reports differ")
    lookup = {key: i for i, key in enumerate(arrays["row_keys"].tolist())}
    return frame, train, test, extra, arrays, lookup, manifest


def fingerprint(inputs):
    return {"code_sha256": digest(Path(__file__)), "source_provenance_sha256": digest(source.DIRECTORY/"provenance.json"),
            "input_verification_sha256": digest(INPUT_AUDIT), "native_dataset_sha256": inputs[6]["dataset_sha256"],
            "previous_selection_sha256": digest(PREVIOUS), "public_real_data_policy_sha256": digest(source.POLICY),
            "dependency_code_sha256": {name: digest(Path(__file__).with_name(name)) for name in
                ("fatigue_physiology_pairs.py", "fatigue_warm_sgd.py", "fatigue_joint_transfer.py", "fatigue_dynamics_experiment.py")},
            "software_versions": {name: importlib.metadata.version(name) for name in ("torch", "numpy", "pandas", "scikit-learn", "joblib")},
            "worker_processes": 2}


def select_windows(arrays, lookup, keys):
    indexes = [lookup[key] for key in keys]
    return {name: arrays[name][indexes].copy() for name in ("fast_current", "fast_prior", "slow_current", "slow_prior")}


def normalize_windows(windows, candidate):
    """Deterministic per-query normalization; never a generated observation."""
    result = {}
    for band in ("fast", "slow"):
        current, prior = windows[band+"_current"], windows[band+"_prior"]
        statistics = {}
        for name, values in (("current", current), ("prior", prior)):
            mask = values[:, 2:]
            count = mask.sum(axis=2, keepdims=True)
            mean = (values[:, :2]*mask).sum(axis=2, keepdims=True)/np.maximum(count, 1)
            variance = (((values[:, :2]-mean)*mask)**2).sum(axis=2, keepdims=True)/np.maximum(count, 1)
            scale = np.maximum(np.sqrt(variance), candidate["prior_reference_scale_floor"]*np.abs(mean))
            statistics[name] = count, mean, np.maximum(scale, 1e-6)
        for phase, values in (("current", current), ("prior", prior)):
            count, mean, scale = statistics["prior"]
            if phase == "current":
                mean = np.where(count > 0, mean, statistics["current"][1])
                scale = np.where(count > 0, scale, statistics["current"][2])
            normalized = values.copy()
            normalized[:, :2] = np.clip((values[:, :2]-mean)/scale, -candidate["normalized_value_clip"], candidate["normalized_value_clip"])*values[:, 2:]
            if not np.isfinite(normalized).all() or not np.isin(normalized[:, 2:], [0, 1]).all():
                raise ValueError("Invalid natural observation mask or normalized actual input")
            result[band+"_"+phase] = torch.from_numpy(normalized)
    return result


def prepare_offsets(fitting, extra, specification):
    if not set(extra.group_key) <= set(fitting.group_key) or set(extra.row_key) & set(fitting.row_key):
        raise ValueError("Extra actual targets must belong exclusively to the native fitting people")
    native_offsets = torch.empty((len(fitting), 21), dtype=torch.float64)
    extra_offsets = torch.empty((len(extra), 21), dtype=torch.float64)
    inner = []
    for fit, val in GroupKFold(n_splits=3).split(fitting, groups=fitting.group_key):
        train, validation = fitting.iloc[fit], fitting.iloc[val]
        extra_indexes = np.flatnonzero(extra.group_key.isin(set(validation.group_key)))
        if set(train.group_key) & set(validation.group_key):
            raise ValueError("Inner baseline leaked fitting-person truth")
        model = WarmPersonalBorg({"steps": 0}).fit(train, specification)
        native_offsets[val] = base_features(model, validation)[1]
        if len(extra_indexes):
            extra_offsets[extra_indexes] = base_features(model, extra.iloc[extra_indexes])[1]
        inner.append({"fit_row_keys": train.row_key.tolist(), "validation_row_keys": validation.row_key.tolist(),
                      "extra_validation_row_keys": extra.iloc[extra_indexes].row_key.tolist()})
    base = WarmPersonalBorg({"steps": 0}).fit(fitting, specification)
    return {"base": base, "fit_logits": native_offsets, "extra_logits": extra_offsets, "inner_folds": inner,
            "fit_row_keys": fitting.row_key.tolist(), "extra_row_keys": extra.row_key.tolist()}


class PhysiologyEncoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.fast = nn.Sequential(nn.Conv1d(4, 8, 9, stride=4, padding=4), nn.ReLU(),
            nn.Conv1d(8, 8, 5, stride=4, padding=2), nn.ReLU(), nn.AdaptiveAvgPool1d(4), nn.Flatten())
        self.slow = nn.Sequential(nn.Conv1d(4, 4, 5, stride=2, padding=2), nn.ReLU(),
            nn.Conv1d(4, 4, 3, stride=2, padding=1), nn.ReLU(), nn.AdaptiveAvgPool1d(4), nn.Flatten())

    def forward(self, windows, phase):
        return torch.cat((self.fast(windows["fast_"+phase]), self.slow(windows["slow_"+phase])), dim=1)


class WaveformResidual(nn.Module):
    def __init__(self, context_size, paired):
        super().__init__()
        self.encoder, self.paired = PhysiologyEncoder(), paired
        self.corrector = nn.Sequential(nn.Linear(context_size+21+(144 if paired else 48), 16), nn.Tanh(), nn.Linear(16, 21))
        nn.init.zeros_(self.corrector[-1].weight)
        nn.init.zeros_(self.corrector[-1].bias)

    def forward(self, windows, context, offsets):
        current = self.encoder(windows, "current")
        if self.paired:
            prior = self.encoder(windows, "prior")
            current = torch.cat((current, prior, current-prior), dim=1)
        return self.corrector(torch.cat((context, torch.softmax(offsets, dim=1).float(), current), dim=1)).to(offsets.dtype)


class PhysiologyPairBorg:
    def __init__(self, candidate):
        self.candidate = candidate

    def fit(self, frame, extra, native_windows, extra_windows, specification, cached=None, observer=None):
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        if not set(extra.group_key) <= set(frame.group_key) or set(extra.row_key) & set(frame.row_key):
            raise ValueError("Extra public reports leaked another person's outcome or duplicate the canonical cohort")
        cache = prepare_offsets(frame, extra, specification) if cached is None else cached
        if cache["fit_row_keys"] != frame.row_key.tolist() or cache["extra_row_keys"] != extra.row_key.tolist():
            raise ValueError("Nested offsets belong to a different original/extra fitting cohort")
        self.base = cache["base"]
        self.base.model.requires_grad_(False)
        self.input_features = list(specification["features"])
        include = self.candidate["include_extra_actual_reports"]
        fitting = pd.concat([frame, extra], ignore_index=True) if include else frame
        windows = {name: np.concatenate([native_windows[name], extra_windows[name]], axis=0) if include else value.copy()
                   for name, value in native_windows.items()}
        if len(fitting) != len(windows["fast_current"]):
            raise ValueError("Actual waveform inputs and current report targets misaligned")
        offsets = torch.cat([cache["fit_logits"], cache["extra_logits"]], dim=0) if include else cache["fit_logits"]
        context = base_features(self.base, fitting)[0].float()
        current = fitting.label.str.removeprefix("Borg ").to_numpy(int)
        prior = fitting.prior_borg.to_numpy(int)
        target = torch.tensor(current-prior+10, dtype=torch.long)
        if observer is not None:
            observer(fitting[self.input_features].copy(), {name: value.copy() for name, value in windows.items()}, current.copy(), prior.copy())
        normalized = normalize_windows(windows, self.candidate)
        torch.manual_seed(self.candidate["random_seed"])
        self.network = WaveformResidual(context.shape[1], self.candidate["waveform_view"] == "current_and_prior_waveforms")
        optimizer = torch.optim.AdamW(self.network.parameters(), lr=self.candidate["learning_rate"], weight_decay=self.candidate["weight_decay"])
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, self.candidate["epochs"]), eta_min=.0003)
        self.loss_endpoints = []
        for epoch in range(self.candidate["epochs"]):
            optimizer.zero_grad(set_to_none=True)
            correction = self.network(normalized, context, offsets)
            classification = nn.functional.cross_entropy(offsets+correction, target)
            penalty = self.candidate["correction_penalty"]*correction.square().mean()
            loss = classification+penalty
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite real waveform likelihood")
            loss.backward()
            if any(p.grad is not None and not torch.isfinite(p.grad).all() for p in self.network.parameters()):
                raise ValueError("Nonfinite waveform gradient")
            nn.utils.clip_grad_norm_(self.network.parameters(), 5.)
            optimizer.step()
            scheduler.step()
            if epoch in (0, self.candidate["epochs"]-1):
                self.loss_endpoints.append({"classification": float(classification.detach()), "penalty": float(penalty.detach()), "total": float(loss.detach())})
        self.network.requires_grad_(False).eval()
        for parameter in self.network.parameters():
            parameter.grad = None
        self.training_summary = {"original_native_targets": len(frame), "additional_actual_targets": len(extra) if include else 0,
            "total_actual_targets": len(fitting), "inner_participant_folds": 3, "synthetic_examples": 0,
            "artificial_input_masks": 0, "missing_native_cases_dropped": 0}
        return self

    def predict(self, frame, windows):
        with torch.no_grad():
            context, offsets = base_features(self.base, frame)
            correction = self.network(normalize_windows(windows, self.candidate), context.float(), offsets)
            logits = offsets+correction
            if not torch.isfinite(logits).all():
                raise ValueError("Nonfinite native Borg prediction")
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
    if set(validation.group_key) & set(fitting.group_key) or set(eligible.group_key) & set(validation.group_key):
        raise ValueError("Native or extra report leaked validation people")
    specification = core_candidate(manifest)
    identity = {"signature": signature, "fold_number": number, "fit_row_keys": fitting.row_key.tolist(),
                "validation_row_keys": validation.row_key.tolist(), "extra_eligible_row_keys": eligible.row_key.tolist()}
    cache_path = DIRECTORY/"bases"/f"fold-{number}.joblib"
    metadata_path = cache_path.with_suffix(".json")
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text())
        if any(metadata.get(k) != v for k, v in identity.items()) or metadata["cache_sha256"] != digest(cache_path):
            raise ValueError("Frozen nested native/extra offset cache changed")
        cached = joblib.load(cache_path)
    else:
        cached = prepare_offsets(fitting, eligible, specification)
        joblib.dump(cached, cache_path)
        metadata_path.write_text(json.dumps({**identity, "cache_sha256": digest(cache_path), "inner_folds": cached["inner_folds"]}, indent=2)+"\n", encoding="utf-8")
    native_windows = select_windows(arrays, lookup, fitting.row_key)
    extra_windows = select_windows(arrays, lookup, eligible.row_key)
    validation_windows = select_windows(arrays, lookup, validation.row_key)
    for c in plan()[2:]:
        path = DIRECTORY/"folds"/f"{c['id']}-fold-{number}.json"
        row_identity = {**identity, "candidate": c}
        if path.exists():
            saved = json.loads(path.read_text())
            if any(saved.get(k) != v for k, v in row_identity.items()):
                raise ValueError("Saved real waveform recipe changed")
        else:
            model = PhysiologyPairBorg(c).fit(fitting, eligible, native_windows, extra_windows, specification, cached)
            predicted = model.predict(validation, validation_windows)
            saved = {**row_identity, "predicted": predicted.tolist(), "loss_endpoints": model.loss_endpoints, "training_summary": model.training_summary}
            path.write_text(json.dumps(saved, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        print(f"Real physiological recipe {c['id']} fold {number+1}/5 complete", flush=True)
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
    for sub in ("bases", "folds"):
        (DIRECTORY/sub).mkdir(exist_ok=True)
    report = {**signature, "version": 1, "status": "running", "plan": plan(), "results": [],
        "train_row_keys": train.row_key.tolist(), "evaluation_denominator": len(train), "test_denominator": len(test),
        "target_accuracy": .8, "minimum_cv_for_new_test_evaluation": .65, "test_used_for_selection": False,
        "previous_benchmark_results_are_published": True, "synthetic_examples": 0,
        "policy": "Exact original Borg. One paired physiological input per real report; no resampling into extra labeled windows, interpolation, artificial masks or validation-driven stopping. Extra 56 actual outcomes are fitting-person-only. Native baseline offsets exclude each report's person in three inner folds. Baseline normalization fits canonical outer-fitting rows only. Shared waveform normalization is per query using actual earlier-window statistics, with current-only fallback when the earlier sensor is absent. Missing cases retained. Test evaluation requires frozen CV>=.65 recipe."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k, v in signature.items()) or old["plan"] != plan() or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen real physiology study changed")
        report = old
    else:
        save(report)
    if report["status"] == "complete":
        return report
    folds = list(GroupKFold(n_splits=5).split(train, groups=train.group_key))
    with ProcessPoolExecutor(max_workers=2, initializer=worker_initialize) as pool:
        futures = [pool.submit(compute_fold, (number, fit, val)) for number, (fit, val) in enumerate(folds)]
        for future in as_completed(futures):
            print(f"All real physiological recipes completed fold {future.result()+1}/5", flush=True)
    previous = json.loads(PREVIOUS.read_text())
    for c in plan():
        if any(r["candidate"] == c for r in report["results"]):
            continue
        if c["algorithm"] == "previous_real_control":
            old = next(r for r in previous["results"] if r["candidate"]["id"] == c["parent_candidate_id"])
            predicted, details = np.asarray(old["oof_predictions"]), []
        else:
            predicted, details = np.empty(len(train), dtype=object), []
            for number, (_, val) in enumerate(folds):
                saved = json.loads((DIRECTORY/"folds"/f"{c['id']}-fold-{number}.json").read_text())
                predicted[val] = saved["predicted"]
                details.append(saved)
        scores = [float(accuracy_score(train.iloc[val].label, predicted[val])) for _, val in folds]
        report["results"].append({"candidate": c, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
            "pooled_oof_accuracy": float(accuracy_score(train.label, predicted)), "oof_predictions": predicted.tolist(), "folds": details})
        winner = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=winner["candidate"]["id"], best_cv_accuracy=winner["accuracy_mean"])
        save(report)
        print(f"Real physiological recipe {c['id']}: CV={np.mean(scores):.6f}", flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
