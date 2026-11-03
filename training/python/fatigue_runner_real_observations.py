"""Source movement transfer fitted only on unchanged real public windows.

No artificial missing blocks, history views, generated sensor examples or
synthetic-pretrained weights. Source F/NF stays an auxiliary protocol task.
"""
from __future__ import annotations

import importlib.metadata
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import joblib
import numpy as np
import torch
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits
from torch import nn

import fatigue_catboost as catboost
import fatigue_runner_transfer as helpers
from fatigue_warm_sgd import core_candidate
from public_sources import ROOT, digest

DIRECTORY = helpers.RESEARCH / "runner-real-observations-80-v1"
POLICY = ROOT / "docs/fatigue-80-2026-10-25/public-real-data-policy.json"
PARENT = helpers.RESEARCH / "source-transition-teachers-80-v1/selection.json"
_RUNTIME = None


def encoder_plan():
    return [{"id": f"real-runner-encoder-{i:03d}", "epochs": epochs, "learning_rate": rate,
        "weight_decay": .01, "batch_size": 64, "random_seed": 42,
        "objective": "original_source_F_NF_protocol_BCE", "artificial_input_transformations": False}
        for i, (epochs, rate) in enumerate(((0, .001), (30, .001), (30, .003), (90, .001), (90, .003)))]


class RealRunnerEncoder(helpers.FrozenRunnerEncoder):
    def fit(self, windows, states, people, batch_observer=None):
        windows = helpers.validate_windows(windows)
        weights = helpers.source_weights(states, people)
        if len(windows) != len(states) or self.candidate["artificial_input_transformations"] is not False:
            raise ValueError("Aligned real source observations without artificial input transformations required")
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        torch.manual_seed(self.candidate["random_seed"])
        generator = torch.Generator().manual_seed(self.candidate["random_seed"])
        network = helpers.SourceNetwork()
        optimizer = torch.optim.AdamW(network.parameters(), lr=self.candidate["learning_rate"], weight_decay=self.candidate["weight_decay"])
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, self.candidate["epochs"]), eta_min=.0001)
        x, y, weight = torch.from_numpy(windows.copy()), torch.as_tensor(states, dtype=torch.float32), torch.from_numpy(weights)
        self.loss_endpoints, steps = [], 0
        for epoch in range(self.candidate["epochs"]):
            total, seen = 0., []
            for indexes in torch.randperm(len(x), generator=generator).split(self.candidate["batch_size"]):
                batch = x[indexes]
                if batch_observer is not None:
                    batch_observer(epoch, indexes.numpy().copy(), batch.numpy().copy(), y[indexes].numpy().copy())
                optimizer.zero_grad(set_to_none=True)
                losses = nn.functional.binary_cross_entropy_with_logits(network(batch), y[indexes], reduction="none")
                loss = (losses*weight[indexes]).mean()
                if not torch.isfinite(loss):
                    raise ValueError("Nonfinite real-source protocol likelihood")
                loss.backward()
                if any(p.grad is None or not torch.isfinite(p.grad).all() for p in network.parameters()):
                    raise ValueError("Nonfinite real-source protocol gradients")
                nn.utils.clip_grad_norm_(network.parameters(), 5.)
                optimizer.step()
                total += float((losses.detach()*weight[indexes]).sum())
                seen.extend(indexes.tolist())
                steps += 1
            if sorted(seen) != list(range(len(x))):
                raise ValueError("An epoch did not use exactly the original source windows")
            scheduler.step()
            if epoch in (0, self.candidate["epochs"]-1):
                self.loss_endpoints.append(total/float(weight.sum()))
        self.network = network.requires_grad_(False).eval()
        for parameter in self.network.parameters():
            parameter.grad = None
        self.source_summary = {"prepared_source_windows": len(windows), "prepared_source_people": sorted(set(people)),
            "gradient_steps": steps, "source_windows_used_for_gradient_updates": len(windows) if steps else 0,
            "person_and_condition_weight_total": float(weights.sum()), "native_borg_targets_used": 0,
            "artificial_sensor_rows": 0, "artificial_history_rows": 0, "source_input_masking": False,
            "every_epoch_uses_each_original_window_once": True}
        return self


