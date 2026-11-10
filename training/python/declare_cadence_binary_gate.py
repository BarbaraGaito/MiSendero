"""Freeze the distinct physiology/history source binary task before fitting."""
import json
from pathlib import Path
import fatigue_cadence_binary_gate as study
from public_sources import digest

audit = json.loads(study.INPUT_AUDIT.read_text())
assert audit['verification']=='passed' and audit['source_fitting_pairs']==851
report = {'version':1,'implementation_code_sha256':digest(Path(study.__file__)),'plan':study.plan(),
    'input_verification_sha256':digest(study.INPUT_AUDIT),'previous_verification_sha256':digest(study.PARENT_AUDIT),
    'source_fitting_actual_pairs':851,'source_reserved_pairs':206,'source_actual_second_priors':727,
    'original_native_fit_cases':487,'original_native_test_cases':179,'new_joint_network_fits':20,'new_native_base_fits':0,
    'minimum_cv_for_new_test_evaluation':.65,'test_used_for_selection':False,'synthetic_rows':0,
    'independent_refit_policy':'All4new recipes in all5native personfolds,all20fold artifacts and6OOFmetrics.',
    'rationale':'Previous binary auxiliary histories and penalty tuning did not beat the native control. '
        'Test actual prior physiological state alongside actual first/second reports in a shared encoder. '
        'Six numerical inputs(prior2plus4HRsummaries) use separate fitting-only native/source normalization '
        'and five actual missing-value indicators. The source851pairs preserve original6-20outcomes in '
        'their own change predicate/head;native exact delta ratios/base weights remain frozen. Source '
        'physiology comes from the completed prior bout. Native prior HR/baseline have verified earlier '
        'clocks;different rest definitions remain explicit. No measured response ages,current-bout HR, '
        'source native-context rows or target-scale equivalence are fabricated. Fixed80epochs,penalty1 '
        '(best lower penalty in previous CV),source0/.1and optimizer.003/decay.1. Matched source-zero '
        'controls isolate auxiliary supervision from new measured inputs. Keep all original487/179cases.'}
if study.PROPOSAL.exists():
    assert json.loads(study.PROPOSAL.read_text())==report
else:
    assert not (study.DIRECTORY/'selection.json').exists()
    study.PROPOSAL.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'frozen_recipes':6,'new_joint_network_fits':20,'source_fitting_actual_pairs':851,
    'predictive_fitting_started':False}),flush=True)
