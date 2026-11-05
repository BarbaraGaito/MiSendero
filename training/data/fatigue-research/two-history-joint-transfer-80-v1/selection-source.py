"""Joint backpropagation on actual public two-prior histories and native Borg.

Separate continuous source-delta heads share an encoder with a zero-initialized
native correction. Native bases and offsets use participant-disjoint fitting.
"""
from __future__ import annotations

import copy
import importlib.metadata
import json
import warnings
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
from torch import nn

import fatigue_emap_ordered_functions as predecessor
import fatigue_public_two_prior_histories_v2 as source
from fatigue_catboost import CatBoostBorg
from fatigue_dynamics_experiment import DynamicsClassifier
from fatigue_joint_transfer import JointResidualNetwork
from fatigue_probability import validate_calibration
from public_sources import digest

DIRECTORY = predecessor.DIRECTORY.parent/"two-history-joint-transfer-80-v1"
DOCS = predecessor.parent.source.DOCS
PARENT_AUDIT = DOCS/"emap-ordered-functions-verification.json"
INPUT_AUDIT = DOCS/"public-two-prior-history-v2-verification.json"
PROPOSAL = DOCS/"shared-two-prior-joint-proposal.md"
COMMON = [source.PRIOR,source.SECOND]
TARGETS = {"emap":"current_rpe","worker":"borg_native","sts":"borg_native"}
SOURCE_COUNTS = {"emap":248,"worker":253,"sts":49}
FLOOR = .0001
_RUNTIME = None


def plan(proof):
    controls = ["emap-order-000","emap-order-001"]+[proof["best_new_by_member"][m]["candidate"]["id"] for m in ("core","cat")]
    result = [{"id":f"two-history-joint-{i:03d}","algorithm":"previous_real_control","parent_candidate_id":key} for i,key in enumerate(controls)]
    for member in ("core","cat"):
        for weight in (0.,.1,1.):
            for epochs in (80,200):
                result.append({"id":f"two-history-joint-{len(result):03d}","algorithm":"joint_actual_two_history_residual",
                    "member":member,"auxiliary_weight":weight,"epochs":epochs,"base_probability_floor":FLOOR,
                    "learning_rate":.003,"weight_decay":.1,"correction_penalty":.1,"random_seed":42,
                    "source_target":"original_continuous_current_minus_actual_prior","native_target":"original_integer_delta_class"})
    return result


def load_inputs():
    old = predecessor.load_inputs()
    selection = json.loads((predecessor.DIRECTORY/"selection.json").read_text())
    proof = json.loads(PARENT_AUDIT.read_text())
    if (selection["status"] != "complete" or len(selection["results"]) != 10
        or proof["selection_sha256"] != digest(predecessor.DIRECTORY/"selection.json")
        or proof["verification_code_sha256"] != digest(Path(__file__).with_name("audit_fatigue_emap_ordered_functions.py"))
        or not proof["original_native_rows_and_targets_preserved"] or proof["actual_native_target_calls_observed"] != 20):
        raise ValueError("Preceding original-native history comparison is not independently complete")
    external,manifest = source.load()
    audit = json.loads(INPUT_AUDIT.read_text())
    if (audit["verification"] != "passed" or audit["audit_code_sha256"] != digest(Path(__file__).with_name("audit_public_two_prior_histories_v2.py"))
        or audit["source_preparation_code_sha256"] != digest(Path(source.__file__))
        or audit["source_provenance_sha256"] != digest(source.DIRECTORY/"provenance.json")
        or audit["fitting_observed_second_priors"] != 367 or not audit["all_original_source_columns_and_targets_preserved"]):
        raise ValueError("Direct original-cell two-prior source audit changed")
    fitting,reserved = external[external.source_partition.eq("fitting")].copy(),external[external.source_partition.eq("reserved")].copy()
    frame,train,test = old["frame"],old["train"],old["test"]
    if ((len(frame),len(train),len(test),len(fitting),len(reserved)) != (666,487,179,550,57)
        or fitting.groupby("source_domain").size().to_dict() != SOURCE_COUNTS
        or set(frame.group_key)&set(external.group_key) or set(train.group_key)&set(test.group_key)
        or set(fitting.group_key)&set(reserved.group_key)):
        raise ValueError("Original native/source cases or person reservations changed")
    specifications = copy.deepcopy(old["specifications"])
    specifications["core"]["params"].update(max_iter=5000,max_fun=100000,tol=.0001)
    if any(s["target_mode"] != "change_from_prior" for s in specifications.values()):
        raise ValueError("Native bases must preserve original delta-class supervision")
    context = list(specifications["core"]["features"])
    if len(context) != 13 or set(context)&{"label","row_key","group_key"}:
        raise ValueError("Compact genuine native context changed")
    return {"frame":frame,"train":train,"test":test,"source":fitting,"reserved_source":reserved,
        "source_manifest":manifest,"specifications":specifications,"context_features":context,
        "previous":selection,"previous_audit":proof,"previous_inputs":old}


