"""Freeze a bounded CatBoost step-size/tree-budget comparison before fitting."""
import json
from pathlib import Path

import fatigue_catboost_schedule as study
from public_sources import digest

assert len(study.plan()) == 16 and tuple(study.RATES) == (.01,.03,.09)
assert tuple(study.PREFIXES) == (300,900,1800,2700)
old_directory = study.DIRECTORY.parent/"catboost-80-v1"
old = json.loads((old_directory/"selection.json").read_text())
baseline = next(r for r in old["results"] if r["candidate"]["id"] == "catboost-023")
short = next(r for r in old["results"] if r["candidate"]["id"] == "catboost-021")
assert baseline["candidate"]["features"] == short["candidate"]["features"] == list(study.FEATURES)
assert baseline["accuracy_mean"] == .6379721574248428
report = {"version":1,"implementation_code_sha256":digest(Path(study.__file__)),"plan":study.plan(),
    "learning_rates":list(study.RATES),"tree_prefixes":list(study.PREFIXES),"depth":3,"l2_leaf_reg":30.,
    "original_feature_count":29,"original_features":list(study.FEATURES),"original_training_cases":487,"original_test_cases":179,
    "original_native_person_folds":5,"new_unique_schedules":10,"fresh_historical_controls":2,"inherited_controls":4,
    "maximum_tree_trajectory_fits":15,"native_prefix_evaluations":60,
    "minimum_cv_for_new_test_evaluation":.65,"test_used_for_selection":False,"synthetic_rows":0,
    "early_stopping_with_validation_or_test":False,"source_target_conversion_or_pooling":False,
    "original_catboost_code_sha256":digest(Path(study.__file__).with_name("fatigue_catboost.py")),
    "original_catboost_selection_sha256":digest(old_directory/"selection.json"),
    "public_real_data_policy_sha256":digest(study.DOCS/"public-real-data-policy.json"),
    "original_catboost_900_tree_cv":baseline["accuracy_mean"],"original_catboost_300_tree_cv":short["accuracy_mean"],
    "official_parameter_tuning":"https://catboost.ai/docs/en/concepts/parameter-tuning",
    "official_prefix_prediction":"https://catboost.ai/docs/en/concepts/python-reference_catboostclassifier_predict",
    "rationale":"All earlier native CatBoost recipes fixed learning_rate at.03. For depth3/L2=30,300to900trees improved fitting-person CVfrom.617914to.637972;for L2=3the same budget change worsened it. Compare fixed rates.01/.03/.09with300/900/1800/2700trees,holding all other original parameters and29features constant. The.01/2700,.03/900,.09/300triplet has equal rate-times-tree product27to examine step size versus total boosting budget. Train each rate/fold once to2700with no evalset or overfitting detector; evaluate only the four predeclared prefixes. Require.03/300and.03/900prefix predictions to reproduce old original-person OOFcontrols before accepting selection. Source representations and reserved labels are not used to tune these schedules. Preserve all487native fitting cases and179original test cases; only a sole frozenCVwinner above.65may open a new native test."}
if study.PROPOSAL.exists():
    assert json.loads(study.PROPOSAL.read_text()) == report,"Preserve the frozen schedule declaration"
else:
    assert not (study.DIRECTORY/"selection.json").exists(),"Cannot declare after schedule selection started"
    study.PROPOSAL.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
print(json.dumps({"frozen_plan":16,"new_unique_schedules":10,"maximum_tree_trajectory_fits":15,"native_prefix_evaluations":60,
    "model_fitting_started":False}),flush=True)