class RealRunnerBorg:
    def __init__(self, candidate, encoder):
        self.candidate, self.encoder = candidate, encoder

    def fit(self, frame, windows, specifications):
        c = self.candidate
        base = specifications[c["member"]]
        self.input_features = list(base["features"])
        data = helpers.add_features(frame, windows, self.encoder)
        np.testing.assert_array_equal(data["row_key"], frame["row_key"])
        np.testing.assert_array_equal(data["label"], frame["label"])
        native = {**base, "id": c["id"], "features": self.input_features+helpers.GENERATED}
        if c["member"] == "core":
            native["params"] = {**base["params"], "alpha": c["alpha"]}
        with threadpool_limits(limits=1):
            self.model = (helpers.DynamicsClassifier(native) if c["member"] == "core" else helpers.CatBoostBorg(native)).fit(data)
        return self

    def predict(self, frame, windows):
        helpers.validate_calibration(frame)
        return self.model.predict(helpers.add_features(frame, windows, self.encoder))


def load_inputs():
    # Load only original real-report native models. No history-view dataset or
    # model is needed to initialize or fit either native estimator.
    frame, train, test, manifest, _ = catboost.load_inputs()
    cat_path = catboost.DIRECTORY/"selection.json"
    cat = json.loads(cat_path.read_text())
    if (cat["status"] != "complete" or cat["test_used_for_selection"] or cat["plan"] != catboost.plan(manifest)
            or cat["dataset_sha256"] != manifest["dataset_sha256"]
            or cat["code_sha256"] != digest(Path(catboost.__file__)) or cat["train_row_keys"] != train.row_key.tolist()):
        raise ValueError("Frozen real-report CatBoost source changed")
    winner = max(cat["results"], key=lambda r: r["accuracy_mean"])
    if winner["candidate"]["id"] != cat["winner_id"]:
        raise ValueError("CatBoost differs from its original training-only CV winner")
    specifications = {"core": core_candidate(manifest), "cat": winner["candidate"]}
    policy = json.loads(POLICY.read_text())
    if not policy["applies_to_all_further_fitting_and_model_selection"] or DIRECTORY.name in policy["archive_only_studies_with_artificial_input_training"]:
        raise ValueError("This study must comply with the real public-data policy")
    path = helpers.WINDOWS/"provenance.json"
    evidence = json.loads(path.read_text())
    if evidence["feature_code_sha256"] != digest(Path(__file__).with_name("fatigue_runner_windows.py")):
        raise ValueError("Verified real public window preparation changed")
    for name, sha in evidence["dependency_code_sha256"].items():
        if digest(Path(__file__).with_name(name)) != sha:
            raise ValueError("Verified public window helper changed")
    for name, key in (("source.npz", "source_npz_sha256"), ("native.npz", "native_npz_sha256")):
        if digest(helpers.WINDOWS/name) != evidence[key]:
            raise ValueError("Real public signal snapshot changed")
    with np.load(helpers.WINDOWS/"source.npz", allow_pickle=False) as data:
        if set(data.files) != {"windows", "protocol_states", "participants"}:
            raise ValueError("Unexpected target field in source tensors")
        source, states, people = data["windows"], data["protocol_states"], data["participants"]
    with np.load(helpers.WINDOWS/"native.npz", allow_pickle=False) as data:
        if set(data.files) != {"windows", "row_keys"}:
            raise ValueError("Current native outcomes entered signal tensors")
        windows = data["windows"]
        np.testing.assert_array_equal(data["row_keys"], frame.row_key.to_numpy(str))
    if (len(train) != 487 or len(test) != 179 or set(train.group_key) & set(test.group_key)
            or set(people) != helpers.ALLOWED_PEOPLE or len(source) != 330 or len(windows) != 666
            or evidence["native_borg_targets_stored"] != 0 or evidence["interpolated_signals"]):
        raise ValueError("Real source observations, native holdout or missingness policy changed")
    members = {"native_dataset_sha256": manifest["dataset_sha256"], "member_specifications": specifications,
        "cat_selection_sha256": digest(cat_path), "window_provenance_sha256": digest(path)}
    return frame, train, test, members, source, states, people, windows, evidence