def fingerprint(inputs):
    return {"code_sha256":digest(Path(__file__)),"previous_signature":predecessor.fingerprint(inputs["previous_inputs"]),
        "previous_selection_sha256":digest(predecessor.DIRECTORY/"selection.json"),"previous_verification_sha256":digest(PARENT_AUDIT),
        "source_provenance_sha256":digest(source.DIRECTORY/"provenance.json"),"source_input_verification_sha256":digest(INPUT_AUDIT),
        "proposal_sha256":digest(PROPOSAL),"source_dataset_sha256":inputs["source_manifest"]["dataset_sha256"],
        "native_specifications":inputs["specifications"],"native_context_features":inputs["context_features"],
        "public_real_data_policy_sha256":digest(DOCS/"public-real-data-policy.json"),
        "dependency_code_sha256":{name:digest(Path(__file__).with_name(name)) for name in (
            "fatigue_public_two_prior_histories_v2.py","fatigue_joint_transfer.py","fatigue_catboost.py","fatigue_dynamics_experiment.py","fatigue_probability.py")},
        "software_versions":{name:importlib.metadata.version(name) for name in ("torch","numpy","pandas","scikit-learn","catboost","joblib")},
        "worker_processes":2}


def history_query(frame):
    if set(COMMON)<=set(frame):
        return frame[COMMON].copy()
    return pd.DataFrame({source.PRIOR:frame.prior_borg.to_numpy(float),source.SECOND:frame.prior2_borg.to_numpy(float)},index=frame.index)


class NativeBase:
    def __init__(self,member,specification):
        self.member,self.specification = member,copy.deepcopy(specification)

    def fit(self,frame):
        kind = DynamicsClassifier if self.member == "core" else CatBoostBorg
        with warnings.catch_warnings(record=True) as captured,threadpool_limits(limits=1):
            warnings.simplefilter("always",ConvergenceWarning)
            self.classifier = kind(self.specification).fit(frame)
        known = self.classifier.model.classes_.astype(int)+10
        if not np.isin(known,np.arange(21)).all() or len(set(known)) != len(known):
            raise ValueError("Original native base changed its delta-class scale")
        self.class_indices = known
        self.priority = np.asarray(known.tolist()+[i for i in range(21) if i not in known],int)
        self.input_features = list(self.specification["features"])
        self.fitting_summary = {"actual_native_rows":len(frame),"actual_native_people":frame.group_key.nunique(),
            "native_feature_count":len(self.input_features),"synthetic_rows":0,"artificial_history_views":0,
            "convergence_warnings":[str(w.message) for w in captured if issubclass(w.category,ConvergenceWarning)]}
        return self

    def logits(self,frame):
        validate_calibration(frame)
        with threadpool_limits(limits=1):
            probabilities = self.classifier.model.predict_proba(frame[self.input_features])
        values = np.full((len(frame),21),FLOOR,float)
        values[:,self.class_indices] = np.maximum(probabilities,FLOOR)
        values /= values.sum(axis=1,keepdims=True)
        return torch.tensor(np.log(values),dtype=torch.float64)

    def predict(self,frame):
        return self.classifier.predict(frame)


def predictions(logits,priority,frame):
    order = torch.as_tensor(priority,dtype=torch.long)
    delta = order[logits[:,order].argmax(dim=1)].numpy()-10
    values = np.clip(delta+frame.prior_borg.to_numpy(int),0,10)
    return np.asarray([f"Borg {int(value)}" for value in values])


