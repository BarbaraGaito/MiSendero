"""Describe frozen fitting-loss/CV budget pairs without fitting or using new test."""
import json
from pathlib import Path

import numpy as np

import fatigue_two_history_joint as study
from public_sources import digest


def diagnose():
    path = study.DIRECTORY/"selection.json"
    selection = json.loads(path.read_text())
    assert selection["status"] == "complete" and selection["code_sha256"] == digest(Path(study.__file__))
    results = []
    for member in ("core","cat"):
        for weight in (0.,.1,1.):
            pair = {epochs:next(r for r in selection["results"] if r["candidate"].get("member") == member
                and r["candidate"].get("auxiliary_weight") == weight and r["candidate"].get("epochs") == epochs) for epochs in (80,200)}
            native_loss = {epochs:float(np.mean([f["loss_endpoints"][-1]["native_classification"] for f in row["folds"]])) for epochs,row in pair.items()}
            results.append({"member":member,"auxiliary_weight":weight,"cv80":pair[80]["accuracy_mean"],"cv200":pair[200]["accuracy_mean"],
                "cv_change200_minus80":pair[200]["accuracy_mean"]-pair[80]["accuracy_mean"],"mean_native_fitting_loss_by_budget":native_loss,
                "native_fitting_loss_decreased_at200":native_loss[200] < native_loss[80],"cv_decreased_at200":pair[200]["accuracy_mean"] < pair[80]["accuracy_mean"]})
    report = {"version":1,"code_sha256":digest(Path(__file__)),"selection_sha256":digest(path),"paired_native_configurations":results,
        "pairs_with_lower_fitting_loss_and_lower_cv_at200":sum(r["native_fitting_loss_decreased_at200"] and r["cv_decreased_at200"] for r in results),
        "source_reserved_targets_used":False,"native_test_targets_used":False,"new_model_fitting_started":False,
        "scope":"Descriptive paired80/200epoch comparisons from the frozen original person CV and fitting loss endpoints. Lower fitting loss with lower CV is evidence consistent with overfitting,not proof of a future gain. Use an actually different regularization/data axis rather than repeat the same epoch grid; original source/native labels and case counts remain unchanged."}
    output = study.DOCS/"two-history-joint-regularization-diagnostic.json"
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(report),flush=True)
    return report


if __name__ == "__main__":
    diagnose()