def plan():
    result = [{"id": "real-runner-000", "algorithm": "parent_control", "parent_candidate_id": "transition-000"},
              {"id": "real-runner-001", "algorithm": "parent_control", "parent_candidate_id": "transition-001"}]
    for encoder in encoder_plan():
        for member, alpha in (("core", 10.), ("core", 30.), ("cat", None)):
            result.append({"id": f"real-runner-{len(result):03d}", "algorithm": "unchanged_public_source_features",
                "member": member, "alpha": alpha, "encoder_id": encoder["id"]})
    return result


def fingerprint(inputs):
    members, evidence = inputs[3], inputs[-1]
    return {"code_sha256": digest(Path(__file__)), **members, "public_real_data_policy_sha256": digest(POLICY),
        "source_receipt_sha256": evidence["source_receipt_sha256"], "source_npz_sha256": evidence["source_npz_sha256"],
        "native_npz_sha256": evidence["native_npz_sha256"], "previous_selection_sha256": digest(PARENT),
        "dependency_code_sha256": {name: digest(Path(__file__).with_name(name)) for name in
            ("fatigue_runner_transfer.py", "fatigue_runner_windows.py", "fatigue_catboost.py", "fatigue_probability.py", "fatigue_warm_sgd.py", "fatigue_dynamics_experiment.py")},
        "software_versions": {name: importlib.metadata.version(name) for name in ("torch", "numpy", "pandas", "scikit-learn", "catboost", "joblib")}, "worker_processes": 2}


def save(report):
    path = DIRECTORY/"selection.json"
    text = json.dumps(report, indent=2, allow_nan=False)+"\n"
    path.with_suffix(".tmp").write_text(text, encoding="utf-8")
    path.write_text(text, encoding="utf-8")


def worker_initialize():
    global _RUNTIME
    inputs = load_inputs()
    signature = fingerprint(inputs)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    encoders = {}
    for c in encoder_plan():
        path = DIRECTORY/"encoders"/(c["id"]+".joblib")
        descriptor = json.loads(path.with_suffix(".json").read_text())
        if descriptor["signature"] != signature or descriptor["candidate"] != c or descriptor["model_sha256"] != digest(path):
            raise ValueError("Frozen real-source encoder changed")
        encoders[c["id"]] = joblib.load(path)
    _RUNTIME = inputs, signature, encoders


def compute_fold(job):
    c, number, fit, val = job
    inputs, signature, encoders = _RUNTIME
    _, train, _, members, _, _, _, windows, _ = inputs
    fitting, validation = train.iloc[fit], train.iloc[val]
    if set(fitting.group_key) & set(validation.group_key):
        raise ValueError("Native fitting leaked validation people")
    model = RealRunnerBorg(c, encoders[c["encoder_id"]]).fit(fitting, windows[fitting.index], members["member_specifications"])
    predicted = model.predict(validation, windows[validation.index])
    return {"candidate": c, "signature": signature, "fold_number": number, "fit_row_keys": fitting.row_key.tolist(),
        "validation_row_keys": validation.row_key.tolist(), "predicted": predicted.tolist()}


