"""Source-only F/NF pretraining, then frozen features for native Borg models."""
from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import joblib
import numpy as np
import torch
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits
from torch import nn

from fatigue_catboost import CatBoostBorg
from fatigue_dynamics_experiment import DynamicsClassifier
from fatigue_features import RESEARCH
from fatigue_probability import validate_calibration
from fatigue_runner_windows import DIRECTORY as WINDOWS, LENGTH
from fatigue_view_ensemble import load_inputs as member_inputs, fingerprint as member_fingerprint
from public_sources import digest

DIRECTORY = RESEARCH / "runner-supervised-transfer-80-v1"
ALLOWED_PEOPLE = {"006", "007", "008", "011", "012", "013", "014", "015", "017", "018", "019", "020", "021", "022", "023"}
GENERATED = [f"runner_z_{stat}_{i:02d}" for stat in ("mean", "std") for i in range(8)] + ["runner_source_logit"] + [f"runner_coverage_{i}" for i in range(3)]


def validate_windows(windows):
    windows = np.asarray(windows, dtype=np.float32)
    if (windows.ndim != 3 or windows.shape[1:] != (6, LENGTH) or not np.isfinite(windows).all()
            or not np.isin(windows[:, 3:], [0., 1.]).all()
            or np.any(windows[:, :3] * (1-windows[:, 3:]) != 0)):
        raise ValueError("Finite dimensionless windows with explicit masks and zero missing-value padding required")
    return windows


def source_weights(states, people):
    states, people = np.asarray(states), np.asarray(people)
    if (states.shape != people.shape or states.ndim != 1 or not len(states)
            or not np.isin(states, [0, 1]).all() or not set(people) <= ALLOWED_PEOPLE):
        raise ValueError("Only predeclared fitting runner people and original binary protocol states may pretrain")
    pairs = {(person, state): int(((people == person) & (states == state)).sum()) for person in sorted(set(people)) for state in (0, 1)}
    if not all(pairs.values()):
        raise ValueError("Each source person requires both actual F and NF conditions")
    weights = np.asarray([len(states)/(len(pairs)*pairs[p, int(y)]) for p, y in zip(people, states)], dtype=np.float32)
    return weights


