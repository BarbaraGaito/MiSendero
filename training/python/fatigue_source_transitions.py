"""Combine actual repeated Borg reports as source-specific transition teachers.

Worker survey order is known but its exact survey clock is unpublished. No
age is inferred. Only actual previous Borg and causal HR summaries are shared;
different study outcomes and sensor averaging windows retain separate heads.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR
from threadpoolctl import threadpool_limits

import fatigue_runner_transfer as baseline
from fatigue_source_teachers import external_inputs
from public_sources import digest

SOURCE_DIRECTORY = baseline.RESEARCH / "source-prior-transitions-80-v1"
DIRECTORY = baseline.RESEARCH / "source-transition-teachers-80-v1"
FEATURES = ["prior_borg", "hr_last", "hr_history_mean"]
OUTPUTS = [f"transition_{domain}_{kind}" for domain in ("worker", "sts") for kind in ("estimate", "change")]


def build_pairs(sources, manifests, splits):
    rows, counts = [], {}
    for domain in ("worker", "sts"):
        data, manifest, split = sources[domain], manifests[domain], splits[domain]
        if data.row_key.tolist() != split["train_row_keys"] or set(data.group_key) & set(split["test_groups"]):
            raise ValueError("A reserved source person/report entered transition preparation")
        lineage = {row["row_key"]: row for row in manifest["lineage"]}
        if len(lineage) != len(manifest["lineage"]):
            raise ValueError("Duplicate original report lineage")
        by_key = data.set_index("row_key", drop=False)
        prior_map = {}
        for key in data.row_key:
            row = lineage[key]
            if domain == "worker":
                rep = int(re.search(r"\[REP ([1-5])\]", row["questionnaire_column"])[1])
                context = (row["questionnaire_worksheet_row"], rep)
            else:
                context = (row["member"], row["response_time_seconds"])
            if context in prior_map:
                raise ValueError("Ambiguous source survey session/order")
            prior_map[context] = key
        used = []
        for key in data.row_key:
            row, current = lineage[key], by_key.loc[key]
            if domain == "worker":
                rep = int(re.search(r"\[REP ([1-5])\]", row["questionnaire_column"])[1])
                old_key = prior_map.get((row["questionnaire_worksheet_row"], rep-1))
            else:
                old_key = prior_map.get((row["member"], row["prior_response_time_seconds"]))
            if old_key is None:
                continue
            old = by_key.loc[old_key]
            if old.group_key != current.group_key:
                raise ValueError("A previous survey belongs to a different source person")
            previous, target = float(old.borg_native), float(current.borg_native)
            if not np.isfinite([previous, target]).all() or not 0 <= previous <= 10 or not 0 <= target <= 10:
                raise ValueError("Only original finite native CR10 surveys may supervise transitions")
            if domain == "sts" and previous != current.prior_borg:
                raise ValueError("STS previous native Borg disagrees with its actual report lineage")
            rows.append({"source_domain": domain, "row_key": key, "prior_row_key": old_key,
                "group_key": current.group_key, "prior_borg": previous, "borg_native": target,
                "hr_last": current.hr_last, "hr_history_mean": current.hr_history_mean})
            used.append(target)
        counts[domain] = {"transition_targets": len(used), "fractional_targets": sum(v != round(v) for v in used),
                          "first_or_unpaired_reports_without_prior": len(data)-len(used)}
    result = pd.DataFrame(rows)
    if not result.row_key.is_unique:
        raise ValueError("The same observed source target was replicated as several transitions")
    return result, counts


def source_inputs():
    sources, splits = external_inputs()
    manifests = {name: json.loads((baseline.RESEARCH/(name+"-v1")/"provenance.json").read_text()) for name in ("worker", "sts")}
    for name, manifest in manifests.items():
        if manifest["dataset_sha256"] != digest(baseline.RESEARCH/(name+"-v1")/"dataset.csv"):
            raise ValueError("Original source survey snapshot changed")
        if sources[name].row_key.tolist() != splits[name]["train_row_keys"]:
            raise ValueError("External fitting report ordering changed")
        if name == "sts":
            raw = pd.read_csv(baseline.RESEARCH/"sts-v1/dataset.csv")
            lookup = pd.DataFrame(manifest["lineage"])[["row_key"]].join(raw)
            sources[name] = sources[name].merge(lookup[["row_key", "prior_borg"]], on="row_key", validate="one_to_one", how="left")
    return sources, manifests, splits


def prepare():
    sources, manifests, splits = source_inputs()
    data, counts = build_pairs(sources, manifests, splits)
    SOURCE_DIRECTORY.mkdir(exist_ok=True)
    path = SOURCE_DIRECTORY/"dataset.csv"
    if path.exists():
        raise ValueError("Preserve the frozen transition source dataset before preparing another version")
    data.to_csv(path, index=False)
    provenance = {"version": 1, "code_sha256": digest(Path(__file__)), "dataset_sha256": digest(path),
        "source_provenance_sha256": {name: digest(baseline.RESEARCH/(name+"-v1")/"provenance.json") for name in ("worker", "sts")},
        "external_splits": {name: splits[name] for name in ("worker", "sts")}, "counts": counts,
        "actual_transition_targets": len(data), "source_participants": data.group_key.nunique(),
        "features": FEATURES, "synthetic_targets": 0, "interpolated_targets": 0,
        "invented_worker_report_timestamps": 0, "native_target_merge": False,
        "worker_protocol": "https://rogersgroup.northwestern.edu/files/2024/nexusworker.pdf",
        "policy": "Only actual preceding surveys within the same original session/recording. Worker uses immediately preceding repetition and no assumed survey timestamp/age. STS keeps actual published report times and fractional CR10 values. Original fitting participants only. HR units are bpm but window definitions differ, so each source keeps its own auxiliary regressor. Predictions become native features, never new native labels."}
    (SOURCE_DIRECTORY/"provenance.json").write_text(json.dumps(provenance, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"actual_transition_targets": len(data), "counts": counts}), flush=True)


def load_sources():
    manifest = json.loads((SOURCE_DIRECTORY/"provenance.json").read_text())
    if manifest["code_sha256"] != digest(Path(__file__)) or manifest["dataset_sha256"] != digest(SOURCE_DIRECTORY/"dataset.csv"):
        raise ValueError("Frozen transition preparation changed")
    for name, sha in manifest["source_provenance_sha256"].items():
        if digest(baseline.RESEARCH/(name+"-v1")/"provenance.json") != sha:
            raise ValueError("Source report lineage changed")
    data = pd.read_csv(SOURCE_DIRECTORY/"dataset.csv")
    for name, split in manifest["external_splits"].items():
        part = data[data.source_domain.eq(name)]
        if (set(part.row_key) & set(split["test_row_keys"]) or set(part.prior_row_key) & set(split["test_row_keys"])
                or set(part.group_key) & set(split["test_groups"])):
            raise ValueError("External reserved survey/person entered a transition")
    return data, manifest


def fit_teachers(data, algorithm):
    teachers = {}
    for name in ("worker", "sts"):
        part = data[data.source_domain.eq(name)]
        estimator = {"ridge": lambda: Ridge(alpha=10.), "svr": lambda: SVR(C=10., gamma="scale", epsilon=.1),
            "random_forest": lambda: RandomForestRegressor(n_estimators=200, max_depth=4, min_samples_leaf=3, random_state=42, n_jobs=1)}[algorithm]()
        model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), StandardScaler(), estimator)
        # Equal total mass per original source participant; continuous deltas
        # preserve all actual half-point outcomes without class conversion.
        weights = 1./part.groupby("group_key")["group_key"].transform("size").to_numpy()
        weights *= len(part)/weights.sum()
        with threadpool_limits(limits=1):
            model.fit(part[FEATURES], part.borg_native.to_numpy()-part.prior_borg.to_numpy(),
                **{model.steps[-1][0]+"__sample_weight": weights})
        teachers[name] = model
    return teachers


def add_features(frame, teachers):
    baseline.validate_calibration(frame)
    output = frame.copy()
    with threadpool_limits(limits=1):
        for domain, teacher in teachers.items():
            delta = teacher.predict(frame[FEATURES])
            output[f"transition_{domain}_estimate"] = np.clip(frame.prior_borg.to_numpy()+delta, 0, 10)
            output[f"transition_{domain}_change"] = delta
    return output


class TransitionBorg:
    def __init__(self, candidate, teachers):
        self.candidate, self.teachers = candidate, teachers

    def fit(self, frame, specifications):
        c = self.candidate
        self.input_features = list(dict.fromkeys(specifications[c["member"]]["features"]+FEATURES))
        recipe = {**specifications[c["member"]], "id": c["id"], "features": self.input_features+(OUTPUTS if self.teachers else [])}
        with threadpool_limits(limits=1):
            self.model = (baseline.DynamicsClassifier(recipe) if c["member"] == "core" else baseline.CatBoostBorg(recipe)).fit(add_features(frame, self.teachers))
        return self

    def predict(self, frame):
        return self.model.predict(add_features(frame, self.teachers))


def plan():
    recipes = [{"id": "transition-000", "algorithm": "parent_control", "parent_candidate_id": "runner-transfer-000"},
               {"id": "transition-001", "algorithm": "parent_control", "parent_candidate_id": "runner-transfer-001"}]
    for member in ("core", "cat"):
        recipes.append({"id": f"transition-{len(recipes):03d}", "algorithm": "sensor_control", "member": member})
    for algorithm in ("ridge", "svr", "random_forest"):
        for member in ("core", "cat"):
            recipes.append({"id": f"transition-{len(recipes):03d}", "algorithm": algorithm, "member": member})
    return recipes


def load_inputs():
    frame, train, test, manifest, _, _, members, _ = baseline.member_inputs()
    manifest = {**manifest, "member_specifications": members["member_specifications"], "member_fingerprint": baseline.member_fingerprint(members)}
    sources, provenance = load_sources()
    return frame, train, test, manifest, sources, provenance


def fingerprint(inputs):
    _, _, _, manifest, _, provenance = inputs
    return {"code_sha256": digest(Path(__file__)), "native_dataset_sha256": manifest["dataset_sha256"],
        "member_specifications": manifest["member_specifications"], "source_provenance_sha256": digest(SOURCE_DIRECTORY/"provenance.json"),
        "member_fingerprint": manifest["member_fingerprint"],
        "source_dataset_sha256": provenance["dataset_sha256"],
        "baseline_selection_sha256": digest(baseline.DIRECTORY/"selection.json"),
        "dependency_code_sha256": {name: digest(Path(__file__).with_name(name)) for name in ("fatigue_runner_transfer.py", "fatigue_source_teachers.py", "fatigue_auxiliary_transfer.py", "fatigue_dynamics_experiment.py", "fatigue_catboost.py")}}


def select():
    inputs = load_inputs()
    _, train, test, manifest, sources, provenance = inputs
    signature = fingerprint(inputs)
    DIRECTORY.mkdir(exist_ok=True)
    (DIRECTORY/"teachers").mkdir(exist_ok=True)
    path = DIRECTORY/"selection.json"
    report = {**signature, "version": 1, "status": "running", "plan": plan(), "results": [],
        "train_row_keys": train.row_key.tolist(), "target_accuracy": .8, "evaluation_denominator": len(train),
        "test_denominator": len(test), "test_used_for_selection": False, "minimum_cv_for_new_test_evaluation": .65,
        "new_native_borg_targets": 0, "previous_benchmark_results_are_published": True,
        "source_transition_targets": provenance["actual_transition_targets"],
        "policy": "Source-only prior-conditioned regression teachers frozen before native fitting. No native target enters a teacher. No source-label conversion, timestamp invention, future target predictor or change to participant holdouts. Exact original native targets on all cases."}
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k, v in signature.items()) or old["plan"] != plan() or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen source transition teacher study changed")
        report = old
    else:
        path.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    if report["status"] == "complete":
        return report
    previous = json.loads((baseline.DIRECTORY/"selection.json").read_text())
    folds = list(GroupKFold(n_splits=5).split(train, groups=train.group_key))
    teachers = {}
    for c in report["plan"]:
        if any(r["candidate"] == c for r in report["results"]):
            continue
        if c["algorithm"] == "parent_control":
            old = next(r for r in previous["results"] if r["candidate"]["id"] == c["parent_candidate_id"])
            row = {**old, "candidate": c}
        else:
            algorithm = c["algorithm"]
            if algorithm == "sensor_control":
                teachers[algorithm] = {}
            elif algorithm not in teachers:
                teachers[algorithm] = fit_teachers(sources, algorithm)
                joblib.dump(teachers[algorithm], DIRECTORY/"teachers"/(algorithm+".joblib"))
            oof = np.empty(len(train), dtype=object)
            for number, (fit, val) in enumerate(folds):
                fitting, validation = train.iloc[fit], train.iloc[val]
                if set(fitting.group_key) & set(validation.group_key):
                    raise ValueError("Native fold people overlap")
                model = TransitionBorg(c, teachers[algorithm]).fit(fitting, manifest["member_specifications"])
                oof[val] = model.predict(validation)
                print(f"Source transition {c['id']} fold {number+1}/5 complete", flush=True)
            measured = [float(accuracy_score(train.iloc[val].label, oof[val])) for _, val in folds]
            row = {"candidate": c, "accuracy_mean": float(np.mean(measured)), "fold_accuracy": measured,
                "pooled_oof_accuracy": float(accuracy_score(train.label, oof)), "oof_predictions": oof.tolist()}
        report["results"].append(row)
        winner = max(report["results"], key=lambda r: r["accuracy_mean"])
        report.update(winner_id=winner["candidate"]["id"], best_cv_accuracy=winner["accuracy_mean"])
        path.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        print(f"Source transition recipe {len(report['results'])}/10 {c['id']}: CV={row['accuracy_mean']:.6f}", flush=True)
    report["teacher_artifact_sha256"] = {key: digest(DIRECTORY/"teachers"/(key+".joblib")) for key in ("ridge", "svr", "random_forest")}
    report["status"] = "complete"
    path.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    prepare() if args.prepare else select()
