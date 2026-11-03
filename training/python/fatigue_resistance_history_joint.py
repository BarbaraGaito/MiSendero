"""Joint real-history transfer with an independently audited resistance source.

Preserve the preceding source normalization and initial weights, append one
separate original-resistance delta head, and tune correction regularization.
"""
from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
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

import fatigue_resistance_history_inputs as source
import fatigue_two_history_joint as previous
from fatigue_probability import validate_calibration
from public_sources import digest

DIRECTORY = previous.DIRECTORY.parent/"resistance-history-joint-transfer-80-v1"
DOCS = previous.DOCS
PARENT_AUDIT = DOCS/"two-history-joint-verification.json"
INPUT_AUDIT = DOCS/"resistance-history-input-verification.json"
PROPOSAL = DOCS/"resistance-history-expansion-proposal.md"
DIAGNOSTIC = DOCS/"two-history-joint-regularization-diagnostic.json"
COMMON = previous.COMMON
TARGETS = source.TARGETS
SOURCE_COUNTS = {**previous.SOURCE_COUNTS,"resistance":866}
_RUNTIME = None


def plan(proof):
    controls = ["two-history-joint-000","two-history-joint-001"]+[
        proof["best_positive_by_member"][member]["candidate"]["id"] for member in ("core","cat")]
    result = [{"id":f"resistance-joint-{i:03d}","algorithm":"previous_real_control","parent_candidate_id":key}
        for i,key in enumerate(controls)]
    for member in ("core","cat"):
        parent = proof["best_positive_by_member"][member]["candidate"]
        if parent["epochs"] != 80 or parent["auxiliary_weight"] != (.1 if member == "core" else 1.):
            raise ValueError("The predeclared positive history controls changed")
        for penalty in (.1,1.,10.):
            for weight in (0.,.1,1.):
                result.append({"id":f"resistance-joint-{len(result):03d}",
                    "algorithm":"joint_original_resistance_history_residual","member":member,
                    "previous_candidate_id":parent["id"],"auxiliary_weight":parent["auxiliary_weight"],
                    "resistance_weight":weight,"correction_penalty":penalty,"epochs":80,
                    "learning_rate":.003,"weight_decay":.1,"random_seed":42,
                    "base_probability_floor":previous.FLOOR,
                    "source_target":"separate_original_continuous_current_minus_actual_prior",
                    "native_target":"original_integer_delta_class"})
    return result


def load_inputs():
    old = previous.load_inputs()
    selection_path = previous.DIRECTORY/"selection.json"
    selection = json.loads(selection_path.read_text())
    proof = json.loads(PARENT_AUDIT.read_text())
    if (selection["status"] != "complete" or len(selection["results"]) != 16
        or any(selection.get(k) != v for k,v in previous.fingerprint(old).items())
        or proof["selection_sha256"] != digest(selection_path)
        or proof["verification_code_sha256"] != digest(Path(__file__).with_name("audit_fatigue_two_history_joint.py"))
        or proof["native_base_caches_checked"] != 10 or proof["cached_native_base_fit_models_checked"] != 40
        or proof["actual_native_joint_refits"] != 20 or not proof["native_base_weights_frozen"]):
        raise ValueError("The original-native bases and preceding history comparison are not verified")
    for name,expected in proof["native_base_artifact_hashes"].items():
        if digest(previous.DIRECTORY/"bases"/name) != expected:
            raise ValueError("A frozen original-native base cache changed")
    external,manifest = source.load()
    audit = json.loads(INPUT_AUDIT.read_text())
    if (audit["verification"] != "passed"
        or audit["audit_code_sha256"] != digest(Path(__file__).with_name("audit_resistance_history_inputs.py"))
        or audit["source_preparation_code_sha256"] != digest(Path(source.__file__))
        or audit["source_provenance_sha256"] != digest(source.DIRECTORY/"provenance.json")
        or not audit["source_outcomes_kept_separate"] or audit["synthetic_rows"] != 0):
        raise ValueError("The original manual resistance-history input audit changed")
    fitting = external[external.source_partition.eq("fitting")].copy()
    reserved = external[external.source_partition.eq("reserved")].copy()
    old_columns = old["source"].columns
    pd.testing.assert_frame_equal(fitting[fitting.source_domain.ne("resistance")][old_columns].reset_index(drop=True),
        old["source"].reset_index(drop=True),check_dtype=False,rtol=0,atol=0)
    if ((len(old["frame"]),len(old["train"]),len(old["test"]),len(fitting),len(reserved)) != (666,487,179,1416,125)
        or fitting.groupby("source_domain").size().to_dict() != SOURCE_COUNTS
        or fitting[source.SECOND].notna().sum() != 1169
        or set(fitting.group_key)&set(reserved.group_key)
        or set(old["frame"].group_key)&set(external.group_key)):
        raise ValueError("Original native cases or whole-source-person reservations changed")
    return {**old,"source":fitting,"reserved_source":reserved,"source_manifest":manifest,
        "previous_inputs":old,"previous":selection,"previous_audit":proof}


