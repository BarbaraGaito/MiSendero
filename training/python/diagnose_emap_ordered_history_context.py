"""Describe fitting-only ordered RPE changes without fitting or using native test targets."""
import json
from pathlib import Path

import numpy as np

import fatigue_catboost as native
import fatigue_emap_history_inputs as source
from public_sources import digest


def describe(current,prior,second):
    delta = np.asarray(current,float)-np.asarray(prior,float)
    values,counts = np.unique(delta,return_counts=True)
    return {"actual_pairs":len(delta),"actual_second_priors":int(np.isfinite(second).sum()),
        "current_rpe_mean":float(np.mean(current)),"prior_rpe_mean":float(np.mean(prior)),
        "delta_mean":float(np.mean(delta)),"delta_median":float(np.median(delta)),
        "delta_range":[float(delta.min()),float(delta.max())],"unchanged_pairs":int((delta == 0).sum()),
        "decreasing_pairs":int((delta<0).sum()),"increasing_pairs":int((delta>0).sum()),
        "actual_delta_counts":{str(float(value)):int(count) for value,count in zip(values,counts)}}


def diagnose():
    data,provenance = source.load()
    emap = data[data.source_domain.eq("emap")&data.source_partition.eq("fitting")]
    _,train,test,manifest,_ = native.load_inputs()
    assert len(emap) == 248 and len(train) == 487 and len(test) == 179
    by_slot = {str(int(slot)):describe(part.current_rpe,part.prior_borg,part.prior2_borg.to_numpy(float))
        for slot,part in emap.groupby("current_slot")}
    target = train.label.str.removeprefix("Borg ").astype(int).to_numpy()
    report = {"version":1,"code_sha256":digest(Path(__file__)),"source_provenance_sha256":digest(source.DIRECTORY/"provenance.json"),
        "native_dataset_sha256":manifest["dataset_sha256"],"original_native_training_cases":487,"original_native_test_cases":179,
        "emap_fitting_ordered_changes":by_slot,"emap_fitting_all_slots":describe(emap.current_rpe,emap.prior_borg,emap.prior2_borg.to_numpy(float)),
        "native_fitting_changes":describe(target,train.prior_borg,train.prior2_borg.to_numpy(float)),
        "emap_reserved_targets_used":False,"native_test_targets_used":False,"source_model_fitting_started":False,
        "slot_phase_equivalence_to_native_asserted":False,"synthetic_rows":0,"invented_clocks":0,
        "scope":"Descriptive fitting-only current-minus-genuine-prior distributions. SourceT2/T3/T4 denote recorded questionnaire order without invented exact times or correspondence to native terrain/task phase. No reserved source/native targets used for these statistics and no estimator fitted."}
    (source.DOCS/"emap-ordered-history-context-diagnostic.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(report),flush=True)


if __name__ == "__main__":
    diagnose()
