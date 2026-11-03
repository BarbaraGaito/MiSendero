"""Freeze a bounded source-state/direct-delta comparison before fitting."""
import json
from pathlib import Path

import fatigue_furukawa_hr_transfer as study
from public_sources import digest

report = {"version":1,"implementation_code_sha256":digest(Path(study.__file__)),"plan":study.plan(),
    "source_state_targets":252,"source_delta_targets":168,"source_fitting_people":12,"source_reserved_responses":84,"source_reserved_people":4,
    "original_native_fit_cases":487,"original_native_test_cases":179,"original_native_person_folds":5,"new_native_fits":50,
    "source_algorithms":{"ridge":{"alpha":10.},"svr":{"C":10.,"gamma":"scale","epsilon":.1}},
    "source_source_person_mass_equal":True,"source_input_audit_sha256":digest(study.INPUT_AUDIT),
    "preceding_verification_sha256":digest(study.PARENT_AUDIT),"minimum_cv_for_new_test_evaluation":.65,
    "test_used_for_selection":False,"synthetic_rows":0,"native_target_scale_changed":False,
    "rationale":"Fitting-only inspection found currentHR/current original-point correlation.3807versus paired HRchange/RPEchange.0692. Compare actual252response state functions against168real within-condition delta functions,not an epoch repeat. All source intervals equal2min,so do not claim learned interval dependence. SourceHR102.6-145.83bpmversus native49-184; computed scores can extrapolate. Measured native controls include both rawHRand their difference,same original native features/labels. Sourcepointoutputs remain separate representations,never native targets. No assumed rest,individualage,cross-condition ordering or cross-experiment person joins."}
if study.PROPOSAL.exists():
    old = json.loads(study.PROPOSAL.read_text())
    if old != report:
        archive = study.DOCS/"furukawa-hr-transfer-plan-preflight-v1.json"
        snapshot = study.DOCS/"furukawa-hr-transfer-model-preflight-v1.py"
        assert not (study.DIRECTORY/"selection.json").exists() and json.loads(archive.read_text()) == old
        assert old["implementation_code_sha256"] == digest(snapshot) and old["plan"] == report["plan"]
        study.PROPOSAL.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
else:
    study.PROPOSAL.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
print(json.dumps({"frozen_plan":len(report["plan"]),"new_native_fits":50,"source_targets_state_delta":[252,168],"model_fitting_started":False}),flush=True)