def fingerprint(inputs):
    return {"code_sha256":digest(Path(__file__)),"previous_signature":previous.fingerprint(inputs["previous_inputs"]),
        "previous_selection_sha256":digest(previous.DIRECTORY/"selection.json"),
        "previous_verification_sha256":digest(PARENT_AUDIT),"source_provenance_sha256":digest(source.DIRECTORY/"provenance.json"),
        "source_input_verification_sha256":digest(INPUT_AUDIT),"source_dataset_sha256":inputs["source_manifest"]["dataset_sha256"],
        "proposal_sha256":digest(PROPOSAL),"regularization_diagnostic_sha256":digest(DIAGNOSTIC),
        "native_base_artifact_hashes":inputs["previous_audit"]["native_base_artifact_hashes"],
        "native_specifications":inputs["specifications"],"native_context_features":inputs["context_features"],
        "dependency_code_sha256":{"fatigue_resistance_history_inputs.py":digest(Path(source.__file__)),
            "fatigue_two_history_joint.py":digest(Path(previous.__file__))},
        "public_real_data_policy_sha256":digest(DOCS/"public-real-data-policy.json"),"worker_processes":2}


class ResistanceHistoryNetwork(previous.HistoryNetwork):
    def __init__(self,n_history,n_context):
        # Initialize every preceding parameter before appending the new head.
        super().__init__(n_history,n_context,sorted(previous.SOURCE_COUNTS))
        self.source_heads["resistance"] = nn.Linear(8,1)


