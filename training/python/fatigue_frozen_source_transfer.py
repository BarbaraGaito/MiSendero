"""External-only pretraining followed by a frozen native-Borg correction.

Four study-specific continuous CR10 heads pretrain a shared sensor encoder.
That encoder and its normalization then freeze. Original participant-grouped
classifiers can use its estimates/embedding without altering external weights
or combining post-task outcomes with momentary classification labels.
"""
from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import joblib
import numpy as np
import torch
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from torch import nn
from threadpoolctl import threadpool_limits

from fatigue_dynamics_experiment import DynamicsClassifier
from fatigue_features import RESEARCH
from fatigue_joint_sources import DIRECTORY as SOURCE_DIRECTORY, SENSOR_FEATURES, load as source_inputs
from fatigue_probability import validate_calibration
from fatigue_spectral_correction import GENERATED, base_context, corrected_predictions, fit_corrector, inner_context
from fatigue_spectral_experiment import load_inputs as spectral_inputs
from fatigue_warm_sgd import core_candidate
from public_sources import digest

DIRECTORY = RESEARCH / "frozen-source-transfer-80-v1"


class SourceNetwork(nn.Module):
    def __init__(self, n_features, domains):
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(n_features, 16), nn.Tanh(), nn.Linear(16, 8), nn.Tanh())
        self.heads = nn.ModuleDict({name: nn.Linear(8, 1) for name in domains})

    def prediction(self, values, name):
        return 10.*torch.sigmoid(self.heads[name](self.encoder(values)).squeeze(1))


def source_plan():
    return [{"id": f"source-encoder-{i:03d}", "feature_set": name, "features": columns,
             "epochs": epochs, "loss_weighting": weighting, "widths": [16, 8], "learning_rate": .003,
             "weight_decay": .05, "loss": "native_CR10_Huber_separate_study_heads", "random_seed": 42}
            for i, (name, columns, epochs, weighting) in enumerate((name, columns, epochs, weighting)
                for name, columns in (("hr", ["hr_last", "hr_history_mean"]), ("hr_gait", SENSOR_FEATURES))
                for epochs in (200, 600) for weighting in ("equal_domains", "original_report_frequency"))]


class FrozenSourceEncoder:
    def __init__(self, candidate):
        self.candidate = candidate

    def transform(self, frame):
        values = self.scaler.transform(self.imputer.transform(frame[self.candidate["features"]]))
        return torch.tensor(values, dtype=torch.float32)

    def fit(self, external):
        values = external["borg_native"].to_numpy(float)
        if not np.isfinite(values).all() or np.any((values < 0) | (values > 10)) or not external["row_key"].is_unique:
            raise ValueError("Unique actual continuous native CR10 source reports required")
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        torch.manual_seed(42)
        self.imputer = SimpleImputer(strategy="median", keep_empty_features=True, add_indicator=True)
        self.scaler = StandardScaler().fit(self.imputer.fit_transform(external[self.candidate["features"]]))
        self.domains = sorted(external["source_domain"].unique())
        x = self.transform(external)
        self.model = SourceNetwork(x.shape[1], self.domains)
        batches, counts = {}, {}
        for name in self.domains:
            mask = external["source_domain"].eq(name).to_numpy(copy=True)
            batches[name] = x[mask], torch.tensor(values[mask], dtype=torch.float32)
            counts[name] = int(mask.sum())
        self.report_counts = counts
        self.native_fractional_report_count = int((values != np.rint(values)).sum())
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=.003, weight_decay=.05)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=self.candidate["epochs"], eta_min=.0003)
        endpoints = []
        for epoch in range(self.candidate["epochs"]):
            optimizer.zero_grad(set_to_none=True)
            losses = {name: nn.functional.smooth_l1_loss(self.model.prediction(features, name), target, beta=1.)
                      for name, (features, target) in batches.items()}
            if self.candidate["loss_weighting"] == "equal_domains":
                loss = torch.stack(list(losses.values())).mean()
            else:
                loss = sum(losses[name]*counts[name] for name in self.domains)/len(external)
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite external pretraining loss")
            loss.backward()
            if any(p.grad is None or not torch.isfinite(p.grad).all() for p in self.model.parameters()):
                raise ValueError("Nonfinite external encoder gradient")
            nn.utils.clip_grad_norm_(self.model.parameters(), 5.)
            optimizer.step()
            scheduler.step()
            if epoch == 0 or epoch == self.candidate["epochs"]-1:
                endpoints.append(float(loss.detach()))
        self.loss_endpoints = endpoints
        for parameter in self.model.parameters():
            parameter.grad = None
        self.model.requires_grad_(False).eval()
        return self

    def extract(self, frame):
        if any(p.requires_grad for p in self.model.parameters()):
            raise ValueError("The source encoder must stay frozen")
        with torch.no_grad():
            values = self.transform(frame)
            encoded = self.model.encoder(values).numpy()
            scores = {name: self.model.prediction(values, name).numpy() for name in self.domains}
        result = {f"frozen_z_{i:02d}": encoded[:, i] for i in range(8)}
        result.update({"frozen_rpe_"+name: value for name, value in scores.items()})
        result["frozen_mean_rpe"] = np.mean(list(scores.values()), axis=0)
        result["frozen_mean_minus_prior"] = result["frozen_mean_rpe"]-frame["prior_borg"].to_numpy(float)
        if not all(np.isfinite(value).all() for value in result.values()):
            raise ValueError("Nonfinite external frozen representation")
        return result


