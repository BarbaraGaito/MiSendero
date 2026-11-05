"""Leave-one-participant-out comparison: threshold baseline vs Random Forest vs XGBoost.

Nested protocol per held-out participant:
  1. the decision threshold (or baseline rule) is selected on the *other* 29 participants only
     (inner GroupKFold out-of-fold scores, objective F2 = recall-weighted F-score);
  2. the model is refitted on those 29 and evaluated on the held-out participant.
Hyper-parameters are fixed a priori (no tuning on the evaluation folds). No synthetic samples,
oversampling or augmentation are used; class imbalance is handled only with class weights.
"""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import time
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold
from xgboost import XGBClassifier

from .candidates import candidate_peaks, extract_candidates
from .config import (ADL_ACTIVITIES, FALL_ACTIVITIES, GATE_G, NEIGHBOURHOOD, PEAK_INDEX, POST_SAMPLES, PRE_SAMPLES,
                     SAMPLE_RATE_HZ, WINDOW)
from .dataset import ROOT, load_records, summarize as summarize_dataset
from .evaluation import bootstrap_by_participant, counts, f2_score, from_counts, summarize
from .features import FEATURE_ORDER, magnitude, window_features

OUT = ROOT / "training/data/public/fall_detection"
SEED = 20261022
THRESHOLD_GRID = np.round(np.linspace(0.02, 0.98, 97), 2)
UFT = [1.5 + 0.25 * i for i in range(11)]            # impact peak thresholds (g)
LFT = [None, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3]      # free-fall minimum (g)
PST = [None, 0.4, 0.3, 0.2, 0.15, 0.1]               # mean |m - 1| after the impact (g)


def make_model(name: str, positives: int, negatives: int):
    if name == "random_forest":
        return RandomForestClassifier(n_estimators=300, min_samples_leaf=2, max_features="sqrt",
                                      class_weight="balanced_subsample", n_jobs=-1, random_state=SEED)
    if name == "xgboost":
        return XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                             min_child_weight=2, scale_pos_weight=negatives / max(positives, 1), tree_method="hist",
                             eval_metric="aucpr", n_jobs=-1, random_state=SEED, verbosity=0)
    raise ValueError(name)


def best_threshold(y, score) -> float:
    best, best_value = 0.5, -1.0
    for tau in THRESHOLD_GRID:
        value = f2_score(y, score >= tau)
        if value > best_value + 1e-12:
            best, best_value = float(tau), value
    return best


def baseline_rule(X: np.ndarray, rule: tuple) -> np.ndarray:
    uft, lft, pst = rule
    peak, free, post = (X[:, FEATURE_ORDER.index(k)] for k in ("m_max", "freefall_min", "post_dev_mean"))
    out = peak >= uft
    if lft is not None:
        out &= free <= lft
    if pst is not None:
        out &= post <= pst
    return out


def fit_baseline(X, y) -> tuple:
    best, best_key = None, (-1.0, 0)
    for rule in itertools.product(UFT, LFT, PST):
        pred = baseline_rule(X, rule)
        key = (f2_score(y, pred), -int(np.sum(pred & ~y.astype(bool))))
        if key > best_key:
            best, best_key = rule, key
    return best


def gate_table(records) -> list[dict]:
    falls = [r for r in records if r.kind == "fall"]
    rows = []
    for gate in (1.25, 1.5, 1.75, 2.0, 2.5):
        ceiling = np.mean([magnitude(r.xyz_g).max() > gate for r in falls])
        adl = sum(len(candidate_peaks(magnitude(r.xyz_g), gate)) for r in records if r.kind == "adl")
        rows.append({"gate_g": gate, "fall_segments_above_gate": float(ceiling), "adl_candidates": int(adl)})
    return rows


def precompute_analysis(records, participants_of_cands):
    """Features for the continuous-window study (no gate, no peak alignment)."""
    per = collections.defaultdict(lambda: {"adl_x": [], "adl_act": [], "adl_gate": [], "fall_x": collections.defaultdict(list)})
    offsets = (-30, -20, -10, 0, 10, 20)
    for record in records:
        n = len(record.xyz_g)
        m = magnitude(record.xyz_g)
        slot = per[record.participant]
        if record.kind == "adl":
            for start in range(0, n - WINDOW + 1, 10):
                slot["adl_x"].append(window_features(record.xyz_g[start:start + WINDOW]))
                slot["adl_act"].append(record.activity)
                slot["adl_gate"].append(bool(m[start:start + WINDOW].max() > GATE_G))
        else:
            peak = int(np.argmax(m))
            for off in offsets:
                start = peak - (PEAK_INDEX + off)
                if start >= 0 and start + WINDOW <= n:
                    slot["fall_x"][off].append(window_features(record.xyz_g[start:start + WINDOW]))
    return per, offsets