class ResistanceHistoryBorg(previous.JointHistoryBorg):
    def fit(self,frame,external,specification,context_features,cached=None,observer=None,batch_observer=None):
        validate_calibration(frame)
        if (len(external) != 1416 or external.groupby("source_domain").size().to_dict() != SOURCE_COUNTS
            or not external.source_partition.eq("fitting").all() or set(frame.group_key)&set(external.group_key)):
            raise ValueError("Only the1416original fitting-source cases may fit this comparison")
        if cached is None or cached["fit_row_keys"] != frame.row_key.tolist() or cached["base"].member != self.candidate["member"]:
            raise ValueError("A matching frozen original-native base cache is required")
        if cached["base"].specification != specification:
            raise ValueError("Frozen native base parameters changed")
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        c = self.candidate
        self.base,self.context_features = cached["base"],list(context_features)
        self.input_features = list(dict.fromkeys(self.base.input_features+self.context_features))
        before = joblib.hash(cached)
        torch.manual_seed(c["random_seed"])
        old_external = external[external.source_domain.ne("resistance")]
        union = pd.concat([previous.history_query(frame),previous.history_query(old_external)],ignore_index=True)
        self.history_imputer = SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True)
        self.history_scaler = StandardScaler().fit(self.history_imputer.fit_transform(union))
        self.context_imputer = SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True)
        self.context_scaler = StandardScaler().fit(self.context_imputer.fit_transform(frame[self.context_features]))
        history,context = self.history_transform(frame),self.context_transform(frame)
        offsets = cached["fit_logits"].detach()
        current,prior = frame.label.str.removeprefix("Borg ").to_numpy(int),frame.prior_borg.to_numpy(int)
        target = torch.as_tensor(current-prior+10,dtype=torch.long)
        self.domains = sorted(previous.SOURCE_COUNTS)+["resistance"]
        self.network = ResistanceHistoryNetwork(history.shape[1],context.shape[1])
        with torch.no_grad():
            if torch.count_nonzero(self.network.correction(history,context,offsets)):
                raise ValueError("Initial native correction must be zero")
        active = self.domains if c["resistance_weight"] > 0 else self.domains[:-1]
        auxiliary = {}
        for domain in active:
            part = external[external.source_domain.eq(domain)]
            actual,old = part[TARGETS[domain]].to_numpy(float),part[source.PRIOR].to_numpy(float)
            lower = 1 if domain == "resistance" else 0
            if not np.isfinite([actual,old]).all() or np.any((actual<lower)|(actual>10)|(old<lower)|(old>10)):
                raise ValueError("Only original observed continuous source outcomes can supervise each separate head")
            weights = 1./part.groupby("group_key").group_key.transform("size").to_numpy()
            weights *= len(part)/weights.sum()
            auxiliary[domain] = self.history_transform(part),torch.as_tensor(actual-old,dtype=torch.float32),torch.as_tensor(weights,dtype=torch.float32)
            if observer is not None:
                observer("source",domain,part[COMMON].copy(),actual.copy(),old.copy())
        if not c["resistance_weight"]:
            self.network.source_heads["resistance"].requires_grad_(False)
        if observer is not None:
            observer("native","native",frame[self.input_features].copy(),current.copy(),prior.copy())
        optimizer = torch.optim.AdamW(self.network.parameters(),lr=c["learning_rate"],weight_decay=c["weight_decay"])
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=c["epochs"],eta_min=.0003)
        self.loss_endpoints = []
        initial_gradient,initial_new_gradient = None,0.
        for epoch in range(c["epochs"]):
            optimizer.zero_grad(set_to_none=True)
            correction = self.network.correction(history,context,offsets)
            classification = nn.functional.cross_entropy(offsets+correction,target)
            losses = {domain:(nn.functional.smooth_l1_loss(self.network.source_prediction(x,domain),y,beta=1.,reduction="none")*w).sum()/w.sum()
                for domain,(x,y,w) in auxiliary.items()}
            old_mean = torch.stack([losses[d] for d in self.domains[:-1]]).mean()
            source_loss = old_mean if not c["resistance_weight"] else (3*old_mean+c["resistance_weight"]*losses["resistance"])/(3+c["resistance_weight"])
            total = classification+c["auxiliary_weight"]*source_loss+c["correction_penalty"]*correction.square().mean()
            if not torch.isfinite(total):
                raise ValueError("Nonfinite original-resistance joint loss")
            if batch_observer is not None:
                batch_observer(epoch,history.detach().numpy().copy(),target.numpy().copy(),
                    {domain:(x.numpy().copy(),y.numpy().copy(),w.numpy().copy()) for domain,(x,y,w) in auxiliary.items()})
            if epoch == 0 and c["resistance_weight"] > 0:
                gradients = torch.autograd.grad(c["auxiliary_weight"]*c["resistance_weight"]*losses["resistance"]/(3+c["resistance_weight"]),
                    tuple(self.network.encoder.parameters()),retain_graph=True)
                initial_new_gradient = float(torch.sqrt(sum(g.square().sum() for g in gradients)))
                if not initial_new_gradient > 0:
                    raise ValueError("Original resistance supervision did not reach the shared encoder")
            total.backward()
            if any(p.grad is not None and not torch.isfinite(p.grad).all() for p in self.network.parameters()):
                raise ValueError("Nonfinite actual-source joint gradient")
            if epoch == 0:
                initial_gradient = float(torch.sqrt(sum(p.grad.square().sum() for p in self.network.encoder.parameters() if p.grad is not None)))
                if not initial_gradient > 0:
                    raise ValueError("Original source heads did not supervise the encoder")
            nn.utils.clip_grad_norm_(self.network.parameters(),5.)
            optimizer.step()
            scheduler.step()
            if epoch in (0,c["epochs"]-1):
                self.loss_endpoints.append({"epoch":epoch,"total":float(total.detach()),"native_classification":float(classification.detach()),
                    "source_delta_mean":float(source_loss.detach()),"source_losses":{d:float(v.detach()) for d,v in losses.items()}})
        self.network.requires_grad_(False).eval()
        for p in self.network.parameters():
            p.grad = None
        if joblib.hash(cached) != before:
            raise ValueError("Joint backpropagation changed a frozen original-native base/cache")
        self.training_summary = {"actual_native_targets":len(frame),"source_input_rows_for_shared_preprocessing":550,
            "source_fitting_targets_available":1416,"actual_source_targets_in_objective":1416 if c["resistance_weight"] else 550,
            "source_targets_by_separate_head":{d:SOURCE_COUNTS[d] for d in active},
            "resistance_source_targets_in_objective":866 if c["resistance_weight"] else 0,
            "source_fitting_actual_second_priors":1169,"native_actual_second_priors":int(frame.prior2_borg.notna().sum()),
            "gradient_steps":c["epochs"],"initial_encoder_gradient_l2":initial_gradient,
            "initial_resistance_only_encoder_gradient_l2":initial_new_gradient,"native_base_weights_frozen":True,
            "native_context_features":len(self.context_features),"source_reserved_targets_not_fitted":125,
            "base_probability_floor":previous.FLOOR,"synthetic_rows":0,"artificial_history_views":0,
            "invented_source_times_or_sensor_joins":0}
        return self


