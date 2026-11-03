"""Freeze and evaluate the sole CV-qualified joint-history winner on original179."""
from __future__ import annotations

import json
from datetime import datetime,timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import accuracy_score

import fatigue_two_history_joint as study
from public_sources import digest


def evaluate():
    inputs = study.load_inputs()
    signature = study.fingerprint(inputs)
    selection_path = study.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    if (selection["status"] != "complete" or selection["plan"] != study.plan(inputs["previous_audit"])
        or any(selection.get(k) != v for k,v in signature.items()) or selection["test_used_for_selection"]):
        raise ValueError("Native CV selection must be complete and unchanged before test")
    winner = max(selection["results"],key=lambda r:r["accuracy_mean"])
    if winner["candidate"]["id"] != selection["winner_id"] or winner["accuracy_mean"] != selection["best_cv_accuracy"]:
        raise ValueError("The test candidate differs from the frozen full-CV winner")
    if winner["accuracy_mean"] < selection["minimum_cv_for_new_test_evaluation"] or winner["candidate"]["algorithm"] == "previous_real_control":
        return {"evaluation_performed":False,"reason":"No new native CV winner reached the predeclared .65 gate",
            "winner_id":selection["winner_id"],"best_cv_accuracy":selection["best_cv_accuracy"],"original_test_cases":179}
    directory = study.DIRECTORY/"evaluation"
    directory.mkdir(exist_ok=True)
    artifact = directory/"model.joblib"
    descriptor_path = directory/"pre-test-model.json"
    candidate = winner["candidate"]
    identity = {"signature":signature,"selection_sha256":digest(selection_path),"candidate":candidate,
        "evaluation_code_sha256":digest(Path(__file__)),"original_train_row_keys":inputs["train"].row_key.tolist(),
        "original_test_row_keys":inputs["test"].row_key.tolist(),"training_cases":487,"test_cases":179,
        "test_used_for_selection":False,"artifact_frozen_before_test_prediction":True,"deployment_approved":False}
    if descriptor_path.exists():
        descriptor = json.loads(descriptor_path.read_text())
        if any(descriptor.get(k) != v for k,v in identity.items()) or descriptor["model_sha256"] != digest(artifact):
            raise ValueError("Previously frozen joint-history test artifact changed")
    else:
        cache = study.prepare_base(inputs["train"],candidate["member"],inputs["specifications"][candidate["member"]])
        model = study.JointHistoryBorg(candidate).fit(inputs["train"],inputs["source"],inputs["specifications"][candidate["member"]],
            inputs["context_features"],cached=cache)
        joblib.dump(model,artifact)
        descriptor = {**identity,"frozen_at":datetime.now(timezone.utc).isoformat(),"model_sha256":digest(artifact),
            "training_summary":model.training_summary,"loss_endpoints":model.loss_endpoints,"runtime_input_features":model.input_features}
        descriptor_path.write_text(json.dumps(descriptor,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    # Load the already-written model/descriptor before any test prediction.
    model = joblib.load(artifact)
    test = inputs["test"]
    prediction = model.predict(test[model.input_features])
    if len(prediction) != 179 or not set(prediction)<={f"Borg {i}" for i in range(11)}:
        raise ValueError("Joint-history test output changed original denominator or native scale")
    actual = test.label.to_numpy()
    correct = int((prediction == actual).sum())
    metrics = {"version":1,"evaluation_performed":True,"descriptor_sha256":digest(descriptor_path),
        "model_sha256":digest(artifact),"selection_sha256":digest(selection_path),"winner_id":selection["winner_id"],
        "selected_cv_accuracy":winner["accuracy_mean"],"test_accuracy":float(accuracy_score(actual,prediction)),
        "correct":correct,"cases":179,"original_training_cases":487,"test_used_for_selection":False,
        "required_correct_for_80_percent":144,"target_accuracy":.8,"achieved":correct>=144,
        "scope":"Original179participant-held exact Borg labels only, after one frozen full-CV selection. Serialized joint model reloaded before test; runtime query excludes current truth and IDs. Public actual source histories only,57source targets reserved; no changed labels, synthetic examples or case filtering."}
    metrics_path = directory/"metrics.json"
    if metrics_path.exists() and json.loads(metrics_path.read_text()) != metrics:
        raise ValueError("Saved frozen joint-history test metrics do not reproduce")
    output = test[["row_key","group_key","label"]].copy()
    output["predicted"] = prediction
    csv_path = directory/"predictions.csv"
    if csv_path.exists():
        import pandas as pd
        pd.testing.assert_frame_equal(pd.read_csv(csv_path),output.reset_index(drop=True),check_dtype=False)
    else:
        output.to_csv(csv_path,index=False)
    metrics_path.write_text(json.dumps(metrics,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    np.testing.assert_array_equal(joblib.load(artifact).predict(test[model.input_features]),prediction)
    return metrics


if __name__ == "__main__":
    print(json.dumps(evaluate(),indent=2,allow_nan=False))