def select():
    inputs = load_inputs()
    _, train, test, _, source, states, people, _, _ = inputs
    signature = fingerprint(inputs)
    DIRECTORY.mkdir(exist_ok=True)
    for name in ("encoders", "folds"):
        (DIRECTORY/name).mkdir(exist_ok=True)
    report = {**signature, "version": 1, "status": "running", "plan": plan(), "encoder_plan": encoder_plan(), "results": [],
        "train_row_keys": train.row_key.tolist(), "target_accuracy": .8, "evaluation_denominator": len(train),
        "test_denominator": len(test), "test_used_for_selection": False, "minimum_cv_for_new_test_evaluation": .65,
        "previous_benchmark_results_are_published": True, "new_native_borg_targets": 0,
        "source_protocol_states_are_native_borg_labels": False, "synthetic_training_rows": 0,
        "artificial_input_masking": False, "artificial_history_views": False,
        "policy": "Only actual unchanged public source windows supervise original F/NF protocol, then weights freeze. Source windows are repeated optimization passes, not new Borg observations. Native estimators receive only the 487 original real reports in participant-disjoint folds. No generated signals, artificial input blocks/history views, synthetic pretraining, source-to-native target conversion, easier denominator or test tuning."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k, v in signature.items()) or old["plan"] != plan() or old["encoder_plan"] != encoder_plan() or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen real-public source experiment changed")
        report = old
    else:
        save(report)
    if report["status"] == "complete":
        return report
    for c in encoder_plan():
        path = DIRECTORY/"encoders"/(c["id"]+".joblib")
        if path.with_suffix(".json").exists():
            d = json.loads(path.with_suffix(".json").read_text())
            if d["signature"] != signature or d["candidate"] != c or d["model_sha256"] != digest(path):
                raise ValueError("Saved real-source encoder changed")
        else:
            encoder = RealRunnerEncoder(c).fit(source, states, people)
            joblib.dump(encoder, path)
            d = {"signature": signature, "candidate": c, "model_sha256": digest(path),
                 "source_summary": encoder.source_summary, "loss_endpoints": encoder.loss_endpoints}
            path.with_suffix(".json").write_text(json.dumps(d, indent=2)+"\n", encoding="utf-8")
        print(f"Real public source encoder {c['id']} ready, epochs={c['epochs']}, no input augmentation", flush=True)
    folds = list(GroupKFold(n_splits=5).split(train, groups=train.group_key))
    jobs = []
    for c in report["plan"]:
        if c["algorithm"] == "parent_control":
            continue
        for number, (fit, val) in enumerate(folds):
            path = DIRECTORY/"folds"/f"{c['id']}-fold-{number}.json"
            if path.exists():
                saved = json.loads(path.read_text())
                if (saved["signature"] != signature or saved["candidate"] != c or saved["fold_number"] != number
                        or saved["fit_row_keys"] != train.iloc[fit].row_key.tolist()
                        or saved["validation_row_keys"] != train.iloc[val].row_key.tolist()):
                    raise ValueError("Saved real-public native fold changed")
            else:
                jobs.append((c, number, fit, val))
    if jobs:
        with ProcessPoolExecutor(max_workers=2, initializer=worker_initialize) as pool:
            futures = [pool.submit(compute_fold, job) for job in jobs]
            for future in as_completed(futures):
                saved = future.result()
                path = DIRECTORY/"folds"/f"{saved['candidate']['id']}-fold-{saved['fold_number']}.json"
                path.write_text(json.dumps(saved, indent=2)+"\n", encoding="utf-8")
                print(f"Real public native fold {saved['candidate']['id']} {saved['fold_number']+1}/5 complete", flush=True)
    previous = json.loads(PARENT.read_text())
    for c in report["plan"]:
        if any(r["candidate"] == c for r in report["results"]):
            continue
        if c["algorithm"] == "parent_control":
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
        best = max(report["results"], key=lambda r:r["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"])
        save(report)
        print(f"Real public recipe {len(report['results'])}/17 {c['id']}: CV={np.mean(scores):.6f}", flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
