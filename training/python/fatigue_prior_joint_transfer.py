"""Joint source/native learning from actual prior-conditioned public reports."""
from __future__ import annotations

import importlib.metadata
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from torch import nn

import fatigue_survey_prior_teachers as parent
from fatigue_joint_transfer import JointResidualNetwork,base_features,prepare_base
from public_sources import digest

DIRECTORY = parent.DIRECTORY.parent/"prior-conditioned-joint-transfer-80-v1"
COMMON = ["prior_borg","hr_last","hr_history_mean"]
_RUNTIME = None


class PriorTransitionNetwork(JointResidualNetwork):
    def source_prediction(self,sensor,domain):
        return self.source_heads[domain](self.encoder(sensor)).squeeze(1)


def load_inputs():
    inputs = parent.load_inputs()
    frame,train,test,members,external,provenance,_,_ = inputs
    originals,manifests,_ = parent.parent.source_inputs()
    pieces = []
    for name in ("worker","sts"):
        part = external[external.source_domain.eq(name)]
        clock = originals[name][["row_key","elapsed_minutes"]]
        joined = part.merge(clock,on="row_key",how="left",validate="one_to_one",sort=False)
        if joined.row_key.tolist() != part.row_key.tolist() or not np.isfinite(joined.elapsed_minutes).all() or (joined.elapsed_minutes < 0).any():
            raise ValueError("Source observed elapsed exposure is missing or misaligned; no clock filling allowed")
        pieces.append(joined)
    external = pd.concat(pieces,ignore_index=True)
    if len(external) != 302 or not external.row_key.is_unique or set(train.group_key) & set(external.group_key):
        raise ValueError("Original real source pairs changed or participant namespaces collide")
    context = list(dict.fromkeys(members["member_specifications"]["core"]["features"]+
        [f for f in members["member_specifications"]["cat"]["features"] if f != "current_terrain"]))
    if set(context) & {"label","row_key","group_key"}:
        raise ValueError("Current targets or identifiers cannot be shared native context")
    evidence = {"native_members":members,"source_pair_provenance_sha256":digest(parent.source.DIRECTORY/"provenance.json"),
        "original_source_dataset_sha256":{name:manifests[name]["dataset_sha256"] for name in ("worker","sts")},
        "context_features":context,"common_features":COMMON,
        "source_elapsed_clock_definition":{"worker":"Observed current repetition endpoint minus first working repetition start; not an invented Borg response time or age.",
            "sts":"Original relative recording Time at the actually observed Borg cell, in minutes."},
        "native_elapsed_clock_definition":"Known current task start to the original prediction time, in minutes.",
        "source_row_feature_hash":digest_frame(external)}
    return frame,train,test,external,evidence


def digest_frame(frame):
    import hashlib
    values = pd.util.hash_pandas_object(frame,index=False).to_numpy()
    return hashlib.sha256(values.tobytes()).hexdigest()