def added_feature_names(domains):
    return [*[f"frozen_z_{i:02d}" for i in range(8)], *["frozen_rpe_"+name for name in sorted(domains)],
            "frozen_mean_rpe", "frozen_mean_minus_prior"]


def add_features(frame, context, encoder):
    if context.shape != (len(frame), len(GENERATED)):
        raise ValueError("Cross-fitted baseline context missing")
    return frame.assign(**{name: context[:, i] for i, name in enumerate(GENERATED)}, **encoder.extract(frame))


class FrozenTransferBorg:
    def __init__(self, candidate, encoder=None):
        self.candidate, self.encoder = candidate, encoder

    def fit(self, frame, core_specification):
        with threadpool_limits(limits=1):
            self.base = DynamicsClassifier(core_specification).fit(frame)
            if self.candidate["algorithm"] == "control":
                return self
            context, self.inner_folds = inner_context(frame, core_specification)
            data = add_features(frame, context, self.encoder)
            target = frame["label"].str.removeprefix("Borg ").to_numpy(int)-context[:, 0].astype(int)
            self.corrector = fit_corrector(data, target, self.candidate)
        return self

    def predict(self, frame):
        validate_calibration(frame)
        if self.candidate["algorithm"] == "control":
            return self.base.predict(frame)
        context = base_context(self.base, frame)
        data = add_features(frame, context, self.encoder)
        scores = self.corrector.predict_proba(data[self.candidate["features"]])
        return corrected_predictions(context[:, 0], scores, self.corrector.classes_, self.candidate["zero_margin"])


def plan(manifest, domains):
    prior = core_candidate(manifest)["features"]
    candidates = [{"id": "frozen-transfer-000", "algorithm": "control", "feature_set": "incumbent_control", "features": prior}]
    columns = prior+GENERATED+added_feature_names(domains)
    for source in source_plan():
        for c in (.001, .01, .1):
            for margin in (0., .1, .25):
                candidates.append({"id": f"frozen-transfer-{len(candidates):03d}", "algorithm": "logistic",
                                   "feature_set": "frozen_"+source["feature_set"], "features": columns, "params": {"C": c, "max_iter": 3000},
                                   "zero_margin": margin, "source_encoder": source})
    return candidates


def fingerprint(manifest, source_manifest):
    helpers = ("fatigue_joint_sources.py", "fatigue_spectral_correction.py", "fatigue_spectral_experiment.py", "fatigue_dynamics_experiment.py", "fatigue_warm_sgd.py")
    return {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"],
            "spectral_dataset_sha256": manifest["spectral_dataset_sha256"], "spectral_provenance_sha256": manifest["spectral_provenance_sha256"],
            "source_dataset_sha256": source_manifest["dataset_sha256"], "source_provenance_sha256": digest(SOURCE_DIRECTORY / "provenance.json"),
            "external_splits": source_manifest["external_splits"], "core_candidate": core_candidate(manifest),
            "dependency_code_sha256": {name: digest(Path(__file__).with_name(name)) for name in helpers},
            "software_versions": {name: importlib.metadata.version(name) for name in ("torch", "numpy", "pandas", "scikit-learn", "joblib")}}