def worker_initialize():
    global _RUNTIME
    inputs = load_inputs()
    _RUNTIME = inputs,fingerprint(inputs)


def compute_native_group(job):
    member,number,fit,val = job
    inputs,signature = _RUNTIME
    cache = previous.read_base_cache(inputs["previous_inputs"],member,number,fit,val)
    fitting,validation = inputs["train"].iloc[fit],inputs["train"].iloc[val]
    if set(fitting.group_key)&set(validation.group_key):
        raise ValueError("Outer native fitting/validation people overlap")
    completed = []
    for candidate in plan(inputs["previous_audit"])[4:]:
        if candidate["member"] != member:
            continue
        path = DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json"
        if path.exists():
            saved = json.loads(path.read_text())
            if saved["signature"] != signature or saved["candidate"] != candidate or saved["fit_row_keys"] != fitting.row_key.tolist() or saved["validation_row_keys"] != validation.row_key.tolist():
                raise ValueError("Frozen original-resistance fold changed")
            continue
        model = ResistanceHistoryBorg(candidate).fit(fitting,inputs["source"],inputs["specifications"][member],inputs["context_features"],cached=cache)
        predicted = model.predict(validation[model.input_features]).tolist()
        if not candidate["resistance_weight"] and candidate["correction_penalty"] == .1:
            old = next(r for r in inputs["previous"]["results"] if r["candidate"]["id"] == candidate["previous_candidate_id"])
            np.testing.assert_array_equal(predicted,np.asarray(old["oof_predictions"])[val])
            if model.loss_endpoints != old["folds"][number]["loss_endpoints"]:
                raise ValueError("Matched zero-new-source control did not reproduce the preceding actual losses")
        saved = {"signature":signature,"candidate":candidate,"fold_number":number,"fit_row_keys":fitting.row_key.tolist(),
            "validation_row_keys":validation.row_key.tolist(),"predicted":predicted,
            "training_summary":model.training_summary,"loss_endpoints":model.loss_endpoints}
        path.write_text(json.dumps(saved,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        completed.append(candidate["id"])
        print(f"Original resistance joint fold {candidate['id']} {number+1}/5 complete",flush=True)
    return {"member":member,"fold":number,"completed_new_recipes":completed}


def save(report):
    path = DIRECTORY/"selection.json"
    payload = json.dumps(report,indent=2,allow_nan=False)+"\n"
    path.with_suffix(".tmp").write_text(payload,encoding="utf-8")
    path.write_text(payload,encoding="utf-8")


def select():
    inputs = load_inputs()
    signature = fingerprint(inputs)
    train,test = inputs["train"],inputs["test"]
    candidates = plan(inputs["previous_audit"])
    DIRECTORY.mkdir(exist_ok=True)
    (DIRECTORY/"folds").mkdir(exist_ok=True)
    report = {**signature,"version":1,"status":"running","plan":candidates,"results":[],"target_accuracy":.8,
        "train_row_keys":train.row_key.tolist(),"evaluation_denominator":len(train),"test_denominator":len(test),
        "test_used_for_selection":False,"previous_benchmark_results_are_published":True,"minimum_cv_for_new_test_evaluation":.65,
        "actual_source_fitting_targets_available":1416,"actual_source_fitting_second_priors":1169,"reserved_source_targets_not_fitted":125,
        "native_base_caches_reused":10,"new_native_base_fits":0,"new_native_borg_targets":0,"synthetic_training_rows":0,
        "source_targets_pooled_across_instruments":False,
        "policy":"Fixed22recipes:4preceding real controls plus2frozen native bases x3correction penalties(.1/1/10) x3new resistance head weights(0/.1/1),80epochs. Reuse40verified bases and3inner-person logits per outer fold. Old550source histories plus native fitting rows alone fit normalization; original new866resistance targets use a fourth continuous-delta head,appended after old3heads initialization. Preserve550old source fitting targets,add866original manual resistance pairs with4people,keep125stored source targets reserved. Per-head person weights,separate original outcomes; zero new weight excludes all866new current labels and reproduces the old control at penalty.1. Fixed native context13features and21integer-delta residuals,AdamWlr.003decay.1. No generated examples,learned EMG labels,synthetic weights,jitter,SMOTE,invented clocks/phases/sensors,label pooling or changes to original487/179native cases."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k,v in signature.items()) or old["plan"] != candidates or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen original-resistance history study changed")
        report = old
    else:
        (DIRECTORY/"selection-source.py").write_bytes(Path(__file__).read_bytes())
        save(report)
    if report["status"] == "complete":
        return report
    folds = list(GroupKFold(n_splits=5).split(train,groups=train.group_key))
    jobs = [(member,number,fit,val) for member in ("core","cat") for number,(fit,val) in enumerate(folds)
        if any(not (DIRECTORY/"folds"/f"{c['id']}-fold-{number}.json").exists() for c in candidates[4:] if c["member"] == member)]
    if jobs:
        with ProcessPoolExecutor(max_workers=2,initializer=worker_initialize) as pool:
            for future in as_completed([pool.submit(compute_native_group,job) for job in jobs]):
                result = future.result()
                print(f"Original resistance group complete:{result['member']} fold{result['fold']+1}/5",flush=True)
    for candidate in candidates:
        if any(r["candidate"] == candidate for r in report["results"]):
            continue
        if candidate["algorithm"] == "previous_real_control":
            old = next(r for r in inputs["previous"]["results"] if r["candidate"]["id"] == candidate["parent_candidate_id"])
            predicted,details = np.asarray(old["oof_predictions"]),[]
        else:
            predicted,details = np.empty(len(train),dtype=object),[]
            for number,(_,val) in enumerate(folds):
                saved = json.loads((DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json").read_text())
                predicted[val] = saved["predicted"]
                details.append(saved)
        scores = [float(accuracy_score(train.iloc[val].label,predicted[val])) for _,val in folds]
        report["results"].append({"candidate":candidate,"accuracy_mean":float(np.mean(scores)),"fold_accuracy":scores,
            "pooled_oof_accuracy":float(accuracy_score(train.label,predicted)),"oof_predictions":predicted.tolist(),"folds":details})
        winner = max(report["results"],key=lambda r:r["accuracy_mean"])
        report.update(winner_id=winner["candidate"]["id"],best_cv_accuracy=winner["accuracy_mean"])
        save(report)
        print(f"Original resistance recipe {candidate['id']}:CV={np.mean(scores):.6f}",flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    import fatigue_resistance_history_joint as implementation
    implementation.select()
