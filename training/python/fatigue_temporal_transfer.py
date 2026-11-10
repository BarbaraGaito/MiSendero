"""External masked phone-signal pretraining, then frozen native Borg correction.

WHAMAP f-level values are never read. Reconstruction targets are original
observed signal bins. Native query tensors contain only the available past;
the original Borg labels and participant holdout remain unchanged.
"""
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

from fatigue_dynamics_experiment import DynamicsClassifier
from fatigue_features import RESEARCH
from fatigue_probability import validate_calibration
from fatigue_spectral_correction import GENERATED, base_context, corrected_predictions, fit_corrector, inner_context
from fatigue_spectral_experiment import load_inputs as spectral_inputs
from fatigue_temporal_windows import DIRECTORY as WINDOW_DIRECTORY, LENGTH, STATISTICS
from fatigue_warm_sgd import core_candidate
from public_sources import digest

DIRECTORY = RESEARCH / "temporal-transfer-80-v1"
EMBEDDING_NAMES = [f"temporal_z_{stat}_{i:02d}" for stat in ("mean", "std") for i in range(8)]
FITTING_PEOPLE = {"subject_01", "subject_03", "subject_04", "subject_05", "subject_06", "subject_07", "subject_08", "subject_10"}


class MaskedAutoencoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = nn.Sequential(nn.Conv1d(6, 16, 5, stride=2, padding=2), nn.GELU(),
                                     nn.Conv1d(16, 32, 5, stride=2, padding=2), nn.GELU(),
                                     nn.Conv1d(32, 8, 3, stride=2, padding=1), nn.GELU())
        self.decoder = nn.Sequential(nn.ConvTranspose1d(8, 32, 4, stride=2, padding=1), nn.GELU(),
                                     nn.ConvTranspose1d(32, 16, 4, stride=2, padding=1), nn.GELU(),
                                     nn.ConvTranspose1d(16, 3, 4, stride=2, padding=1))

    def forward(self, values):
        return self.decoder(self.encoder(values))


