"""Low-dimensional source scores plus causal HR changes, exact native Borg."""
from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import joblib
import numpy as np
import torch
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

import fatigue_runner_anchor_transfer as paired
from public_sources import digest

DIRECTORY = paired.parent.RESEARCH / "compact-physiology-80-v1"
HR = ["hr_last", "hr_change_after_prior", "hr_recent_slope"]
SCORES = ["compact_current_logit", "compact_logit_delta", "compact_logit_delta_per_minute",
          "compact_current_coverage", "compact_prior_coverage", "compact_pair_available"]
_RUNTIME = None


def compact_scores(frame, current, reference, encoder):
    paired.parent.validate_calibration(frame)
    if len(frame) != len(current) or len(frame) != len(reference):
        raise ValueError("All original query rows require aligned current/prior sensor inputs")
    current, reference = paired.parent.validate_windows(current), paired.parent.validate_windows(reference)
    now, old = encoder.extract(current), encoder.extract(reference)
    has_now = current[:, 3:].sum(axis=(1, 2)) > 0
    has_old = reference[:, 3:].sum(axis=(1, 2)) > 0
    available = has_now & has_old
    delta = np.where(available, now[:, 16]-old[:, 16], np.nan)
    values = np.column_stack((np.where(has_now, now[:, 16], np.nan), delta,
        delta/frame["prior_age_minutes"].to_numpy(float), current[:, 3:].mean(axis=(1, 2)),
        reference[:, 3:].mean(axis=(1, 2)), available.astype(float)))
    return frame.assign(**{name: values[:, i] for i, name in enumerate(SCORES)})


class CompactPhysiologyBorg:
    def __init__(self, candidate, encoder=None):
        self.candidate, self.encoder = candidate, encoder

    def feature_frame(self, frame, current, reference):
        return frame if self.candidate["mode"] == "hr_only" else compact_scores(frame, current, reference, self.encoder)

    def fit(self, frame, current, reference, specifications):
        c = self.candidate
        base = specifications[c["member"]]
        self.input_features = list(dict.fromkeys(base["features"]+(HR if c["mode"] != "gait_only" else [])))
        columns = self.input_features+(SCORES if c["mode"] != "hr_only" else [])
        if set(columns) & {"label", "row_key", "group_key"}:
            raise ValueError("Current outcomes and participant/query identifiers cannot be predictors")
        native = {**base, "id": c["id"], "feature_set": "compact_causal_physiology", "features": columns}
        with threadpool_limits(limits=1):
            data = self.feature_frame(frame, current, reference)
            self.model = (paired.parent.DynamicsClassifier(native) if c["member"] == "core" else paired.parent.CatBoostBorg(native)).fit(data)
        return self

    def predict(self, frame, current, reference):
        paired.parent.validate_calibration(frame)
        return self.model.predict(self.feature_frame(frame, current, reference))


def plan():
    recipes = [("hr_only", "core", None), ("hr_only", "cat", None),
        ("gait_only", "cat", "runner-encoder-004"),
        ("gait_hr", "core", "runner-encoder-000"), ("gait_hr", "cat", "runner-encoder-000"),
        ("gait_hr", "core", "runner-encoder-004"), ("gait_hr", "cat", "runner-encoder-004"),
        ("gait_hr", "cat", "runner-encoder-001")]
    result = [{"id": "compact-000", "algorithm": "parent_control", "parent_candidate_id": "runner-transfer-000"},
              {"id": "compact-001", "algorithm": "parent_control", "parent_candidate_id": "runner-transfer-001"}]
    for mode, member, encoder in recipes:
        result.append({"id": f"compact-{len(result):03d}", "algorithm": "compact_physiology",
                       "mode": mode, "member": member, "encoder_id": encoder})
    return result


def load_inputs():
    inputs = paired.load_inputs()
    previous = json.loads((paired.DIRECTORY / "selection.json").read_text())
    if previous["status"] != "complete" or previous["plan"] != paired.plan(inputs[-1]):
        raise ValueError("Completed high-dimensional paired parent changed")
    return inputs


def fingerprint(inputs):
    _, _, _, members, window_manifest, _, _, _, _ = inputs
    return {"code_sha256": digest(Path(__file__)), "paired_input_fingerprint": paired.fingerprint(members, window_manifest),
        "paired_selection_sha256": digest(paired.DIRECTORY / "selection.json"),
        "worker_processes": 2, "hr_predictors": HR, "compact_source_predictors": SCORES,
        "encoder_selection": "004 has the lowest source fitting BCE; 001 came from the previously best source-trained native CV recipe; 000 is its initialized-weight control. No held-out native outcome used."}


def worker_initialize():
    global _RUNTIME
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    inputs = load_inputs()
    parent_signature = fingerprint(inputs)["paired_input_fingerprint"]["parent_fingerprint"]
    encoders = {}
    for key in ("runner-encoder-000", "runner-encoder-001", "runner-encoder-004"):
        path = paired.parent.DIRECTORY / "encoders" / (key+".joblib")
        descriptor = json.loads(path.with_suffix(".json").read_text())
        if descriptor["signature"] != parent_signature or descriptor["model_sha256"] != digest(path):
            raise ValueError("Source-only frozen encoder changed")
        encoders[key] = joblib.load(path)
    _RUNTIME = inputs, encoders


