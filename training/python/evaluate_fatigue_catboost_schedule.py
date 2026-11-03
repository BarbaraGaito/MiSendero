"""Freeze/reload only the sole CV-qualified native CatBoost schedule."""
import json
from datetime import datetime,timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import fatigue_catboost_schedule as study
from public_sources import digest


def evaluate():
    inputs = study.load_inputs()
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    winner = max(selection["results"],key=lambda r:r["accuracy_mean"])
    if (selection["status"] != "complete" or selection["plan"] != study.plan()
        or any(selection.get(k) != v for k,v in study.fingerprint(inputs).items())
        or selection["test_used_for_selection"] or selection["winner_id"] != winner["candidate"]["id"]
        or selection["best_cv_accuracy"] != winner["accuracy_mean"]
        or selection["matched_original_prefix_controls_verified"] != 10):
        raise ValueError("Only the unchanged completed original-person CVselection may qualify")
    directory = study.DIRECTORY/"evaluation"
    qualified = winner["candidate"]["algorithm"] != "previous_real_control" and winner["accuracy_mean"] >= .65
    if not qualified:
        if (directory/"metrics.json").exists():
            raise ValueError("A new test exists below the predeclared CVgate")
        return {"evaluation_performed":False,"reason":"No new winner reached the predeclared .65CVgate",
            "winner_id":selection["winner_id"],"best_cv_accuracy":selection["best_cv_accuracy"],"original_test_cases":179}
    identity = {"signature":study.fingerprint(inputs),"selection_sha256":digest(path),
        "candidate":winner["candidate"],"evaluation_code_sha256":digest(Path(__file__)),
        "original_train_row_keys":inputs["train"].row_key.tolist(),"original_test_row_keys":inputs["test"].row_key.tolist(),
        "training_cases":487,"test_cases":179,"test_used_for_selection":False,
        "artifact_frozen_before_test_prediction":True,"deployment_approved":False}
    directory.mkdir(exist_ok=True)
    artifact,descriptor_path = directory/"model.joblib",directory/"pre-test-model.json"
    if not descriptor_path.exists():
        model = study.ScheduledCatBoostBorg(winner["candidate"]).fit(inputs["train"])
        joblib.dump(model,artifact)
        descriptor = {**identity,"frozen_at":datetime.now(timezone.utc).isoformat(),"model_sha256":digest(artifact),
            "optimizer_summary":model.optimizer_summary,"runtime_input_features":model.input_features}
        descriptor_path.write_text(json.dumps(descriptor,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    descriptor = json.loads(descriptor_path.read_text())
    if any(descriptor.get(k) != v for k,v in identity.items()) or descriptor["model_sha256"] != digest(artifact):
        raise ValueError("The frozen sole CatBoost schedule artifact changed")
    model = joblib.load(artifact)
    test = inputs["test"]
    predicted = model.predict(test[model.input_features])
    if len(predicted) != 179 or not set(predicted)<={f"Borg {i}" for i in range(11)}:
        raise ValueError("The original native test population or Borgscale changed")
    correct = int((predicted == test.label.to_numpy()).sum())
    metrics = {"version":1,"evaluation_performed":True,"descriptor_sha256":digest(descriptor_path),
        "model_sha256":digest(artifact),"selection_sha256":digest(path),"winner_id":selection["winner_id"],
        "selected_cv_accuracy":winner["accuracy_mean"],"test_accuracy":correct/179,"correct":correct,"cases":179,
        "original_training_cases":487,"test_used_for_selection":False,"required_correct_for_80_percent":144,
        "target_accuracy":.8,"achieved":correct>=144,
        "scope":"Unchanged179native exactBorgcases after frozen original-person CVselection. Sole selected fixed-rate/tree-budget classifier fitted only on487actualnative outcomes,serialized with descriptor before test prediction,and reloaded. No generated rows,source targets,adaptive scheduler,test-directed early stopping or denominator change."}
    output = test[["row_key","group_key","label"]].copy().reset_index(drop=True)
    output["predicted"] = predicted
    predictions_path,metrics_path = directory/"predictions.csv",directory/"metrics.json"
    if predictions_path.exists():
        pd.testing.assert_frame_equal(pd.read_csv(predictions_path),output,check_dtype=False)
    else:
        output.to_csv(predictions_path,index=False)
    if metrics_path.exists() and json.loads(metrics_path.read_text()) != metrics:
        raise ValueError("Frozen original-test metrics no longer reproduce")
    metrics_path.write_text(json.dumps(metrics,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    np.testing.assert_array_equal(joblib.load(artifact).predict(test[model.input_features]),predicted)
    return metrics


if __name__ == "__main__":
    print(json.dumps(evaluate(),indent=2,allow_nan=False),flush=True)