def masked_batch(batch, generator, probability):
    """Hide random eight-bin blocks; supervise only observed, hidden bins."""
    observed = batch[:, 3:]
    blocks = torch.rand((len(batch), 1, LENGTH//8), generator=generator) < probability
    hidden = blocks.repeat_interleave(8, dim=2).expand(-1, 3, -1)*observed
    visible = observed*(1.-hidden)
    inputs = torch.cat((torch.where(visible.bool(), batch[:, :3], 0.), visible), dim=1)
    targets = torch.where(observed.bool(), batch[:, :3], 0.)
    return inputs, targets, hidden


def reconstruction_loss(predicted, target, supervised):
    if predicted.shape != target.shape or supervised.shape != target.shape or not supervised.sum() > 0:
        raise ValueError("Observed masked reconstruction targets are required")
    return ((predicted-target).square()*supervised).sum()/supervised.sum()


def validate_windows(windows):
    windows = np.asarray(windows, dtype=np.float32)
    if (windows.ndim != 3 or windows.shape[1:] != (6, LENGTH) or not np.isfinite(windows).all()
            or not np.isin(windows[:, 3:], [0., 1.]).all()
            or np.any(windows[:, :3][windows[:, 3:] == 0] != 0)):
        raise ValueError("Finite signal windows with explicit observation masks required")
    return windows


def encoder_plan():
    return [{"id": f"temporal-encoder-{i:03d}", "epochs": epochs, "mask_probability": probability,
             "mask_block_bins": 8, "batch_size": 64, "learning_rate": .003, "weight_decay": .01,
             "random_seed": 42, "objective": "observed_masked_signal_MSE", "input_channels": 6,
             "encoder_channels": [16, 32, 8], "window_samples": LENGTH}
            for i, (epochs, probability) in enumerate((epochs, p) for epochs in (20, 60) for p in (.15, .35))]


class FrozenTemporalEncoder:
    def __init__(self, candidate):
        self.candidate = candidate

    def fit(self, windows, participants):
        windows = validate_windows(windows)
        if len(participants) != len(windows) or not len(windows) or not set(participants) <= FITTING_PEOPLE:
            raise ValueError("Only the predeclared WHAMAP fitting participants may pretrain")
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        torch.manual_seed(42)
        generator = torch.Generator().manual_seed(42)
        values = torch.from_numpy(windows.copy())
        network = MaskedAutoencoder()
        optimizer = torch.optim.AdamW(network.parameters(), lr=.003, weight_decay=.01)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=self.candidate["epochs"], eta_min=.0003)
        self.loss_endpoints = []
        for epoch in range(self.candidate["epochs"]):
            total, denominator = 0., 0
            order = torch.randperm(len(values), generator=generator)
            for positions in order.split(64):
                inputs, targets, supervision = masked_batch(values[positions], generator, self.candidate["mask_probability"])
                if not supervision.sum() > 0:
                    continue
                optimizer.zero_grad(set_to_none=True)
                loss = reconstruction_loss(network(inputs), targets, supervision)
                if not torch.isfinite(loss):
                    raise ValueError("Nonfinite observed signal pretraining loss")
                loss.backward()
                if any(p.grad is None or not torch.isfinite(p.grad).all() for p in network.parameters()):
                    raise ValueError("Nonfinite masked autoencoder gradient")
                nn.utils.clip_grad_norm_(network.parameters(), 5.)
                optimizer.step()
                total += float(loss.detach())*len(positions)
                denominator += len(positions)
            if not denominator:
                raise ValueError("No observed bins were selected for reconstruction")
            scheduler.step()
            if epoch in (0, self.candidate["epochs"]-1):
                self.loss_endpoints.append(total/denominator)
        self.encoder = network.encoder.requires_grad_(False).eval()
        for parameter in self.encoder.parameters():
            parameter.grad = None
        self.source_window_count = len(windows)
        self.source_participants = sorted(set(participants))
        return self

    def extract(self, windows):
        windows = validate_windows(windows)
        if any(p.requires_grad for p in self.encoder.parameters()):
            raise ValueError("The external temporal encoder must stay frozen")
        with torch.no_grad():
            encoded = self.encoder(torch.from_numpy(windows.copy()))
            features = torch.cat((encoded.mean(dim=2), encoded.std(dim=2, correction=0)), dim=1).numpy()
        # Biases alone do not represent an observation for an empty query.
        features[windows[:, 3:].sum(axis=(1, 2)) == 0] = 0.
        if not np.isfinite(features).all():
            raise ValueError("Nonfinite frozen temporal representation")
        return features


def add_features(frame, context, windows, statistics, encoder):
    if context.shape != (len(frame), len(GENERATED)) or statistics.shape != (len(frame), len(STATISTICS)) or len(windows) != len(frame):
        raise ValueError("Runtime causal windows and cross-fitted context must match the query batch")
    embedding = encoder.extract(windows)
    return frame.assign(**{name: context[:, i] for i, name in enumerate(GENERATED)},
                        **{name: embedding[:, i] for i, name in enumerate(EMBEDDING_NAMES)},
                        **{name: statistics[:, i] for i, name in enumerate(STATISTICS)})


class TemporalBorg:
    """Inference receives current past-only windows; no stored query/label lookup."""
    def __init__(self, candidate, encoder=None):
        self.candidate, self.encoder = candidate, encoder

    def fit(self, frame, windows, statistics, core_specification):
        with threadpool_limits(limits=1):
            self.base = DynamicsClassifier(core_specification).fit(frame)
            if self.candidate["algorithm"] == "control":
                return self
            context, self.inner_folds = inner_context(frame, core_specification)
            features = add_features(frame, context, windows, statistics, self.encoder)
            target = frame["label"].str.removeprefix("Borg ").to_numpy(int)-context[:, 0].astype(int)
            self.corrector = fit_corrector(features, target, self.candidate)
        return self

    def predict(self, frame, windows, statistics):
        validate_calibration(frame)
        if self.candidate["algorithm"] == "control":
            return self.base.predict(frame)
        context = base_context(self.base, frame)
        features = add_features(frame, context, windows, statistics, self.encoder)
        return corrected_predictions(context[:, 0], self.corrector.predict_proba(features[self.candidate["features"]]),
                                     self.corrector.classes_, self.candidate["zero_margin"])


def load_windows(frame):
    path = WINDOW_DIRECTORY / "provenance.json"
    evidence = json.loads(path.read_text())
    if (evidence["feature_code_sha256"] != digest(Path(__file__).with_name("fatigue_temporal_windows.py"))
            or evidence["native_borg_targets_stored"] != 0 or evidence["f_level_used"]
            or evidence["gap_interpolation"] or evidence["synthetic_borg_supervision_rows"] != 0):
        raise ValueError("Frozen feature-only temporal windows changed")
    for name, sha in evidence["dependency_code_sha256"].items():
        if digest(Path(__file__).with_name(name)) != sha:
            raise ValueError("Temporal preparation helper changed")
    for name, key in (("source.npz", "source_npz_sha256"), ("queries.npz", "query_npz_sha256")):
        if digest(WINDOW_DIRECTORY / name) != evidence[key]:
            raise ValueError("Temporal signal snapshot changed")
    with np.load(WINDOW_DIRECTORY / "source.npz", allow_pickle=False) as source:
        windows, participants = source["windows"], source["participants"]
    with np.load(WINDOW_DIRECTORY / "queries.npz", allow_pickle=False) as queries:
        np.testing.assert_array_equal(queries["row_keys"], frame["row_key"].to_numpy(str))
        native_windows, statistics = queries["windows"], queries["statistics"]
    if len(native_windows) != 666 or len(windows) != evidence["unlabelled_source_windows"] or set(participants) != FITTING_PEOPLE:
        raise ValueError("Original queries or external fitting split changed")
    return windows, participants, native_windows, statistics, evidence


def plan(manifest):
    prior = core_candidate(manifest)["features"]
    candidates = [{"id": "temporal-transfer-000", "algorithm": "control", "feature_set": "incumbent_control", "features": prior}]
    columns = prior+GENERATED+EMBEDDING_NAMES+STATISTICS
    for encoder in encoder_plan():
        for c in (.001, .01, .1):
            for margin in (0., .1, .25):
                candidates.append({"id": f"temporal-transfer-{len(candidates):03d}", "algorithm": "logistic",
                    "feature_set": "frozen_temporal", "features": columns, "params": {"C": c, "max_iter": 3000},
                    "zero_margin": margin, "source_encoder": encoder})
    return candidates


def fingerprint(manifest):
    helpers = ("fatigue_temporal_windows.py", "whamap_phone_bins.py", "fatigue_spectral_correction.py",
               "fatigue_spectral_experiment.py", "fatigue_dynamics_experiment.py", "fatigue_warm_sgd.py")
    return {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"],
            "temporal_provenance_sha256": digest(WINDOW_DIRECTORY / "provenance.json"),
            "dependency_code_sha256": {name: digest(Path(__file__).with_name(name)) for name in helpers},
            "software_versions": {name: importlib.metadata.version(name) for name in ("torch", "numpy", "pandas", "scikit-learn", "joblib")}}


def select():
    frame, train, _, manifest, _ = spectral_inputs()
    source, people, windows, statistics, window_evidence = load_windows(frame)
    signature = {**fingerprint(manifest), "plan": plan(manifest), "source_plan": encoder_plan(),
                 "core_candidate": core_candidate(manifest), "train_row_keys": train["row_key"].tolist()}
    DIRECTORY.mkdir(exist_ok=True)
    path = DIRECTORY / "selection.json"
    report = {**signature, "version": 1, "target_accuracy": .8, "status": "running", "results": [],
              "test_used_for_selection": False, "previous_benchmark_results_are_published": True, "external_test_used": False,
              "synthetic_rows": 0, "native_momentary_target_merge": False, "source_borg_labels_used": 0,
              "source_signal_windows": len(source), "source_people": len(set(people)), "f_level_used": False,
              "evaluation_denominator": 487, "test_denominator": 179, "minimum_cv_for_new_test_evaluation": .65,
              "policy": "External fitting-only observed phone bins pretrain a masked autoencoder without Borg/f-level labels. All encoder weights freeze. The native residual classifier uses inner participant-held-out baseline predictions. All original queries remain, with gaps masked and no interpolation, current/future sensor or Borg data."}
    if path.exists():
        report = json.loads(path.read_text())
        if any(report.get(k) != v for k, v in signature.items()):
            raise ValueError("Frozen temporal pretraining plan or inputs changed")
    else:
        path.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    encoders = {}
    for spec in encoder_plan():
        directory = DIRECTORY / "encoders" / spec["id"]
        model_path, meta_path = directory / "model.joblib", directory / "descriptor.json"
        identity = {"signature": fingerprint(manifest), "candidate": spec}
        if meta_path.exists():
            saved = json.loads(meta_path.read_text())
            if any(saved.get(k) != v for k, v in identity.items()) or digest(model_path) != saved["model_sha256"]:
                raise ValueError("Saved temporal encoder changed")
            encoder = joblib.load(model_path)
        else:
            encoder = FrozenTemporalEncoder(spec).fit(source, people)
            directory.mkdir(parents=True, exist_ok=True)
            joblib.dump(encoder, model_path)
            meta_path.write_text(json.dumps({**identity, "model_sha256": digest(model_path), "source_window_count": len(source),
                "source_participants": encoder.source_participants, "loss_endpoints": encoder.loss_endpoints,
                "all_parameters_frozen": not any(p.requires_grad for p in encoder.encoder.parameters()),
                "decoder_stored": False, "source_borg_labels_used": 0, "f_level_used": False}, indent=2)+"\n", encoding="utf-8")
        encoders[spec["id"]] = encoder
        print(f"Temporal pretraining {spec['id']}: observed masked MSE {encoder.loss_endpoints}", flush=True)
    index = {key: i for i, key in enumerate(frame["row_key"])}
    positions = np.asarray([index[key] for key in train["row_key"]])
    train_windows, train_stats = windows[positions], statistics[positions]
    folds = list(GroupKFold(n_splits=5).split(train, groups=train["group_key"]))
    packed, evidence, base_predictions = [], [], np.empty(len(train), dtype=object)
    with threadpool_limits(limits=1):
        for number, (fit, val) in enumerate(folds):
            fitting, validation = train.iloc[fit], train.iloc[val]
            if set(fitting["group_key"]) & set(validation["group_key"]):
                raise ValueError("Outer temporal residual correction leaked participants")
            context_fit, inner = inner_context(fitting, signature["core_candidate"])
            base = DynamicsClassifier(signature["core_candidate"]).fit(fitting)
            context_val = base_context(base, validation)
            base_predictions[val] = [f"Borg {i}" for i in context_val[:, 0].astype(int)]
            packed.append((context_fit, context_val))
            evidence.append({"fit_row_keys": fitting["row_key"].tolist(), "validation_row_keys": validation["row_key"].tolist(),
                             "inner_folds": inner, "fit_context": context_fit.tolist(), "validation_context": context_val.tolist()})
            print(f"Temporal native correction: nested baseline fold {number+1}/5", flush=True)
    expected = json.loads((RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
    expected = next(r["oof_predictions"] for r in expected["results"] if r["candidate"]["id"] == "alternative-023")
    np.testing.assert_array_equal(base_predictions, expected)
    report["folds"] = evidence
    cached = {}
    for candidate in signature["plan"]:
        if any(r["candidate"] == candidate for r in report["results"]):
            continue
        predicted = base_predictions.copy()
        if candidate["algorithm"] != "control":
            key = (candidate["source_encoder"]["id"], candidate["params"]["C"])
            if key not in cached:
                scores = []
                for (fit, val), (context_fit, context_val) in zip(folds, packed):
                    fitting = add_features(train.iloc[fit], context_fit, train_windows[fit], train_stats[fit], encoders[key[0]])
                    validation = add_features(train.iloc[val], context_val, train_windows[val], train_stats[val], encoders[key[0]])
                    target = train.iloc[fit]["label"].str.removeprefix("Borg ").to_numpy(int)-context_fit[:, 0].astype(int)
                    with threadpool_limits(limits=1):
                        corrector = fit_corrector(fitting, target, candidate)
                        probability = corrector.predict_proba(validation[candidate["features"]])
                    scores.append((probability, corrector.classes_))
                cached[key] = scores
            for (_, val), (_, context), (probabilities, classes) in zip(folds, packed, cached[key]):
                predicted[val] = corrected_predictions(context[:, 0], probabilities, classes, candidate["zero_margin"])
        scores = [float(accuracy_score(train.iloc[val]["label"], predicted[val])) for _, val in folds]
        report["results"].append({"candidate": candidate, "accuracy_mean": float(np.mean(scores)), "fold_accuracy": scores,
            "pooled_oof_accuracy": float(accuracy_score(train["label"], predicted)), "oof_predictions": predicted.tolist(),
            "changed_decisions": int((predicted != base_predictions).sum())})
        best = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"], best_cv_accuracy=best["accuracy_mean"],
                      status="complete" if len(report["results"]) == len(signature["plan"]) else "running")
        content = json.dumps(report, indent=2, allow_nan=False)+"\n"
        path.with_suffix(".tmp").write_text(content, encoding="utf-8")
        path.write_text(content, encoding="utf-8")
        print(f"Temporal transfer {len(report['results'])}/{len(signature['plan'])}: exact CV={np.mean(scores):.6f}, best={best['accuracy_mean']:.6f}", flush=True)


if __name__ == "__main__":
    select()