def prepare_base(frame,member,specification):
    logits = torch.empty((len(frame),21),dtype=torch.float64)
    models,evidence = [],[]
    for number,(fit,val) in enumerate(GroupKFold(n_splits=3).split(frame,groups=frame.group_key)):
        fitting,validation = frame.iloc[fit],frame.iloc[val]
        if set(fitting.group_key)&set(validation.group_key):
            raise ValueError("Inner native fitting/validation people overlap")
        model = NativeBase(member,specification).fit(fitting)
        logits[val] = model.logits(validation)
        np.testing.assert_array_equal(predictions(logits[val],model.priority,validation),model.predict(validation))
        models.append(model)
        evidence.append({"number":number,"fit_row_keys":fitting.row_key.tolist(),"validation_row_keys":validation.row_key.tolist(),
            "fitting_summary":model.fitting_summary})
    base = NativeBase(member,specification).fit(frame)
    np.testing.assert_array_equal(predictions(base.logits(frame),base.priority,frame),base.predict(frame))
    return {"base":base,"inner_models":models,"inner_folds":evidence,"fit_logits":logits,"fit_row_keys":frame.row_key.tolist()}


class HistoryNetwork(JointResidualNetwork):
    def source_prediction(self,history,domain):
        return self.source_heads[domain](self.encoder(history)).squeeze(1)


class JointHistoryBorg:
    def __init__(self,candidate):
        self.candidate = candidate

    def history_transform(self,frame):
        return torch.tensor(self.history_scaler.transform(self.history_imputer.transform(history_query(frame))),dtype=torch.float32)

    def context_transform(self,frame):
        return torch.tensor(self.context_scaler.transform(self.context_imputer.transform(frame[self.context_features])),dtype=torch.float32)

    def fit(self,frame,external,specification,context_features,cached=None,observer=None,batch_observer=None):
        validate_calibration(frame)
        if (len(external) != 550 or external.groupby("source_domain").size().to_dict() != SOURCE_COUNTS
            or not external.source_partition.eq("fitting").all() or set(frame.group_key)&set(external.group_key)):
            raise ValueError("Only the550original fitting source targets and distinct native people may fit this joint model")
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        c = self.candidate
        cached = prepare_base(frame,c["member"],specification) if cached is None else cached
        if cached["fit_row_keys"] != frame.row_key.tolist() or cached["base"].member != c["member"]:
            raise ValueError("Native base cache belongs to other actual fitting cases or classifier")
        self.base = cached["base"]
        self.context_features = list(context_features)
        self.input_features = list(dict.fromkeys(self.base.input_features+self.context_features))
        before = joblib.hash(self.base)
        torch.manual_seed(c["random_seed"])
        union = pd.concat([history_query(frame),history_query(external)],ignore_index=True)
        self.history_imputer = SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True)
        self.history_scaler = StandardScaler().fit(self.history_imputer.fit_transform(union))
        self.context_imputer = SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True)
        self.context_scaler = StandardScaler().fit(self.context_imputer.fit_transform(frame[self.context_features]))
        history,context,offsets = self.history_transform(frame),self.context_transform(frame),cached["fit_logits"].detach()
        current,prior = frame.label.str.removeprefix("Borg ").to_numpy(int),frame.prior_borg.to_numpy(int)
        target = torch.as_tensor(current-prior+10,dtype=torch.long)
        self.domains = sorted(SOURCE_COUNTS)
        self.network = HistoryNetwork(history.shape[1],context.shape[1],self.domains)
        with torch.no_grad():
            if torch.count_nonzero(self.network.correction(history,context,offsets)):
                raise ValueError("Initial native correction must be zero")
        auxiliary = {}
        if c["auxiliary_weight"] > 0:
            for domain in self.domains:
                part = external[external.source_domain.eq(domain)]
                actual,old = part[TARGETS[domain]].to_numpy(float),part[source.PRIOR].to_numpy(float)
                if not np.isfinite([actual,old]).all() or np.any((actual<0)|(actual>10)|(old<0)|(old>10)):
                    raise ValueError("Only original continuous current/prior CR10 values can supervise a source head")
                weights = 1./part.groupby("group_key").group_key.transform("size").to_numpy()
                weights *= len(part)/weights.sum()
                auxiliary[domain] = self.history_transform(part),torch.as_tensor(actual-old,dtype=torch.float32),torch.as_tensor(weights,dtype=torch.float32)
                if observer is not None:
                    observer("source",domain,part[COMMON].copy(),actual.copy(),old.copy())
        else:
            self.network.source_heads.requires_grad_(False)
        if observer is not None:
            observer("native","native",frame[self.input_features].copy(),current.copy(),prior.copy())
        optimizer = torch.optim.AdamW(self.network.parameters(),lr=c["learning_rate"],weight_decay=c["weight_decay"])
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=c["epochs"],eta_min=.0003)
        self.loss_endpoints = []
        initial_encoder_gradient = None
        for epoch in range(c["epochs"]):
            optimizer.zero_grad(set_to_none=True)
            correction = self.network.correction(history,context,offsets)
            classification = nn.functional.cross_entropy(offsets+correction,target)
            losses = {domain:(nn.functional.smooth_l1_loss(self.network.source_prediction(x,domain),y,beta=1.,reduction="none")*w).sum()/w.sum()
                for domain,(x,y,w) in auxiliary.items()}
            source_loss = torch.stack(list(losses.values())).mean() if losses else torch.tensor(0.)
            total = classification+c["auxiliary_weight"]*source_loss+c["correction_penalty"]*correction.square().mean()
            if not torch.isfinite(total):
                raise ValueError("Nonfinite two-history joint loss")
            if batch_observer is not None:
                batch_observer(epoch,history.detach().numpy().copy(),target.numpy().copy(),
                    {domain:(x.numpy().copy(),y.numpy().copy(),w.numpy().copy()) for domain,(x,y,w) in auxiliary.items()})
            total.backward()
            if any(p.grad is not None and not torch.isfinite(p.grad).all() for p in self.network.parameters()):
                raise ValueError("Nonfinite actual two-history joint gradient")
            if epoch == 0:
                initial_encoder_gradient = float(torch.sqrt(sum(p.grad.square().sum() for p in self.network.encoder.parameters() if p.grad is not None)))
                if c["auxiliary_weight"] > 0 and not initial_encoder_gradient > 0:
                    raise ValueError("Actual source supervision did not reach the shared encoder")
            nn.utils.clip_grad_norm_(self.network.parameters(),5.)
            optimizer.step()
            scheduler.step()
            if epoch in (0,c["epochs"]-1):
                self.loss_endpoints.append({"epoch":epoch,"total":float(total.detach()),"native_classification":float(classification.detach()),
                    "source_delta_mean":float(source_loss.detach()),"source_losses":{d:float(v.detach()) for d,v in losses.items()}})
        self.network.requires_grad_(False).eval()
        for p in self.network.parameters():
            p.grad = None
        if joblib.hash(self.base) != before:
            raise ValueError("Joint backpropagation changed the frozen native base")
        self.training_summary = {"actual_native_targets":len(frame),"source_input_rows_for_shared_preprocessing":550,
            "actual_source_targets_in_objective":550 if auxiliary else 0,"source_targets_by_separate_head":SOURCE_COUNTS if auxiliary else {},
            "source_fitting_actual_second_priors":367,"native_actual_second_priors":int(frame.prior2_borg.notna().sum()),
            "gradient_steps":c["epochs"],"initial_encoder_gradient_l2":initial_encoder_gradient,"native_base_weights_frozen":True,
            "native_context_features":len(self.context_features),"source_reserved_targets_not_fitted":57,
            "base_probability_floor":FLOOR,"synthetic_rows":0,"artificial_history_views":0,"invented_source_times_or_sensor_joins":0}
        return self

    def predict(self,frame):
        validate_calibration(frame)
        with torch.no_grad():
            offsets = self.base.logits(frame)
            logits = offsets+self.network.correction(self.history_transform(frame),self.context_transform(frame),offsets)
        if not torch.isfinite(logits).all():
            raise ValueError("Nonfinite corrected native logits")
        return predictions(logits,self.base.priority,frame)