def compute_fold(job):
    candidate, number, fit, val, signature = job
    inputs, encoders = _RUNTIME
    _, train, _, members, _, current, reference, _, _ = inputs
    fitting, validation = train.iloc[fit], train.iloc[val]
    if set(fitting["group_key"]) & set(validation["group_key"]):
        raise ValueError("Native fold leaked validation people")
    encoder = encoders.get(candidate["encoder_id"])
    model = CompactPhysiologyBorg(candidate, encoder).fit(fitting, current[fitting.index], reference[fitting.index], members["member_specifications"])
    predicted = model.predict(validation, current[validation.index], reference[validation.index])
    return {"signature": signature, "candidate": candidate, "fold_number": number,
        "fit_row_keys": fitting["row_key"].tolist(), "validation_row_keys": validation["row_key"].tolist(),
        "predicted": predicted.tolist()}


def save(report):
    path = DIRECTORY / "selection.json"
    text = json.dumps(report, indent=2, allow_nan=False)+"\n"
    path.with_suffix(".tmp").write_text(text, encoding="utf-8")
    path.write_text(text, encoding="utf-8")


def select():
    inputs = load_inputs()
    _, train, test, _, _, _, _, anchors, previous = inputs
    signature, candidates = fingerprint(inputs), plan()
    DIRECTORY.mkdir(exist_ok=True)
    (DIRECTORY / "folds").mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "status": "running", "plan": candidates,
        "train_row_keys": train["row_key"].tolist(), "results": [], "target_accuracy": .8,
        "evaluation_denominator": len(train), "test_denominator": len(test), "test_used_for_selection": False,
        "previous_benchmark_results_are_published": True, "minimum_cv_for_new_test_evaluation": .65,
        "new_native_borg_targets": 0, "source_protocol_states_are_native_borg_labels": False,
        "original_queries_with_both_sensor_windows": anchors["both_windows_with_any_signal"],
        "policy": "Use six source-score/availability features instead of large latent vectors, and three already causal HR predictors. Genuine missing scores stay NaN and are imputed only inside fitting folds (or handled by CatBoost). Keep all original cases. Source encoders remain frozen. Two independent worker processes compute disjoint fitting folds; only the parent writes reports. No current/future target predictor, source-to-Borg conversion or test tuning."}
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k, v in signature.items()) or old["plan"] != candidates or old["train_row_keys"] != report["train_row_keys"]:
            raise ValueError("Frozen compact experiment code, source or plan changed")
        report = old
    else:
        save(report)
    if report["status"] == "complete":
        return report
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    cache, jobs = {}, []
    for c in candidates:
        if c["algorithm"] == "parent_control":
            continue
        for number, (fit, val) in enumerate(folds):
            output = DIRECTORY / "folds" / f"{c['id']}-fold-{number}.json"
            if output.exists():
                saved = json.loads(output.read_text())
                if (saved["signature"] != signature or saved["candidate"] != c
                        or saved["fit_row_keys"] != train.iloc[fit]["row_key"].tolist()
                        or saved["validation_row_keys"] != train.iloc[val]["row_key"].tolist()):
                    raise ValueError("Cached compact physiology fold changed")
                cache[c["id"], number] = saved
            else:
                jobs.append((c, number, fit, val, signature))
    def collect():
        while len(report["results"]) < len(candidates):
            c = candidates[len(report["results"])]
            if c["algorithm"] == "parent_control":
                inherited = next(r for r in previous["results"] if r["candidate"]["id"] == c["parent_candidate_id"])
                predicted, details = np.asarray(inherited["oof_predictions"]), []
            else:
                if not all((c["id"], i) in cache for i in range(5)):
                    break
                predicted, details = np.empty(len(train), dtype=object), []
                for number, (_, val) in enumerate(folds):
                    saved = cache[c["id"], number]
                    predicted[val] = saved["predicted"]
                    details.append(saved)
            scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
            report["results"].append({"candidate": c, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
                "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)), "oof_predictions": predicted.tolist(), "folds": details})
            best = max(report["results"], key=lambda r: r["accuracy_mean"])
            report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"])
            save(report)
            print(f"Compact physiology {len(report['results'])}/10 {c['id']}: CV={np.mean(scores):.6f}, best={best['accuracy_mean']:.6f}", flush=True)
    collect()
    if jobs:
        with ProcessPoolExecutor(max_workers=2, initializer=worker_initialize) as executor:
            pending = [executor.submit(compute_fold, job) for job in jobs]
            for future in as_completed(pending):
                saved = future.result()
                key = saved["candidate"]["id"], saved["fold_number"]
                output = DIRECTORY / "folds" / f"{key[0]}-fold-{key[1]}.json"
                output.write_text(json.dumps(saved, indent=2, allow_nan=False)+"\n", encoding="utf-8")
                cache[key] = saved
                print(f"Compact fold complete {key[0]} {key[1]+1}/5", flush=True)
                collect()
    if len(report["results"]) != 10:
        raise ValueError("Some frozen compact recipes did not finish")
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