class PriorJointBorg:
    def __init__(self,candidate):
        self.candidate = candidate

    def shared_transform(self,frame):
        return torch.tensor(self.shared_scaler.transform(self.shared_imputer.transform(frame[self.candidate["common_features"]])),dtype=torch.float32)

    def context_transform(self,frame):
        return torch.tensor(self.context_scaler.transform(self.context_imputer.transform(frame[self.context_features])),dtype=torch.float32)

    def fit(self,frame,external,specification,context_features,cached=None,observer=None):
        parent.native.helpers.validate_calibration(frame)
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        cached = prepare_base(frame,specification) if cached is None else cached
        if cached["fit_row_keys"] != frame.row_key.tolist() or set(frame.group_key) & set(external.group_key):
            raise ValueError("Wrong native baseline cache or source/native person overlap")
        self.base = cached["base"]
        self.base.model.requires_grad_(False)
        self.context_features = list(context_features)
        self.input_features = list(dict.fromkeys(self.context_features+self.candidate["common_features"]))
        torch.manual_seed(42)
        columns = self.candidate["common_features"]
        union = pd.concat([frame[columns],external[columns]],ignore_index=True)
        self.shared_imputer = SimpleImputer(strategy="median",keep_empty_features=True,add_indicator=True)
        self.shared_scaler = StandardScaler().fit(self.shared_imputer.fit_transform(union))
        self.context_imputer = SimpleImputer(strategy="median",keep_empty_features=True,add_indicator=True)
        self.context_scaler = StandardScaler().fit(self.context_imputer.fit_transform(frame[self.context_features]))
        sensor,context,offsets = self.shared_transform(frame),self.context_transform(frame),cached["fit_logits"].detach()
        current = frame.label.str.removeprefix("Borg ").to_numpy(int)
        target = torch.tensor(current-frame.prior_borg.to_numpy(int)+10,dtype=torch.long)
        self.domains = sorted(external.source_domain.unique())
        self.source_report_counts = {name:int(external.source_domain.eq(name).sum()) for name in self.domains}
        auxiliary = {}
        for name in self.domains:
            rows = external[external.source_domain.eq(name)]
            actual,prior = rows.borg_native.to_numpy(float),rows.prior_borg.to_numpy(float)
            if not np.isfinite([actual,prior]).all() or np.any((actual < 0)|(actual > 10)|(prior < 0)|(prior > 10)):
                raise ValueError("Only unchanged original current/previous continuous CR10 values may supervise source heads")
            weights = 1./rows.groupby("group_key")["group_key"].transform("size").to_numpy()
            weights *= len(rows)/weights.sum()
            auxiliary[name] = self.shared_transform(rows),torch.tensor(actual-prior,dtype=torch.float32),torch.tensor(weights,dtype=torch.float32)
            if observer is not None:
                observer("source",name,rows[columns].copy(),actual.copy(),prior.copy())
        if observer is not None:
            observer("native","native",frame[self.input_features].copy(),current.copy(),frame.prior_borg.to_numpy(int).copy())
        self.network = PriorTransitionNetwork(sensor.shape[1],context.shape[1],self.domains)
        with torch.no_grad():
            initial = self.network.correction(sensor,context,offsets)
            if torch.count_nonzero(initial):
                raise ValueError("The initial native correction must leave the original baseline unchanged")
        optimizer = torch.optim.AdamW(self.network.parameters(),lr=.003,weight_decay=.1)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=max(1,self.candidate["epochs"]),eta_min=.0003)
        self.loss_endpoints = []
        for epoch in range(self.candidate["epochs"]):
            optimizer.zero_grad(set_to_none=True)
            correction = self.network.correction(sensor,context,offsets)
            classification = nn.functional.cross_entropy(offsets+correction,target)
            losses = {name:(nn.functional.smooth_l1_loss(self.network.source_prediction(x,name),y,beta=1.,reduction="none")*weight).sum()/weight.sum()
                for name,(x,y,weight) in auxiliary.items()}
            source_loss = torch.stack(list(losses.values())).mean()
            penalty = .1*correction.square().mean()
            total = classification+self.candidate["auxiliary_weight"]*source_loss+penalty
            if not torch.isfinite(total):
                raise ValueError("Nonfinite prior-conditioned joint likelihood")
            total.backward()
            if any(p.grad is not None and not torch.isfinite(p.grad).all() for p in self.network.parameters()):
                raise ValueError("Nonfinite prior-conditioned shared gradient")
            nn.utils.clip_grad_norm_(self.network.parameters(),5.)
            optimizer.step()
            scheduler.step()
            if epoch in (0,self.candidate["epochs"]-1):
                self.loss_endpoints.append({"total":float(total.detach()),"native_classification":float(classification.detach()),
                    "source_delta_mean":float(source_loss.detach()),"source_losses":{name:float(v.detach()) for name,v in losses.items()}})
        self.network.requires_grad_(False).eval()
        for parameter in self.network.parameters():
            parameter.grad = None
        self.training_summary = {"actual_native_targets":len(frame),"actual_source_targets":len(external),
            "source_report_counts":self.source_report_counts,"inner_participant_folds":3,
            "synthetic_training_rows":0,"artificial_input_masks":0,"invented_source_report_ages":0}
        return self

    def predict(self,frame):
        parent.native.helpers.validate_calibration(frame)
        with torch.no_grad():
            offsets = base_features(self.base,frame)[1]
            logits = offsets+self.network.correction(self.shared_transform(frame),self.context_transform(frame),offsets)
            if not torch.isfinite(logits).all():
                raise ValueError("Nonfinite corrected native Borg output")
            order = torch.tensor(self.base.model.priority)
            delta = order[logits[:,order].argmax(dim=1)].numpy()-10
        native = np.clip(delta+frame.prior_borg.to_numpy(int),0,10)
        return np.asarray([f"Borg {v}" for v in native])


