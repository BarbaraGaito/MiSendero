"""Source-only six-minute-walk transfer, keeping original Borg cases intact."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits

from common.grouped_fatigue_search import grouped_search
from fatigue_dynamics_experiment import DynamicsClassifier, plan as dynamics_plan
from fatigue_features import RESEARCH
from fatigue_phone_experiment import plan as phone_plan
from fatigue_spectral_experiment import load_inputs as spectral_inputs
from public_sources import digest
from sixmwt_fatigue import ACC_FEATURES, DIRECTORY as SOURCE_DIRECTORY, load as source_inputs

DIRECTORY = RESEARCH / "gait-source-transfer-80-v1"
TEACHER_COLUMNS = ["sixmwt_external_estimate", "sixmwt_estimate_minus_prior"]


def teacher_plan():
    return [{"id": f"gait-teacher-{i:02d}", "algorithm": algorithm, "features": features, "feature_set": name}
            for i, (name, features, algorithm) in enumerate((name, columns, algorithm)
                for name, columns in (("hr", ["hr_last"]), ("acceleration_spectra", ACC_FEATURES), ("hr_and_spectra", ["hr_last", *ACC_FEATURES]))
                for algorithm in ("ridge", "svr", "random_forest"))]


def fit_teacher(source, candidate):
    estimator = {"ridge": lambda: Ridge(alpha=10.), "svr": lambda: SVR(C=10., gamma="scale", epsilon=.1),
                 "random_forest": lambda: RandomForestRegressor(n_estimators=200, max_depth=4, min_samples_leaf=5, random_state=42, n_jobs=1)}[candidate["algorithm"]]()
    model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), StandardScaler(), estimator)
    with threadpool_limits(limits=1):
        model.fit(source[candidate["features"]], source["borg_native"].to_numpy(float))
    return model


def add_teacher(frame, teacher, features):
    # The source prediction is an estimated covariate, never observed Borg.
    predicted = np.clip(teacher.predict(frame[features]), 0, 10)
    return frame.assign(sixmwt_external_estimate=predicted,
                        sixmwt_estimate_minus_prior=predicted-frame["prior_borg"].to_numpy(float))


def plan(manifest):
    prior = next(c["features"] for c in phone_plan(manifest) if c["feature_set"] == "incumbent_control")
    history = next(c["features"] for c in dynamics_plan(manifest) if c["feature_set"] == "compact_dynamics")
    mlp = {"hidden_layer_sizes": [16, 8], "solver": "lbfgs", "alpha": 10., "max_iter": 1000}
    candidates = [{"id": "gait-transfer-000", "feature_set": "incumbent_control", "features": prior,
                   "algorithm": "mlp", "params": mlp, "target_mode": "change_from_prior", "teacher": None},
                  {"id": "gait-transfer-001", "feature_set": "history_control", "features": history,
                   "algorithm": "mlp", "params": mlp, "target_mode": "change_from_prior", "teacher": None}]
    for teacher in teacher_plan():
        for name, columns, algorithm, params in (("prior_mlp", prior, "mlp", mlp), ("history_mlp", history, "mlp", mlp),
                                                 ("prior_svm", prior, "svm", {"C": 10., "gamma": "scale"})):
            candidates.append({"id": f"gait-transfer-{len(candidates):03d}", "feature_set": name, "features": columns+TEACHER_COLUMNS,
                               "algorithm": algorithm, "params": params, "target_mode": "change_from_prior", "teacher": teacher})
    return candidates


class GaitTransferBorg:
    def __init__(self, candidate, source=None):
        self.candidate = candidate
        self.source = source

    def fit(self, frame):
        c = self.candidate
        self.teacher = None
        if c["teacher"] is not None:
            source = self.source if self.source is not None else source_inputs()[0]
            if set(source["group_key"]) & set(frame["group_key"]):
                raise ValueError("External source participant namespace collides with original fitting people")
            self.teacher = fit_teacher(source, c["teacher"])
            frame = add_teacher(frame, self.teacher, c["teacher"]["features"])
        self.model = DynamicsClassifier(c).fit(frame)
        return self

    def predict(self, frame):
        if self.teacher is not None:
            frame = add_teacher(frame, self.teacher, self.candidate["teacher"]["features"])
        return self.model.predict(frame)


def load_inputs():
    frame, train, test, manifest, protocol = spectral_inputs()
    source, reserved, source_manifest = source_inputs()
    if set(source["group_key"]) & set(frame["group_key"]) or set(source["row_key"]) & set(reserved["row_key"]):
        raise ValueError("External and original participant holdouts overlap")
    return frame, train, test, manifest, protocol, source, source_manifest


def fingerprint(manifest, source_manifest):
    helpers = ("fatigue_dynamics_experiment.py", "fatigue_spectral_experiment.py", "sixmwt_fatigue.py")
    return {"code_sha256": digest(Path(__file__)), "dataset_sha256": manifest["dataset_sha256"],
            "spectral_dataset_sha256": manifest["spectral_dataset_sha256"],
            "spectral_provenance_sha256": manifest["spectral_provenance_sha256"],
            "source_dataset_sha256": source_manifest["dataset_sha256"],
            "source_provenance_sha256": digest(SOURCE_DIRECTORY / "provenance.json"), "external_split": source_manifest["split"],
            "dependency_code_sha256": {name: digest(Path(__file__).with_name(name)) for name in helpers},
            "grouped_search_code_sha256": digest(Path(__file__).parent / "common/grouped_fatigue_search.py"),
            "external_test_used": False, "teachers_use_geofatigue_labels": False, "original_momentary_target_merge": False,
            "external_fitting_reports": 48, "external_reserved_reports": 12,
            "scope": "Post-test CR10 remains source-only supervision. Its predictions are estimated inputs to the original participant-grouped classifier. All 487 OOF and 179 test cases remain native and unchanged."}


def select():
    _, train, _, manifest, _, source, source_manifest = load_inputs()
    # This class binds only the 48 external fitting reports, including when
    # the common runner creates a new estimator for each original fold.
    class SourceBound(GaitTransferBorg):
        def __init__(self, candidate):
            super().__init__(candidate, source)
    grouped_search(DIRECTORY, train, plan(manifest), fingerprint(manifest, source_manifest), SourceBound)
    report = json.loads((DIRECTORY / "selection.json").read_text(encoding="utf-8"))
    original = json.loads((RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
    expected = next(r["oof_predictions"] for r in original["results"] if r["candidate"]["id"] == "alternative-023")
    actual = next(r["oof_predictions"] for r in report["results"] if r["candidate"]["id"] == "gait-transfer-000")
    np.testing.assert_array_equal(actual, expected)
    original = json.loads((RESEARCH / "augmented-observed-feedback-80-v1/selection.json").read_text())
    expected = next(r["oof_predictions"] for r in original["results"] if r["candidate"]["algorithm"] == "mlp"
                    and r["candidate"]["feature_set"] == "compact_dynamics" and r["candidate"]["alpha"] == 10.
                    and r["candidate"]["target_mode"] == "change_from_prior" and r["candidate"]["extra_weight"] == 0.)
    actual = next(r["oof_predictions"] for r in report["results"] if r["candidate"]["id"] == "gait-transfer-001")
    np.testing.assert_array_equal(actual, expected)
    print("Both gait-transfer controls reproduce all 487 original OOF decisions", flush=True)


if __name__ == "__main__":
    select()
