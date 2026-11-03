"""Compare current learned movement with its exact observed-prior anchor."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import torch
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

import fatigue_runner_transfer as parent
from fatigue_runner_anchor_windows import DIRECTORY as ANCHORS
from public_sources import digest

DIRECTORY = parent.RESEARCH / "runner-anchor-transfer-80-v1"
ADDED = [f"runner_anchor_delta_{i:02d}" for i in range(17)] + [f"runner_anchor_coverage_{i}" for i in range(3)] + ["runner_anchor_pair_available"]


def paired_features(frame, current, reference, encoder):
    if len(frame) != len(current) or len(frame) != len(reference):
        raise ValueError("Current and actual-prior sensor inputs must align with every native query")
    current, reference = parent.validate_windows(current), parent.validate_windows(reference)
    now, old = encoder.extract(current), encoder.extract(reference)
    observed = (current[:, 3:].sum(axis=(1, 2)) > 0) & (reference[:, 3:].sum(axis=(1, 2)) > 0)
    change = now[:, :17]-old[:, :17]
    change[~observed] = 0.
    paired = np.column_stack((change, old[:, 17:], observed.astype(np.float32)))
    return frame.assign(**{name: now[:, i] for i, name in enumerate(parent.GENERATED)},
                        **{name: paired[:, i] for i, name in enumerate(ADDED)})


class AnchoredRunnerBorg:
    def __init__(self, candidate, encoder):
        self.candidate, self.encoder = candidate, encoder

    def fit(self, frame, current, reference, specifications):
        c = self.candidate
        base = specifications[c["member"]]
        self.input_features = list(base["features"])
        native = {**base, "id": c["id"], "feature_set": "current_and_observed_prior_runner_features",
                  "features": base["features"]+parent.GENERATED+ADDED}
        if c["member"] == "core":
            native["params"] = {**base["params"], "alpha": c["alpha"]}
        data = paired_features(frame, current, reference, self.encoder)
        with threadpool_limits(limits=1):
            self.model = (parent.DynamicsClassifier(native) if c["member"] == "core" else parent.CatBoostBorg(native)).fit(data)
        return self

    def predict(self, frame, current, reference):
        parent.validate_calibration(frame)
        return self.model.predict(paired_features(frame, current, reference, self.encoder))


def plan(parent_selection):
    trained = max((r for r in parent_selection["results"] if r["candidate"]["algorithm"] != "control"
                   and r["candidate"]["encoder"]["epochs"] > 0), key=lambda r: r["accuracy_mean"])
    selected = trained["candidate"]["encoder"]
    encoders = [parent.encoder_plan()[0], selected]
    result = [{"id": "anchor-transfer-000", "algorithm": "parent_control", "parent_candidate_id": "runner-transfer-000", "member": "core"},
              {"id": "anchor-transfer-001", "algorithm": "parent_control", "parent_candidate_id": "runner-transfer-001", "member": "cat"}]
    for encoder in encoders:
        for member, alpha in (("core", 10.), ("core", 30.), ("cat", None)):
            matched = next(r["candidate"]["id"] for r in parent_selection["results"] if r["candidate"]["algorithm"] != "control"
                and r["candidate"]["encoder"] == encoder and r["candidate"]["member"] == member and r["candidate"]["alpha"] == alpha)
            result.append({"id": f"anchor-transfer-{len(result):03d}", "algorithm": "paired_frozen_runner_features",
                "member": member, "alpha": alpha, "encoder": encoder, "matched_current_only_recipe": matched})
    return result


def load_inputs():
    inputs = parent.load_inputs()
    frame, train, test, _, _, members, _, _, _, _, current, window_manifest = inputs
    parent_path = parent.DIRECTORY / "selection.json"
    selection = json.loads(parent_path.read_text())
    signature = parent.fingerprint(members, window_manifest)
    if (selection["status"] != "complete" or len(selection["results"]) != 17
            or any(selection.get(k) != v for k, v in signature.items()) or selection["plan"] != parent.plan()
            or selection["train_row_keys"] != train["row_key"].tolist()):
        raise ValueError("The completed current-window parent selection changed")
    manifest = json.loads((ANCHORS / "provenance.json").read_text())
    if (manifest["feature_code_sha256"] != digest(Path(__file__).with_name("fatigue_runner_anchor_windows.py"))
            or manifest["prior_npz_sha256"] != digest(ANCHORS / "prior.npz")
            or manifest["current_window_provenance_sha256"] != digest(parent.WINDOWS / "provenance.json")
            or manifest["current_npz_sha256"] != window_manifest["native_npz_sha256"]
            or manifest["native_queries_retained"] != 666 or manifest["native_borg_targets_stored"] != 0):
        raise ValueError("Prepared causal prior anchors changed or contain current outcomes")
    for name, sha in manifest["dependency_code_sha256"].items():
        if digest(Path(__file__).with_name(name)) != sha:
            raise ValueError("Prior-anchor preparation helper changed")
    with np.load(ANCHORS / "prior.npz", allow_pickle=False) as data:
        if set(data.files) != {"windows", "row_keys"}:
            raise ValueError("Unexpected label or identity input in anchor tensors")
        reference = data["windows"]
        np.testing.assert_array_equal(data["row_keys"], frame["row_key"].to_numpy(str))
    return frame, train, test, members, window_manifest, current, reference, manifest, selection


def fingerprint(members, windows):
    return {"code_sha256": digest(Path(__file__)), "parent_fingerprint": parent.fingerprint(members, windows),
        "parent_selection_sha256": digest(parent.DIRECTORY / "selection.json"),
        "anchor_provenance_sha256": digest(ANCHORS / "provenance.json"),
        "anchor_npz_sha256": digest(ANCHORS / "prior.npz")}


def save(report):
    path = DIRECTORY / "selection.json"
    text = json.dumps(report, indent=2, allow_nan=False)+"\n"
    path.with_suffix(".tmp").write_text(text, encoding="utf-8")
    path.write_text(text, encoding="utf-8")


def select():
    frame, train, test, members, windows, current, reference, anchors, previous = load_inputs()
    signature, candidates = fingerprint(members, windows), plan(previous)
    DIRECTORY.mkdir(exist_ok=True)
    (DIRECTORY / "folds").mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "status": "running", "plan": candidates,
        "train_row_keys": train["row_key"].tolist(), "results": [], "target_accuracy": .8,
        "evaluation_denominator": len(train), "test_denominator": len(test), "test_used_for_selection": False,
        "previous_benchmark_results_are_published": True, "minimum_cv_for_new_test_evaluation": .65,
        "native_cases_with_both_sensor_windows": anchors["both_windows_with_any_signal"],
        "new_native_borg_targets": 0, "source_protocol_states_are_native_borg_labels": False,
        "encoder_selection_rule": "Use the frozen encoder from the best source-trained grouped-CV parent recipe and the matching untrained encoder. This is a post-selection follow-up on reused training CV; no held-out outcome is consulted.",
        "policy": "Keep all original native cases. Reference inputs end at their exact actual prior report time. Missing current/reference windows remain explicitly masked; their learned difference is neutral zero with an availability flag. Pretrained encoders stay frozen. No target interpolation, invented report clocks, source-state-to-Borg mapping, current/future labels or easier denominator."}
    if path.exists():
        old = json.loads(path.read_text())
        if (any(old.get(k) != v for k, v in signature.items()) or old["plan"] != candidates
                or old["train_row_keys"] != report["train_row_keys"]):
            raise ValueError("Frozen paired-input study changed")
        report = old
    else:
        save(report)
    if report["status"] == "complete":
        return report
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    encoders = {}
    for candidate in candidates:
        if candidate["algorithm"] == "parent_control":
            continue
        specification = candidate["encoder"]
        if specification["id"] in encoders:
            continue
        path = parent.DIRECTORY / "encoders" / (specification["id"]+".joblib")
        descriptor = json.loads(path.with_suffix(".json").read_text())
        if descriptor["signature"] != signature["parent_fingerprint"] or descriptor["candidate"] != specification or descriptor["model_sha256"] != digest(path):
            raise ValueError("Frozen source-only encoder changed")
        encoders[specification["id"]] = joblib.load(path)
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for c in candidates:
        if any(r["candidate"] == c for r in report["results"]):
            continue
        predicted, details = np.empty(len(train), dtype=object), []
        if c["algorithm"] == "parent_control":
            inherited = next(r for r in previous["results"] if r["candidate"]["id"] == c["parent_candidate_id"])
            predicted[:] = inherited["oof_predictions"]
        else:
            for number, (fit, val) in enumerate(folds):
                fitting, validation = train.iloc[fit], train.iloc[val]
                identity = {"signature": signature, "candidate": c, "fit_row_keys": fitting["row_key"].tolist(), "validation_row_keys": validation["row_key"].tolist()}
                path = DIRECTORY / "folds" / f"{c['id']}-fold-{number}.json"
                if path.exists():
                    saved = json.loads(path.read_text())
                    if any(saved.get(k) != v for k, v in identity.items()):
                        raise ValueError("Saved paired-input fold changed")
                else:
                    model = AnchoredRunnerBorg(c, encoders[c["encoder"]["id"]]).fit(fitting, current[fitting.index], reference[fitting.index], members["member_specifications"])
                    decision = model.predict(validation, current[validation.index], reference[validation.index])
                    saved = {**identity, "predicted": decision.tolist()}
                    path.write_text(json.dumps(saved, indent=2)+"\n", encoding="utf-8")
                predicted[val] = saved["predicted"]
                details.append(saved)
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        report["results"].append({"candidate": c, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
            "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)), "oof_predictions": predicted.tolist(), "folds": details})
        best = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"])
        save(report)
        print(f"Paired runner transfer {len(report['results'])}/{len(candidates)} {c['id']}: CV={np.mean(scores):.6f}, best={best['accuracy_mean']:.6f}", flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