def select():
    frame, train, _, manifest, _ = spectral_inputs()
    external, source_manifest = source_inputs()
    candidates = plan(manifest, source_manifest["domains"])
    signature = {**fingerprint(manifest, source_manifest), "plan": candidates, "source_plan": source_plan(), "train_row_keys": train["row_key"].tolist()}
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "running", "results": [], "test_used_for_selection": False,
              "previous_benchmark_results_are_published": True, "external_test_used": False, "synthetic_rows": 0,
              "source_fitting_reports": 520, "native_momentary_target_merge": False, "evaluation_denominator": 487, "test_denominator": 179,
              "minimum_cv_for_new_test_evaluation": .65,
              "policy": "Encoder and normalization fit only 520 original external fitting reports and then freeze. Separate study-specific continuous CR10 heads preserve source/outcome context. GeoFatigue residual labels use inner participant-held-out baseline predictions. All original query cases remain; no current/future Borg predictor or external holdout label."}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    if path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
        if any(report.get(k) != v for k, v in signature.items()):
            raise ValueError("Frozen source-pretraining study changed")
    if not report["results"]:
        path.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    encoders = {}
    for spec in source_plan():
        directory = DIRECTORY / "encoders" / spec["id"]
        model_path, meta_path = directory / "model.joblib", directory / "descriptor.json"
        evidence = {"signature": fingerprint(manifest, source_manifest), "candidate": spec}
        if meta_path.exists():
            saved = json.loads(meta_path.read_text())
            if any(saved.get(k) != v for k, v in evidence.items()) or digest(model_path) != saved["model_sha256"]:
                raise ValueError("Saved frozen source encoder changed")
            encoder = joblib.load(model_path)
        else:
            encoder = FrozenSourceEncoder(spec).fit(external)
            directory.mkdir(parents=True, exist_ok=True)
            joblib.dump(encoder, model_path)
            meta_path.write_text(json.dumps({**evidence, "model_sha256": digest(model_path), "loss_endpoints": encoder.loss_endpoints,
                                            "actual_source_report_counts": encoder.report_counts, "native_fractional_reports": encoder.native_fractional_report_count,
                                            "all_network_parameters_frozen": not any(p.requires_grad for p in encoder.model.parameters())}, indent=2)+"\n", encoding="utf-8")
        encoders[spec["id"]] = encoder
        print(f"Source-only encoder {len(encoders)}/{len(source_plan())}: 520 original reports, frozen", flush=True)
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    packed, base_predictions, evidence = [], np.empty(len(train), dtype=object), []
    with threadpool_limits(limits=1):
        for fit, val in folds:
            fitting, validation = train.iloc[fit], train.iloc[val]
            if set(fitting["group_key"]) & set(validation["group_key"]):
                raise ValueError("Frozen transfer base leaked validation people")
            context_fit, inner = inner_context(fitting, signature["core_candidate"])
            base = DynamicsClassifier(signature["core_candidate"]).fit(fitting)
            context_val = base_context(base, validation)
            packed.append((fitting, validation, context_fit, context_val))
            base_predictions[val] = [f"Borg {i}" for i in context_val[:, 0].astype(int)]
            evidence.append({"fit_row_keys": fitting["row_key"].tolist(), "validation_row_keys": validation["row_key"].tolist(),
                             "inner_folds": inner, "fit_context": context_fit.tolist(), "validation_context": context_val.tolist()})
    expected = json.loads((RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
    expected = next(r["oof_predictions"] for r in expected["results"] if r["candidate"]["id"] == "alternative-023")
    np.testing.assert_array_equal(base_predictions, expected)
    report["folds"] = evidence
    cached = {}
    for candidate in candidates:
        if any(r["candidate"] == candidate for r in report["results"]):
            continue
        predicted = base_predictions.copy()
        if candidate["algorithm"] != "control":
            key = (candidate["source_encoder"]["id"], candidate["params"]["C"])
            if key not in cached:
                encoder = encoders[key[0]]
                values = []
                for fitting, validation, context_fit, context_val in packed:
                    fit_data, val_data = add_features(fitting, context_fit, encoder), add_features(validation, context_val, encoder)
                    target = fitting["label"].str.removeprefix("Borg ").to_numpy(int)-context_fit[:, 0].astype(int)
                    with threadpool_limits(limits=1):
                        model = fit_corrector(fit_data, target, candidate)
                    values.append((model.predict_proba(val_data[candidate["features"]]), model.classes_))
                cached[key] = values
            for (_, val), (_, _, _, context), (scores, classes) in zip(folds, packed, cached[key]):
                predicted[val] = corrected_predictions(context[:, 0], scores, classes, candidate["zero_margin"])
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
                                  "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)), "oof_predictions": predicted.tolist(),
                                  "changed_decisions": int((predicted != base_predictions).sum())})
        best = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"],
                      status="complete" if len(report["results"]) == len(candidates) else "running")
        content = json.dumps(report, indent=2, allow_nan=False)+"\n"
        path.with_suffix(".tmp").write_text(content, encoding="utf-8")
        path.write_text(content, encoding="utf-8")
        print(f"Frozen source transfer {len(report['results'])}/{len(candidates)}: exact CV={np.mean(scores):.6f}, best={best['accuracy_mean']:.6f}", flush=True)


if __name__ == "__main__":
    select()
