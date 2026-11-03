"""Freeze and reload only the sole CV-qualified runner HR transfer winner."""
from __future__ import annotations

import json
from datetime import datetime,timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import fatigue_furukawa_hr_transfer as study
from public_sources import digest


def frozen_identity(inputs,selection):
    winner = max(selection["results"],key=lambda r:r["accuracy_mean"])
    if (selection["status"] != "complete" or selection["plan"] != study.plan()
        or any(selection.get(k) != v for k,v in study.fingerprint(inputs).items())
        or selection["test_used_for_selection"] or winner["candidate"]["id"] != selection["winner_id"]
        or winner["accuracy_mean"] != selection["best_cv_accuracy"]):
        raise ValueError("Only the unchanged complete original-person CVselection may qualify for test")
    qualified = winner["candidate"]["algorithm"] != "previous_real_control" and winner["accuracy_mean"] >= .65
    return winner,qualified,{"signature":study.fingerprint(inputs),"selection_sha256":digest(study.DIRECTORY/"selection.json"),
        "candidate":winner["candidate"],"evaluation_code_sha256":digest(Path(__file__)),
        "original_train_row_keys":inputs["train"].row_key.tolist(),"original_test_row_keys":inputs["test"].row_key.tolist(),
        "training_cases":487,"test_cases":179,"test_used_for_selection":False,"artifact_frozen_before_test_prediction":True,
        "deployment_approved":False}


def verify_frozen_evaluation(inputs,selection):
    winner,qualified,identity = frozen_identity(inputs,selection)
    if not qualified:
        raise ValueError("No new winner passed the predeclared .65CVtest gate")
    directory = study.DIRECTORY/"evaluation"
    artifact,descriptor_path = directory/"model.joblib",directory/"pre-test-model.json"
    descriptor = json.loads(descriptor_path.read_text())
    if any(descriptor.get(k) != v for k,v in identity.items()) or descriptor["model_sha256"] != digest(artifact):
        raise ValueError("The frozen original runnerHRtest artifact changed")
    model = joblib.load(artifact)
    test = inputs["test"]
    prediction = model.predict(test[model.input_features])
    if len(prediction) != 179 or not set(prediction)<={f"Borg {i}" for i in range(11)}:
        raise ValueError("Original test cases or native Borgscale changed")
    correct = int((prediction == test.label.to_numpy()).sum())
    metrics = {"version":1,"evaluation_performed":True,"descriptor_sha256":digest(descriptor_path),
        "model_sha256":digest(artifact),"selection_sha256":digest(study.DIRECTORY/"selection.json"),
        "winner_id":selection["winner_id"],"selected_cv_accuracy":winner["accuracy_mean"],"test_accuracy":correct/179,
        "correct":correct,"cases":179,"original_training_cases":487,"test_used_for_selection":False,
        "required_correct_for_80_percent":144,"target_accuracy":.8,"achieved":correct>=144,
        "scope":"Unchanged179native exactBorgcases after frozen original-person CVselection. Serialized model/descriptor written before test prediction and reloaded. Source functions use252actual original-point states or168actual deltas from12people;84source responses remain reserved. No generated rows,source-native outcome conversion or altered denominator."}
    output = test[["row_key","group_key","label"]].copy().reset_index(drop=True)
    output["predicted"] = prediction
    csv_path,metrics_path = directory/"predictions.csv",directory/"metrics.json"
    if csv_path.exists():
        pd.testing.assert_frame_equal(pd.read_csv(csv_path),output,check_dtype=False)
    else:
        output.to_csv(csv_path,index=False)
    if metrics_path.exists() and json.loads(metrics_path.read_text()) != metrics:
        raise ValueError("Frozen original test metrics no longer reproduce")
    metrics_path.write_text(json.dumps(metrics,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    np.testing.assert_array_equal(joblib.load(artifact).predict(test[model.input_features]),prediction)
    return metrics


def evaluate():
    inputs = study.load_inputs()
    selection = json.loads((study.DIRECTORY/"selection.json").read_text())
    winner,qualified,identity = frozen_identity(inputs,selection)
    if not qualified:
        if (study.DIRECTORY/"evaluation/metrics.json").exists():
            raise ValueError("A new test exists below the predeclared CVgate")
        return {"evaluation_performed":False,"reason":"No new winner reached the predeclared .65CVgate",
            "winner_id":selection["winner_id"],"best_cv_accuracy":selection["best_cv_accuracy"],"original_test_cases":179}
    directory = study.DIRECTORY/"evaluation"
    directory.mkdir(exist_ok=True)
    artifact,descriptor_path = directory/"model.joblib",directory/"pre-test-model.json"
    if not descriptor_path.exists():
        candidate = winner["candidate"]
        teachers = study.read_sources(inputs)
        teacher = teachers[candidate["source_algorithm"]+"-"+candidate["source_task"]] if candidate["algorithm"] == "furukawa_source_function" else None
        model = study.RunnerHRBorg(candidate,teacher).fit(inputs["train"],inputs["specifications"])
        joblib.dump(model,artifact)
        descriptor = {**identity,"frozen_at":datetime.now(timezone.utc).isoformat(),"model_sha256":digest(artifact),
            "optimizer_summary":model.optimizer_summary,"runtime_input_features":model.input_features}
        descriptor_path.write_text(json.dumps(descriptor,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return verify_frozen_evaluation(inputs,selection)


if __name__ == "__main__":
    print(json.dumps(evaluate(),indent=2,allow_nan=False),flush=True)