def plan():
    result = [{"id":"prior-joint-000","algorithm":"previous_real_control","parent_candidate_id":"survey-teacher-000"},
              {"id":"prior-joint-001","algorithm":"previous_real_control","parent_candidate_id":"survey-teacher-001"}]
    for columns in (COMMON,COMMON+["elapsed_minutes"]):
        for weight in (0.,.1,1.):
            for epochs in (80,200):
                result.append({"id":f"prior-joint-{len(result):03d}","algorithm":"prior_conditioned_joint_residual",
                    "common_features":columns,"auxiliary_weight":weight,"epochs":epochs,
                    "source_target":"actual_current_borg_minus_actual_prior_borg","native_target":"original_integer_delta_class",
                    "source_heads":"separate_study_specific_continuous_delta_regression","random_seed":42})
    return result


def fingerprint(inputs):
    return {"code_sha256":digest(Path(__file__)),"inputs":inputs[4],"public_real_data_policy_sha256":digest(parent.native.POLICY),
        "previous_selection_sha256":digest(parent.DIRECTORY/"selection.json"),
        "dependency_code_sha256":{name:digest(Path(__file__).with_name(name)) for name in
            ("fatigue_joint_transfer.py","fatigue_survey_prior_teachers.py","fatigue_source_transitions.py","fatigue_worker_survey_priors.py",
             "fatigue_warm_sgd.py","fatigue_dynamics_experiment.py","fatigue_probability.py","fatigue_runner_real_observations.py")},
        "software_versions":{name:importlib.metadata.version(name) for name in ("torch","numpy","pandas","scikit-learn","joblib")},"worker_processes":2}


def save(report):
    path = DIRECTORY/"selection.json"
    payload = json.dumps(report,indent=2,allow_nan=False)+"\n"
    path.with_suffix(".tmp").write_text(payload,encoding="utf-8")
    path.write_text(payload,encoding="utf-8")


def worker_initialize():
    global _RUNTIME
    inputs = load_inputs()
    _RUNTIME = inputs,fingerprint(inputs)


