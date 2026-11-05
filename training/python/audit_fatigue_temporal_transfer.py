"""Rebuild the unlabelled external signals and audit the frozen temporal study."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

import fatigue_temporal_transfer as temporal
import fatigue_temporal_windows as windows
import whamap_phone_bins as whamap
from fetch_whamap_sensors import DIRECTORY as RAW, PHONE_COLUMNS
from public_sources import digest


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate(selection, frame, train, manifest):
    inventory = json.loads((RAW / "inventory.json").read_text())
    receipt = json.loads((RAW / "fitting-traces-receipt.json").read_text())
    bins_evidence = json.loads((RAW / "phone-bins-provenance.json").read_text())
    require(receipt["all_complete_and_verified"] and len(receipt["verified_files"]) == 32
            and receipt["signature"]["inventory_sha256"] == digest(RAW / "inventory.json")
            and set(inventory["unlabelled_fitting_people"]) == temporal.FITTING_PEOPLE
            and set(inventory["reserved_people"]) == {"subject_02", "subject_09"}
            and inventory["license"]["short_name"] == "CC BY 4.0", "WHAMAP public source, license or fitting split changed")
    require(bins_evidence["receipt_sha256"] == digest(RAW / "fitting-traces-receipt.json")
            and bins_evidence["inventory_sha256"] == digest(RAW / "inventory.json")
            and bins_evidence["extractor_code_sha256"] == digest(Path(whamap.__file__))
            and bins_evidence["quality_policy_code_sha256"] == digest(Path(whamap.__file__).with_name("fatigue_phone_spectral.py"))
            and len(bins_evidence["files"]) == 32, "WHAMAP bin preparation changed")
    require(not receipt["reserved_people_downloaded"] and not receipt["f_level_used_as_borg_target"]
            and receipt["native_borg_targets_used"] == 0 and receipt["videos_downloaded"] == 0
            and not bins_evidence["reserved_source_people_used"] and not bins_evidence["f_level_used"]
            and bins_evidence["native_borg_supervision_rows"] == 0 and not bins_evidence["gap_interpolation"],
            "External holdout or unverified questionnaire labels entered pretraining")
    require(all(not (RAW / person).exists() for person in inventory["reserved_people"]), "A reserved external trace was downloaded")
    source_index = {r["local_path"]: r for r in inventory["files"]}
    verified = {r["local_path"]: r for r in receipt["verified_files"]}
    require(len(verified) == 32 and set(verified) == {r["local_path"] for r in receipt["signature"]["files"]}, "WHAMAP raw receipt changed")
    total_rows, total_bins, repeated_rows, total_bytes = 0, 0, 0, 0
    for number, evidence in enumerate(bins_evidence["files"]):
        source = evidence["source"]
        require(source == source_index[source["local_path"]] and source in receipt["signature"]["files"]
                and source["participant"] in temporal.FITTING_PEOPLE
                and source["filename"] in {"walking.csv", "walking_B.csv", "uphill.csv", "uphill_B.csv"}, "Wrong external pretraining trace")
        path = RAW / source["local_path"]
        require(path.stat().st_size == source["bytes"] == verified[source["local_path"]]["bytes"]
                and digest(path) == source["published_sha256"] == verified[source["local_path"]]["sha256"], "Original WHAMAP trace differs from publisher/receipt")
        raw = pd.read_csv(path, usecols=["time", *PHONE_COLUMNS])
        rebuilt, quality = whamap.segments(raw)
        require(quality == evidence["export_quality"] and not evidence["f_level_read"]
                and evidence["native_borg_supervision_rows"] == 0 and len(rebuilt) == len(evidence["segments"]), "External raw-bin quality reconstruction differs")
        for part, saved in zip(rebuilt, evidence["segments"]):
            path = whamap.CACHE / saved["file"]
            require(digest(path) == saved["sha256"] and len(part) == saved["observed_bins"]
                    and part.attrs["quality"] == saved["quality"], "External observed-bin cache changed")
            with np.load(path, allow_pickle=False) as cached:
                require(set(cached.files) == {"relative_time_ns", "values", "columns"}, "A target or identity channel entered a signal cache")
                np.testing.assert_array_equal(cached["relative_time_ns"], part.index.as_unit("ns").asi8-whamap.EPOCH.value)
                np.testing.assert_array_equal(cached["values"], part[whamap.BIN_COLUMNS].to_numpy(float))
                np.testing.assert_array_equal(cached["columns"], whamap.BIN_COLUMNS)
            total_bins += len(part)
        total_rows += quality["original_sample_rows"]
        repeated_rows += quality["identical_consecutive_export_rows"]
        total_bytes += source["bytes"]
        if (number+1) % 8 == 0:
            print(f"WHAMAP raw phone traces independently rebuilt {number+1}/32", flush=True)
    require(total_bytes == 718190042 and total_rows == bins_evidence["source_export_rows"] == 568074
            and total_bins == bins_evidence["observed_bins"] == 113575
            and repeated_rows == bins_evidence["identical_consecutive_export_rows"] == 455121,
            "External source row/bin counts changed")
    source, people, queries, statistics, window_evidence = temporal.load_windows(frame)
    require(window_evidence["source_bin_provenance_sha256"] == digest(RAW / "phone-bins-provenance.json")
            and window_evidence["parent_dataset_sha256"] == manifest["dataset_sha256"], "Temporal windows use different parents")
    rebuilt_source, rebuilt_stats, rebuilt_people, source_lineage, skipped, _ = windows.source_windows()
    np.testing.assert_array_equal(source, rebuilt_source)
    np.testing.assert_array_equal(people, rebuilt_people)
    with np.load(windows.DIRECTORY / "source.npz", allow_pickle=False) as saved:
        require(set(saved.files) == {"windows", "statistics", "participants"}, "Unlabelled source windows stored targets")
        np.testing.assert_array_equal(saved["statistics"], rebuilt_stats)
    require(source_lineage == window_evidence["source_window_lineage"] and skipped == window_evidence["source_windows_below_90_percent_coverage_skipped"]
            and len(source) == 842 and len(set(people)) == 8, "Temporal source window reconstruction differs")
    rebuilt_queries, rebuilt_stats, keys, lineage, _ = windows.query_windows()
    np.testing.assert_array_equal(queries, rebuilt_queries)
    np.testing.assert_array_equal(statistics, rebuilt_stats)
    np.testing.assert_array_equal(keys, frame["row_key"].to_numpy(str))
    with np.load(windows.DIRECTORY / "queries.npz", allow_pickle=False) as saved:
        require(set(saved.files) == {"windows", "statistics", "row_keys"}, "A current native target entered query tensors")
    require(lineage == window_evidence["query_lineage"] and len(queries) == 666
            and int((queries[:, 3:].sum(axis=(1, 2)) > 0).sum()) == window_evidence["query_rows_with_any_signal"] == 579,
            "Native temporal queries or missingness changed")
    for entry in lineage:
        if entry["latest_used_bin_end_ns"] is not None:
            require(entry["latest_used_bin_end_ns"] <= pd.Timestamp(entry["prediction_time"]).value, "A native phone window used future samples")
    signature = temporal.fingerprint(manifest)
    require(all(selection.get(k) == v for k, v in signature.items())
            and selection["plan"] == temporal.plan(manifest) and selection["source_plan"] == temporal.encoder_plan()
            and selection["status"] == "complete" and len(selection["results"]) == 37
            and selection["source_borg_labels_used"] == selection["synthetic_rows"] == 0
            and not selection["f_level_used"] and not selection["external_test_used"]
            and not selection["native_momentary_target_merge"] and selection["minimum_cv_for_new_test_evaluation"] == .65,
            "Temporal study data, supervision, plan or test gate changed")
    encoders = {}
    for spec in temporal.encoder_plan():
        directory = temporal.DIRECTORY / "encoders" / spec["id"]
        descriptor = json.loads((directory / "descriptor.json").read_text())
        require(descriptor["signature"] == signature and descriptor["candidate"] == spec
                and descriptor["model_sha256"] == digest(directory / "model.joblib")
                and descriptor["source_window_count"] == 842 and set(descriptor["source_participants"]) == temporal.FITTING_PEOPLE
                and descriptor["all_parameters_frozen"] and not descriptor["decoder_stored"]
                and descriptor["source_borg_labels_used"] == 0 and not descriptor["f_level_used"], "Temporal encoder descriptor changed")
        encoder = joblib.load(directory / "model.joblib")
        refit = temporal.FrozenTemporalEncoder(spec).fit(source, people)
        require(set(vars(encoder)) == {"candidate", "loss_endpoints", "encoder", "source_window_count", "source_participants"}
                and not any(p.requires_grad or p.grad is not None for p in encoder.encoder.parameters()), "Temporal encoder stores source queries/labels or is not frozen")
        for key, value in encoder.encoder.state_dict().items():
            require(torch.equal(value, refit.encoder.state_dict()[key]), "Independent masked reconstruction pretraining differs")
        np.testing.assert_allclose(encoder.loss_endpoints, descriptor["loss_endpoints"], rtol=0, atol=1e-12)
        np.testing.assert_allclose(refit.loss_endpoints, descriptor["loss_endpoints"], rtol=0, atol=1e-12)
        encoders[spec["id"]] = encoder
    original = json.loads((temporal.RESEARCH / "calibrated-alternatives-v1/selection.json").read_text())
    expected = next(r["oof_predictions"] for r in original["results"] if r["candidate"]["id"] == "alternative-023")
    control = next(r["oof_predictions"] for r in selection["results"] if r["candidate"]["algorithm"] == "control")
    np.testing.assert_array_equal(control, expected)
    winner = max(selection["results"], key=lambda r: r["accuracy_mean"])
    # Also refit a variant that actually changes decisions, even if a control
    # wins, so the signal path and corrector are exercised independently.
    alternatives = [r for r in selection["results"] if r["candidate"]["algorithm"] != "control" and r["changed_decisions"] > 0]
    checked = [winner]+([max(alternatives, key=lambda r: r["accuracy_mean"])] if alternatives else [])
    index = {key: i for i, key in enumerate(frame["row_key"])}
    positions = np.asarray([index[key] for key in train["row_key"]])
    train_windows, train_statistics = queries[positions], statistics[positions]
    for number, (fit, val) in enumerate(GroupKFold(n_splits=5).split(train, groups=train["group_key"])):
        evidence = selection["folds"][number]
        require(evidence["fit_row_keys"] == train.iloc[fit]["row_key"].tolist()
                and evidence["validation_row_keys"] == train.iloc[val]["row_key"].tolist()
                and not set(train.iloc[fit]["group_key"]) & set(train.iloc[val]["group_key"]), "Temporal outer participant fold changed")
        with threadpool_limits(limits=1):
            context, inner = temporal.inner_context(train.iloc[fit], selection["core_candidate"])
        require(inner == evidence["inner_folds"], "Temporal residual baseline leaked inner participants")
        np.testing.assert_allclose(context, evidence["fit_context"], rtol=0, atol=1e-12)
        for row in checked:
            candidate = row["candidate"]
            encoder = None if candidate["algorithm"] == "control" else encoders[candidate["source_encoder"]["id"]]
            states = {} if encoder is None else {k: v.clone() for k, v in encoder.encoder.state_dict().items()}
            refit = temporal.TemporalBorg(candidate, encoder).fit(train.iloc[fit], train_windows[fit], train_statistics[fit], selection["core_candidate"])
            predicted = refit.predict(train.iloc[val], train_windows[val], train_statistics[val])
            np.testing.assert_array_equal(predicted, np.asarray(row["oof_predictions"])[val])
            changed = train.iloc[val].copy()
            changed["label"], changed["row_key"], changed["group_key"] = "unavailable_target", "unused_query_id", "unused_person_id"
            np.testing.assert_array_equal(predicted, refit.predict(changed, train_windows[val], train_statistics[val]))
            if encoder is not None:
                require(all(torch.equal(value, states[key]) for key, value in encoder.encoder.state_dict().items()), "Native correction fine-tuned external temporal weights")
    if winner["accuracy_mean"] < .65:
        require(not (temporal.DIRECTORY / "evaluation/metrics.json").exists(), "Weak temporal selection bypassed its predeclared test gate")
    return {"publisher_verified_fitting_traces": 32, "raw_source_bytes": total_bytes, "source_people": 8,
            "source_export_rows": total_rows, "identical_consecutive_export_rows": repeated_rows, "observed_100ms_bins": total_bins,
            "unlabelled_source_windows": len(source), "unchanged_native_queries": 666, "native_queries_with_any_signal": 579,
            "source_borg_targets_used": 0, "f_level_used": False, "reserved_people_used": False,
            "raw_bin_and_window_values_independently_reconstructed": True, "source_encoders_refitted_independently": len(encoders),
            "native_oof_variants_refitted": [r["candidate"]["id"] for r in checked],
            "minimum_cv_for_new_test_evaluation": .65, "new_test_gate_passed": winner["accuracy_mean"] >= .65}