class SourceNetwork(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = nn.Sequential(nn.Conv1d(6, 16, 5, stride=2, padding=2), nn.GELU(),
            nn.Conv1d(16, 32, 5, stride=2, padding=2), nn.GELU(), nn.Conv1d(32, 8, 3, stride=2, padding=1), nn.GELU())
        self.head = nn.Linear(16, 1)

    def representation(self, x):
        value = self.encoder(x)
        return torch.cat((value.mean(dim=2), value.std(dim=2, correction=0)), dim=1)

    def forward(self, x):
        return self.head(self.representation(x)).squeeze(1)


def encoder_plan():
    settings = [(0, .001), (30, .001), (30, .003), (90, .001), (90, .003)]
    return [{"id": f"runner-encoder-{i:03d}", "epochs": epochs, "learning_rate": rate,
             "weight_decay": .01, "batch_size": 64, "block_dropout_probability": .1,
             "objective": "source_protocol_F_NF_BCE_only", "random_seed": 42}
            for i, (epochs, rate) in enumerate(settings)]


class FrozenRunnerEncoder:
    def __init__(self, candidate):
        self.candidate = candidate

    def fit(self, windows, states, people):
        windows = validate_windows(windows)
        weights = source_weights(states, people)
        if len(windows) != len(states):
            raise ValueError("Source windows and protocol states are not aligned")
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        torch.manual_seed(42)
        generator = torch.Generator().manual_seed(42)
        network = SourceNetwork()
        optimizer = torch.optim.AdamW(network.parameters(), lr=self.candidate["learning_rate"], weight_decay=self.candidate["weight_decay"])
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, self.candidate["epochs"]), eta_min=.0001)
        x, y, weight = torch.from_numpy(windows.copy()), torch.as_tensor(states, dtype=torch.float32), torch.from_numpy(weights)
        self.loss_endpoints, steps = [], 0
        for epoch in range(self.candidate["epochs"]):
            total = 0.
            for indexes in torch.randperm(len(x), generator=generator).split(self.candidate["batch_size"]):
                batch = x[indexes].clone()
                hidden = (torch.rand((len(indexes), 1, LENGTH//8), generator=generator) < self.candidate["block_dropout_probability"]).repeat_interleave(8, dim=2)
                batch[:, :3] *= ~hidden
                batch[:, 3:] *= ~hidden
                optimizer.zero_grad(set_to_none=True)
                losses = nn.functional.binary_cross_entropy_with_logits(network(batch), y[indexes], reduction="none")
                loss = (losses*weight[indexes]).mean()
                if not torch.isfinite(loss):
                    raise ValueError("Nonfinite source protocol likelihood")
                loss.backward()
                if any(p.grad is None or not torch.isfinite(p.grad).all() for p in network.parameters()):
                    raise ValueError("Nonfinite source protocol gradients")
                nn.utils.clip_grad_norm_(network.parameters(), 5.)
                optimizer.step()
                total += float((losses.detach()*weight[indexes]).sum())
                steps += 1
            scheduler.step()
            if epoch in (0, self.candidate["epochs"]-1):
                self.loss_endpoints.append(total/float(weight.sum()))
        self.network = network.requires_grad_(False).eval()
        for parameter in self.network.parameters():
            parameter.grad = None
        self.source_summary = {"prepared_source_windows": len(windows), "prepared_source_people": sorted(set(people)),
            "gradient_steps": steps, "source_windows_used_for_gradient_updates": len(windows) if steps else 0,
            "person_and_condition_weight_total": float(weights.sum()), "native_borg_targets_used": 0}
        return self

    def extract(self, windows):
        windows = validate_windows(windows)
        if any(p.requires_grad or p.grad is not None for p in self.network.parameters()):
            raise ValueError("Source representation must remain frozen during native fitting/inference")
        with torch.no_grad():
            values = torch.from_numpy(windows.copy())
            representation = self.network.representation(values)
            logit = self.network.head(representation)
            result = torch.cat((representation, logit), dim=1).numpy()
        result[windows[:, 3:].sum(axis=(1, 2)) == 0] = 0.
        return np.column_stack((result, windows[:, 3:].mean(axis=2)))


def add_features(frame, windows, encoder):
    if len(frame) != len(windows):
        raise ValueError("Native input rows and runtime causal windows must align")
    value = encoder.extract(windows)
    return frame.assign(**{name: value[:, i] for i, name in enumerate(GENERATED)})


class RunnerTransferBorg:
    def __init__(self, candidate, encoder=None):
        self.candidate, self.encoder = candidate, encoder

    def fit(self, frame, windows, specifications):
        c = self.candidate
        base = specifications[c["member"]]
        self.input_features = list(base["features"])
        native = dict(base)
        data = frame
        if c["algorithm"] != "control":
            if self.encoder is None:
                raise ValueError("An independently source-fitted frozen encoder is required")
            data = add_features(frame, windows, self.encoder)
            native.update(id=c["id"], feature_set="frozen_runner_representation", features=base["features"]+GENERATED)
            if c["member"] == "core":
                native["params"] = {**base["params"], "alpha": c["alpha"]}
        with threadpool_limits(limits=1):
            self.model = (DynamicsClassifier(native) if c["member"] == "core" else CatBoostBorg(native)).fit(data)
        return self

    def predict(self, frame, windows):
        validate_calibration(frame)
        data = frame if self.candidate["algorithm"] == "control" else add_features(frame, windows, self.encoder)
        return self.model.predict(data)


def load_inputs():
    frame, train, test, manifest, protocol, _, members, winners = member_inputs()
    path = WINDOWS / "provenance.json"
    evidence = json.loads(path.read_text())
    if evidence["feature_code_sha256"] != digest(Path(__file__).with_name("fatigue_runner_windows.py")):
        raise ValueError("Frozen dimensionless window construction changed")
    for name, sha in evidence["dependency_code_sha256"].items():
        if digest(Path(__file__).with_name(name)) != sha:
            raise ValueError("Dimensionless window helper changed")
    for name, key in (("source.npz", "source_npz_sha256"), ("native.npz", "native_npz_sha256")):
        if digest(WINDOWS / name) != evidence[key]:
            raise ValueError("Prepared dimensionless signal inputs changed")
    with np.load(WINDOWS / "source.npz", allow_pickle=False) as source:
        x, states, people = source["windows"], source["protocol_states"], source["participants"]
    with np.load(WINDOWS / "native.npz", allow_pickle=False) as native:
        windows = native["windows"]
        np.testing.assert_array_equal(native["row_keys"], frame["row_key"].to_numpy(str))
    if set(people) != ALLOWED_PEOPLE or len(windows) != 666 or evidence["native_borg_targets_stored"] != 0:
        raise ValueError("Source people or original native queries changed")
    return frame, train, test, manifest, protocol, members, winners, x, states, people, windows, evidence


def plan():
    result = [{"id": "runner-transfer-000", "algorithm": "control", "member": "core"},
              {"id": "runner-transfer-001", "algorithm": "control", "member": "cat"}]
    for encoder in encoder_plan():
        for member, alpha in (("core", 10.), ("core", 30.), ("cat", None)):
            result.append({"id": f"runner-transfer-{len(result):03d}", "algorithm": "frozen_runner_features",
                           "member": member, "alpha": alpha, "encoder": encoder})
    return result


def fingerprint(members, evidence):
    return {"code_sha256": digest(Path(__file__)), "window_provenance_sha256": digest(WINDOWS / "provenance.json"),
        "source_npz_sha256": evidence["source_npz_sha256"], "native_npz_sha256": evidence["native_npz_sha256"],
        "member_fingerprint": member_fingerprint(members),
        "dependency_code_sha256": {n: digest(Path(__file__).with_name(n)) for n in ("fatigue_runner_windows.py", "fatigue_dynamics_experiment.py", "fatigue_catboost.py")},
        "software_versions": {n: importlib.metadata.version(n) for n in ("torch", "numpy", "pandas", "scikit-learn", "catboost", "joblib")}}


def save(report):
    path = DIRECTORY / "selection.json"
    text = json.dumps(report, indent=2, allow_nan=False)+"\n"
    path.with_suffix(".tmp").write_text(text, encoding="utf-8")
    path.write_text(text, encoding="utf-8")


def select():
    frame, train, test, manifest, _, members, winners, x, states, people, windows, evidence = load_inputs()
    signature, candidates = fingerprint(members, evidence), plan()
    DIRECTORY.mkdir(exist_ok=True)
    for name in ("encoders", "folds"):
        (DIRECTORY / name).mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "status": "running", "plan": candidates, "encoder_plan": encoder_plan(),
        "train_row_keys": train["row_key"].tolist(), "results": [], "target_accuracy": .8,
        "evaluation_denominator": len(train), "test_denominator": len(test), "test_used_for_selection": False,
        "previous_benchmark_results_are_published": True, "minimum_cv_for_new_test_evaluation": .65,
        "source_protocol_windows": len(x), "source_fitting_people": len(set(people)), "new_native_borg_targets": 0,
        "source_protocol_states_are_native_borg_labels": False, "native_queries_with_any_signal": evidence["native_queries_with_any_signal"],
        "policy": "Source-only protocol F/NF BCE with equal weight per source person and condition. All encoder parameters stay frozen for native Borg learning. Compare an identical untrained encoder and the two previous point controls. No source state-to-Borg conversion, native-case exclusions, current/future predictor, target interpolation or test tuning."}
    if path.exists():
        old = json.loads(path.read_text())
        if (any(old.get(k) != v for k, v in signature.items()) or old["plan"] != candidates
                or old["train_row_keys"] != report["train_row_keys"] or old["encoder_plan"] != encoder_plan()):
            raise ValueError("Frozen source transfer study inputs, code or plan changed")
        report = old
    else:
        save(report)
    if report["status"] == "complete":
        return report
    encoders = {}
    for specification in encoder_plan():
        model_path = DIRECTORY / "encoders" / (specification["id"]+".joblib")
        descriptor_path = model_path.with_suffix(".json")
        if descriptor_path.exists():
            descriptor = json.loads(descriptor_path.read_text())
            if descriptor["signature"] != signature or descriptor["candidate"] != specification or descriptor["model_sha256"] != digest(model_path):
                raise ValueError("Saved fitting-only source encoder changed")
            encoder = joblib.load(model_path)
        else:
            encoder = FrozenRunnerEncoder(specification).fit(x, states, people)
            joblib.dump(encoder, model_path)
            descriptor = {"signature": signature, "candidate": specification, "model_sha256": digest(model_path),
                          "source_summary": encoder.source_summary, "loss_endpoints": encoder.loss_endpoints}
            descriptor_path.write_text(json.dumps(descriptor, indent=2)+"\n", encoding="utf-8")
        encoders[specification["id"]] = encoder
        print(f"Source protocol encoder {specification['id']} verified; epochs={specification['epochs']}", flush=True)
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    for candidate in candidates:
        if any(r["candidate"] == candidate for r in report["results"]):
            continue
        predicted, details = np.empty(len(train), dtype=object), []
        for number, (fit, val) in enumerate(folds):
            fitting, validation = train.iloc[fit], train.iloc[val]
            identity = {"signature": signature, "candidate": candidate, "fit_row_keys": fitting["row_key"].tolist(), "validation_row_keys": validation["row_key"].tolist()}
            fold_path = DIRECTORY / "folds" / f"{candidate['id']}-fold-{number}.json"
            if fold_path.exists():
                saved = json.loads(fold_path.read_text())
                if any(saved.get(k) != v for k, v in identity.items()):
                    raise ValueError("Saved runner-transfer fitting/validation fold changed")
            else:
                encoder = None if candidate["algorithm"] == "control" else encoders[candidate["encoder"]["id"]]
                model = RunnerTransferBorg(candidate, encoder).fit(fitting, windows[fitting.index], members["member_specifications"])
                decision = model.predict(validation, windows[validation.index])
                saved = {**identity, "predicted": decision.tolist()}
                fold_path.write_text(json.dumps(saved, indent=2)+"\n", encoding="utf-8")
            predicted[val] = saved["predicted"]
            details.append(saved)
        if candidate["algorithm"] == "control":
            if candidate["member"] == "cat":
                expected = winners["cat"]["oof_predictions"]
            else:
                original = json.loads((RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
                expected = next(r["oof_predictions"] for r in original["results"] if r["candidate"]["id"] == "alternative-023")
            np.testing.assert_array_equal(predicted, expected)
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
            "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)), "oof_predictions": predicted.tolist(), "folds": details})
        winner = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=winner["candidate"]["id"], best_cv_accuracy=winner["accuracy_mean"])
        save(report)
        print(f"Runner transfer {len(report['results'])}/{len(candidates)}: {candidate['id']} CV={np.mean(scores):.6f}, best={winner['accuracy_mean']:.6f}", flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