def pooled_report(name, y, pred, score, participants, activities, pockets, extra=None):
    report = summarize(y, pred, score)
    report["bootstrap_95ci_by_participant"] = bootstrap_by_participant(y, pred, participants)
    by_p = []
    for p in np.unique(participants):
        mask = participants == p
        c = counts(y[mask], pred[mask])
        by_p.append({"participant": int(p), **{k: c[k] for k in c}})
    pos = [r["tp"] / (r["tp"] + r["fn"]) for r in by_p if r["tp"] + r["fn"]]
    spec = [r["tn"] / (r["tn"] + r["fp"]) for r in by_p if r["tn"] + r["fp"]]
    report["per_participant"] = {"recall_mean": float(np.mean(pos)), "recall_min": float(np.min(pos)),
                                 "recall_std": float(np.std(pos)), "specificity_mean": float(np.mean(spec)),
                                 "specificity_min": float(np.min(spec)), "specificity_std": float(np.std(spec))}
    report["by_activity"] = {}
    for activity in ADL_ACTIVITIES + FALL_ACTIVITIES:
        mask = activities == activity
        if mask.any():
            c = counts(y[mask], pred[mask])
            report["by_activity"][activity] = ({"windows": int(mask.sum()), "false_positive_rate": c["fp"] / mask.sum(), "false_positives": c["fp"]}
                                               if activity in ADL_ACTIVITIES else
                                               {"windows": int(mask.sum()), "recall": c["tp"] / mask.sum(), "missed": c["fn"]})
    report["by_pocket"] = {}
    for pocket in ("right", "left"):
        mask = pockets == pocket
        c = counts(y[mask], pred[mask])
        report["by_pocket"][pocket] = {"windows": int(mask.sum()), **{k: from_counts(c)[k] for k in ("recall", "specificity", "precision", "f1")}}
    if extra:
        report.update(extra)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="3 participants, for smoke tests only")
    args = parser.parse_args()
    started = time.time()
    records, audit = load_records()
    candidates, X = extract_candidates(records)
    participant = np.array([c.participant for c in candidates])
    kind = np.array([c.kind for c in candidates])
    activity = np.array([c.activity for c in candidates])
    pocket = np.array([c.pocket for c in candidates])
    segment = np.array([c.record_index for c in candidates])
    has_window = np.array([c.has_window for c in candidates])
    main_impact = np.array([c.main_impact for c in candidates])
    labelled = has_window & ((kind == "adl") | main_impact)
    y_all = (kind == "fall").astype(int)
    people = list(range(30))[:3] if args.quick else list(range(30))
    analysis, offsets = precompute_analysis(records, participant)
    print(f"candidates={len(candidates)} labelled={int(labelled.sum())} fall={int(y_all[labelled].sum())} "
          f"adl={int((1 - y_all[labelled]).sum())} prep={time.time() - started:.0f}s", flush=True)

    methods = ["threshold_baseline", "random_forest", "xgboost"]
    score = {m: np.full(len(candidates), np.nan) for m in methods}     # probabilities (baseline: 0/1 decision)
    tau = {m: {} for m in methods}
    fixed_pred = {m: np.zeros(len(candidates), bool) for m in methods}
    nested_pred = {m: np.zeros(len(candidates), bool) for m in methods}
    continuous = {m: {"adl": collections.defaultdict(lambda: [0, 0, 0]), "fall": collections.defaultdict(lambda: [0, 0])} for m in methods[1:]}
    baseline_continuous = {"adl": collections.defaultdict(lambda: [0, 0, 0]), "fall": collections.defaultdict(lambda: [0, 0])}
    for person in people:
        train = labelled & (participant != person)
        test_all = has_window & (participant == person)
        assert not np.any(participant[train] == person), "participant leakage"
        Xtr, ytr, gtr = X[train], y_all[train], participant[train]
        rule = fit_baseline(Xtr, ytr)
        tau["threshold_baseline"][person] = list(rule)
        decision = baseline_rule(X[test_all], rule)
        score["threshold_baseline"][test_all] = decision.astype(float)
        fixed_pred["threshold_baseline"][test_all] = decision
        nested_pred["threshold_baseline"][test_all] = decision
        slot = analysis[person]
        if slot["adl_x"]:
            adl_x = np.vstack(slot["adl_x"])
            for act, gate, flag in zip(slot["adl_act"], slot["adl_gate"], baseline_rule(adl_x, rule)):
                baseline_continuous["adl"][act][0] += 1
                baseline_continuous["adl"][act][1] += int(flag)
                baseline_continuous["adl"][act][2] += int(flag and gate)
        for off, rows in slot["fall_x"].items():
            flags = baseline_rule(np.vstack(rows), rule)
            baseline_continuous["fall"][off][0] += len(rows)
            baseline_continuous["fall"][off][1] += int(flags.sum())
        for name in methods[1:]:
            oof = np.zeros(len(ytr))
            for fit_idx, val_idx in GroupKFold(n_splits=5).split(Xtr, ytr, gtr):
                inner = make_model(name, int(ytr[fit_idx].sum()), int((1 - ytr[fit_idx]).sum()))
                inner.fit(Xtr[fit_idx], ytr[fit_idx])
                oof[val_idx] = inner.predict_proba(Xtr[val_idx])[:, 1]
            chosen = best_threshold(ytr, oof)
            model = make_model(name, int(ytr.sum()), int((1 - ytr).sum()))
            model.fit(Xtr, ytr)
            p = model.predict_proba(X[test_all])[:, 1]
            score[name][test_all] = p
            tau[name][person] = chosen
            fixed_pred[name][test_all] = p >= 0.5
            nested_pred[name][test_all] = p >= chosen
            if slot["adl_x"]:
                probs = model.predict_proba(adl_x)[:, 1]
                for act, gate, value in zip(slot["adl_act"], slot["adl_gate"], probs):
                    continuous[name]["adl"][act][0] += 1
                    continuous[name]["adl"][act][1] += int(value >= chosen)
                    continuous[name]["adl"][act][2] += int(value >= chosen and gate)
            for off, rows in slot["fall_x"].items():
                probs = model.predict_proba(np.vstack(rows))[:, 1]
                continuous[name]["fall"][off][0] += len(rows)
                continuous[name]["fall"][off][1] += int((probs >= chosen).sum())
        print(f"participant {person:2d} done ({time.time() - started:.0f}s)", flush=True)

    evaluated = labelled & np.isin(participant, people)
    result = {"protocol": {
        "validation": "leave-one-participant-out (30 folds); threshold/rule selected on the 29 training participants only",
        "threshold_objective": "F2 (recall-weighted) on inner 5-fold GroupKFold out-of-fold scores",
        "window": {"samples": WINDOW, "pre": PRE_SAMPLES, "post": POST_SAMPLES, "sample_rate_hz": SAMPLE_RATE_HZ},
        "gate_g": GATE_G, "neighbourhood_samples": NEIGHBOURHOOD, "seed": SEED,
        "positives": "main impact (global magnitude maximum) of each fall segment that has a full window",
        "negatives": "every impact candidate of every ADL segment that has a full window",
        "excluded_from_candidate_metrics": "secondary peaks inside fall segments (ambiguous label) and candidates without a full real window; both are reported below",
        "synthetic_data": "none", "oversampling": "none (class weights only)"},
        "dataset": summarize_dataset(records, audit),
        "gate_table": gate_table(records),
        "candidate_counts": {
            "total": int(len(candidates)), "labelled": int(labelled.sum()),
            "fall_positive": int(y_all[labelled].sum()), "adl_negative": int((1 - y_all[labelled]).sum()),
            "fall_main_impact_without_window": int(np.sum(main_impact & ~has_window)),
            "fall_segments_without_gate_candidate": int(sum(1 for r in records if r.kind == "fall") - main_impact.sum()),
            "adl_candidates_without_window": int(np.sum((kind == "adl") & ~has_window)),
            "fall_secondary_candidates": int(np.sum((kind == "fall") & ~main_impact))},
        "models": {}}
    for name in methods:
        report = {"hyperparameters": None if name == "threshold_baseline" else make_model(name, 1, 1).get_params(),
                  "selected_threshold_per_participant": {str(k): v for k, v in tau[name].items()}}
        mask = evaluated
        y, ps = y_all[mask], score[name][mask]
        report["nested_threshold"] = pooled_report(name, y, nested_pred[name][mask], ps, participant[mask], activity[mask], pocket[mask])
        if name != "threshold_baseline":
            report["fixed_threshold_0_5"] = pooled_report(name, y, fixed_pred[name][mask], ps, participant[mask], activity[mask], pocket[mask])
        # Event level: every candidate with a window may raise the alarm for its segment.
        alarm = nested_pred[name]
        fall_segments = [i for i, r in enumerate(records) if r.kind == "fall" and r.participant in people]
        adl_segments = [i for i, r in enumerate(records) if r.kind == "adl" and r.participant in people]
        by_segment = collections.defaultdict(list)
        for idx in np.where(has_window)[0]:
            by_segment[segment[idx]].append(alarm[idx])
        detected = sum(any(by_segment.get(i, [])) for i in fall_segments)
        evaluable = sum(1 for i in fall_segments if any(main_impact[j] and has_window[j] for j in np.where(segment == i)[0]))
        detected_evaluable = sum(any(by_segment.get(i, [])) for i in fall_segments
                                 if any(main_impact[j] and has_window[j] for j in np.where(segment == i)[0]))
        adl_alarms = [sum(by_segment.get(i, [])) for i in adl_segments]
        minutes = sum(len(records[i].xyz_g) for i in adl_segments) / SAMPLE_RATE_HZ / 60
        report["event_level"] = {
            "fall_segments": len(fall_segments), "fall_segments_with_full_window": evaluable,
            "falls_detected": int(detected), "recall_all_fall_segments_lower_bound": detected / len(fall_segments),
            "recall_evaluable_fall_segments": detected_evaluable / evaluable,
            "adl_segments": len(adl_segments), "adl_segments_with_alarm": int(sum(a > 0 for a in adl_alarms)),
            "adl_alarm_candidates": int(sum(adl_alarms)),
            "scripted_adl_minutes": round(minutes, 1),
            "note": "Scripted ADL segments only; this is NOT an hourly false-alarm rate for real hiking."}
        if name != "threshold_baseline":
            cont = continuous[name]
            report["continuous_windows_without_gate"] = {
                "adl_fraction_flagged_by_activity": {a: {"windows": v[0], "flagged": v[1], "fraction": v[1] / v[0],
                                                          "flagged_that_also_pass_gate": v[2]} for a, v in cont["adl"].items()},
                "fall_recall_by_peak_offset_samples": {str(o): {"windows": v[0], "recall": v[1] / v[0]} for o, v in sorted(cont["fall"].items())},
                "note": "Sliding 61-sample windows (hop 10) over ADL segments and impacts shifted inside the window; evaluates the candidate-trained classifier without the impact gate."}
        else:
            cont = baseline_continuous
            report["continuous_windows_without_gate"] = {
                "adl_fraction_flagged_by_activity": {a: {"windows": v[0], "flagged": v[1], "fraction": v[1] / v[0],
                                                          "flagged_that_also_pass_gate": v[2]} for a, v in cont["adl"].items()},
                "fall_recall_by_peak_offset_samples": {str(o): {"windows": v[0], "recall": v[1] / v[0]} for o, v in sorted(cont["fall"].items())}}
        result["models"][name] = report
        s = report["nested_threshold"]
        print(f"{name:20s} P={s['precision']:.3f} R={s['recall']:.3f} Spec={s['specificity']:.3f} F1={s['f1']:.3f} "
              f"F1macro={s['f1_macro']:.3f} PR-AUC={s.get('pr_auc', float('nan')):.3f}", flush=True)
    result["elapsed_seconds"] = round(time.time() - started, 1)
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / ("metrics.quick.json" if args.quick else "metrics.json")
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=float) + "\n", encoding="utf-8")
    np.savez_compressed(ROOT / "training/data/processed/fall_detection_oof.npz" if not args.quick else ROOT / "training/data/processed/fall_detection_oof.quick.npz",
                        participant=participant, kind=kind, activity=activity, pocket=pocket, segment=segment,
                        has_window=has_window, main_impact=main_impact, labelled=labelled,
                        **{f"score_{m}": score[m] for m in methods}, **{f"alarm_{m}": nested_pred[m] for m in methods})
    print("wrote", target, flush=True)


if __name__ == "__main__":
    main()