def read_base_cache(inputs,member,number,fit,val,create=False):
    signature = fingerprint(inputs)
    train = inputs["train"]
    path = DIRECTORY/"bases"/f"{member}-fold-{number}.joblib"
    metadata_path = path.with_suffix(".json")
    identity = {"signature":signature,"member":member,"fold":number,"fit_row_keys":train.iloc[fit].row_key.tolist(),
        "validation_row_keys":train.iloc[val].row_key.tolist()}
    if metadata_path.exists():
        meta = json.loads(metadata_path.read_text())
        if any(meta.get(k) != v for k,v in identity.items()) or meta["cache_sha256"] != digest(path):
            raise ValueError("Frozen inner-person native base cache changed")
        return joblib.load(path)
    if not create:
        raise ValueError("Required precomputed native base cache is absent")
    cache = prepare_base(train.iloc[fit],member,inputs["specifications"][member])
    joblib.dump(cache,path)
    meta = {**identity,"cache_sha256":digest(path),"inner_folds":cache["inner_folds"],"full_base_fitting_summary":cache["base"].fitting_summary,
        "actual_original_native_base_fits":4,"native_base_target_mode":"change_from_prior","synthetic_rows":0}
    metadata_path.write_text(json.dumps(meta,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return cache


def worker_initialize():
    global _RUNTIME
    inputs = load_inputs()
    _RUNTIME = inputs,fingerprint(inputs)


def compute_native_group(job):
    member,number,fit,val = job
    inputs,signature = _RUNTIME
    cache = read_base_cache(inputs,member,number,fit,val,create=True)
    fitting,validation = inputs["train"].iloc[fit],inputs["train"].iloc[val]
    if set(fitting.group_key)&set(validation.group_key):
        raise ValueError("Outer native fitting/validation people overlap")
    print(f"Joint actual-history native base ready:{member} fold{number+1}/5",flush=True)
    results = []
    for candidate in plan(inputs["previous_audit"])[4:]:
        if candidate["member"] != member:
            continue
        path = DIRECTORY/"folds"/f"{candidate['id']}-fold-{number}.json"
        if path.exists():
            saved = json.loads(path.read_text())
            if saved["signature"] != signature or saved["candidate"] != candidate or saved["fit_row_keys"] != fitting.row_key.tolist() or saved["validation_row_keys"] != validation.row_key.tolist():
                raise ValueError("Frozen joint-history native fold changed")
            continue
        model = JointHistoryBorg(candidate).fit(fitting,inputs["source"],inputs["specifications"][member],inputs["context_features"],cached=cache)
        saved = {"signature":signature,"candidate":candidate,"fold_number":number,"fit_row_keys":fitting.row_key.tolist(),
            "validation_row_keys":validation.row_key.tolist(),"predicted":model.predict(validation).tolist(),
            "training_summary":model.training_summary,"loss_endpoints":model.loss_endpoints}
        path.write_text(json.dumps(saved,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        results.append(candidate["id"])
        print(f"Joint actual-history native fold {candidate['id']} {number+1}/5 complete",flush=True)
    return {"member":member,"fold":number,"completed_new_recipes":results}


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
    for name in ("bases","folds"):
        (DIRECTORY/name).mkdir(exist_ok=True)
    report = {**signature,"version":1,"status":"running","plan":candidates,"results":[],"target_accuracy":.8,
        "train_row_keys":train.row_key.tolist(),"evaluation_denominator":len(train),"test_denominator":len(test),
        "test_used_for_selection":False,"previous_benchmark_results_are_published":True,"minimum_cv_for_new_test_evaluation":.65,
        "actual_source_fitting_targets_available":550,"actual_source_fitting_second_priors":367,"reserved_source_targets_not_fitted":57,
        "new_native_borg_targets":0,"synthetic_training_rows":0,"source_targets_pooled_across_instruments":False,
        "policy":"Fixed16recipes:4preceding real controls plus2native bases x3source loss weights(0/.1/1) x2epochs(80/200). NativeMLP16/8alpha10max5000 or original Cat900depth3L2=30,with3inner native-person folds and frozen native base. Shared real prior/second-prior histories from original native fitting cases and550actual source cases,367source second priors measured. Separate EMAP/Worker/STS continuous original-delta heads; per-person source weights. Zero source weight excludes all source labels from the training objective with otherwise matched architecture/preprocessing. Native context13features and21integer-delta residual logits initializedzero;probability floor.0001 preserves initial base decisions. Full-batch AdamW,real rows only; shared preprocessing fits native/source fitting cases,context fits native fitting only. No reserved source/native labels, invented clocks/phases/sensors, generated examples or changed native487/179cases."}
    path = DIRECTORY/"selection.json"
    if path.exists():
        old = json.loads(path.read_text())
        if any(old.get(k) != v for k,v in signature.items()) or old["plan"] != candidates or old["train_row_keys"] != train.row_key.tolist():
            raise ValueError("Frozen joint actual-history study changed")
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
                print(f"Joint native group complete:{result['member']} fold{result['fold']+1}/5",flush=True)
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
        print(f"Joint actual-history recipe {candidate['id']}:CV={np.mean(scores):.6f}",flush=True)
    report["status"] = "complete"
    save(report)
    return report


if __name__ == "__main__":
    # Persist importable class identities in worker caches and saved models.
    import fatigue_two_history_joint as implementation
    implementation.select()