def compute_fold(job):
    candidates,number,fit,val = job
    inputs,signature = _RUNTIME
    _,train,_,external,evidence = inputs
    fitting,validation = train.iloc[fit],train.iloc[val]
    if set(fitting.group_key) & set(validation.group_key):
        raise ValueError("Outer native fitting and validation people overlap")
    cache_path = DIRECTORY/"bases"/f"fold-{number}.joblib"
    metadata_path = cache_path.with_suffix(".json")
    identity = {"signature":signature,"fit_row_keys":fitting.row_key.tolist(),"validation_row_keys":validation.row_key.tolist(),"fold_number":number}
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text())
        if any(metadata.get(k) != v for k,v in identity.items()) or metadata["cache_sha256"] != digest(cache_path):
            raise ValueError("Nested original-report native baseline cache changed")
        cache = joblib.load(cache_path)
    else:
        cache = prepare_base(fitting,evidence["native_members"]["member_specifications"]["core"])
        joblib.dump(cache,cache_path)
        metadata = {**identity,"cache_sha256":digest(cache_path),"inner_folds":cache["inner_folds"]}
        metadata_path.write_text(json.dumps(metadata,indent=2)+"\n",encoding="utf-8")
    results = []
    for c in candidates:
        output = DIRECTORY/"folds"/f"{c['id']}-fold-{number}.json"
        row_identity = {**identity,"candidate":c}
        if output.exists():
            saved = json.loads(output.read_text())
            if any(saved.get(k) != v for k,v in row_identity.items()):
                raise ValueError("Saved prior-conditioned native recipe changed")
        else:
            model = PriorJointBorg(c).fit(fitting,external,evidence["native_members"]["member_specifications"]["core"],evidence["context_features"],cache)
            predicted = model.predict(validation)
            saved = {**row_identity,"predicted":predicted.tolist(),"training_summary":model.training_summary,"loss_endpoints":model.loss_endpoints}
            output.write_text(json.dumps(saved,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        results.append(saved)
    return number,results


def select():
    inputs = load_inputs()
    _,train,test,_,evidence = inputs
    signature = fingerprint(inputs)
    DIRECTORY.mkdir(exist_ok=True)
    for name in ("bases","folds"):
        (DIRECTORY/name).mkdir(exist_ok=True)
    report = {**signature,"version":1,"status":"running","plan":plan(),"results":[],"train_row_keys":train.row_key.tolist(),
        "target_accuracy":.8,"evaluation_denominator":len(train),"test_denominator":len(test),"test_used_for_selection":False,
        "previous_benchmark_results_are_published":True,"minimum_cv_for_new_test_evaluation":.65,"actual_public_source_targets":302,
        "new_native_borg_targets":0,"synthetic_training_rows":0,"invented_source_report_ages":0,
        "policy":"Actual public prior/current responses and HR only; elapsed context is measured at the published recording point, not an invented source survey age. Study-specific heads preserve source outcome context. Native residual offsets are three-fold cross-fitted inside each original participant-disjoint outer fold. No artificial examples, history masking, target conversion, validation stopping or test tuning."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k,v in signature.items()) or old["plan"] != plan() or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen prior-conditioned joint study changed")
        report = old
    else:
        save(report)
    if report["status"] == "complete":
        return report
    candidates = [c for c in report["plan"] if c["algorithm"] != "previous_real_control"]
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    with ProcessPoolExecutor(max_workers=2,initializer=worker_initialize) as pool:
        futures = [pool.submit(compute_fold,(candidates,number,fit,val)) for number,(fit,val) in enumerate(folds)]
        for future in as_completed(futures):
            number,rows = future.result()
            print(f"Prior-conditioned joint native fold {number+1}/5 complete: {len(rows)} recipes, original reports only",flush=True)
    previous = json.loads((parent.DIRECTORY/"selection.json").read_text())
    for c in report["plan"]:
        if any(r["candidate"] == c for r in report["results"]):
            continue
        if c["algorithm"] == "previous_real_control":
            old = next(r for r in previous["results"] if r["candidate"]["id"] == c["parent_candidate_id"])
            predicted,details = np.asarray(old["oof_predictions"]),[]
        else:
            predicted,details = np.empty(len(train),dtype=object),[]
            for number,(_,val) in enumerate(folds):
                saved = json.loads((DIRECTORY/"folds"/f"{c['id']}-fold-{number}.json").read_text())
                predicted[val] = saved["predicted"]
                details.append(saved)
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        report["results"].append({"candidate":c,"accuracy_mean":float(np.mean(scores)),"fold_accuracy":scores,
            "pooled_oof_accuracy":float(accuracy_score(train.label,predicted)),"oof_predictions":predicted.tolist(),"folds":details})
        best = max(report["results"],key=lambda r:r["accuracy_mean"])
        report.update(winner_id=best["candidate"]["id"],best_cv_accuracy=best["accuracy_mean"])
        save(report)
        print(f"Prior-conditioned joint recipe {len(report['results'])}/14 {c['id']}: CV={np.mean(scores):.6f}",flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    select()
