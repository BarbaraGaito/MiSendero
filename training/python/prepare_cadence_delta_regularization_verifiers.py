"""Preserve independent full-delta verification for stronger penalties."""
import json
from pathlib import Path
from public_sources import ROOT,digest

root = Path(__file__).parent
outputs,sources = {},{}
for kind in ('audit','evaluate','test'):
    old = root/f'{kind}_fatigue_cadence_full_delta.py'
    sources[old.name] = digest(old)
    text = (old.read_text().replace('fatigue_cadence_full_delta','fatigue_cadence_delta_regularization')
        .replace('cadence-full-delta','cadence-delta-regularization')
        .replace('cadence_full_delta_residual','cadence_delta_regularization'))
    text = text.replace('Independent full native-delta audit','Independent stronger delta-penalty audit')
    name = f'{kind}_fatigue_cadence_delta_regularization.py'
    compile(text,name,'exec')
    path = root/name
    if path.exists():
        assert path.read_text()==text
    else:
        path.write_text(text,encoding='utf-8')
    outputs[name] = digest(path)
old = root/'diagnose_cadence_full_delta_generalization.py'
sources[old.name] = digest(old)
text = (old.read_text().replace('fatigue_cadence_full_delta','fatigue_cadence_delta_regularization')
    .replace('cadence-full-delta','cadence-delta-regularization')
    .replace("f'cadence-delta-regularization-{","f'delta-regularization-{")
    .replace('previous_scalar_source','previous_penalty1_source')
    .replace('penalty1_outperformed_point1','penalty100_outperformed10')
    .replace("pair[1.]['exact_native_cv_accuracy']>pair[.1]['exact_native_cv_accuracy']",
        "pair[100.]['exact_native_cv_accuracy']>pair[10.]['exact_native_cv_accuracy']"))
text = text.replace('All8new recipes had the full21class native objective.',
    'All8new recipes kept the frozen full21class native objective and changed only penalty10/100.')
name = 'diagnose_cadence_delta_regularization_generalization.py'
compile(text,name,'exec')
path = root/name
if path.exists():
    assert path.read_text()==text
else:
    path.write_text(text,encoding='utf-8')
outputs[name] = digest(path)
report = {'preparation':'passed','preparation_code_sha256':digest(Path(__file__)),
    'frozen_sources_sha256':sources,'derived_files_sha256':outputs,'historical_sources_modified':False,
    'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,
    'changes':'Same independent21class NLL/gradient,source BCE/gradient,80actual backward steps and frozen bases. All14OOFrecipes/40fold artifacts and40independent network refits. Six real-public-data tests;fitting-only10/100generalization diagnostic. Original179qualified-test path preserved.'}
(ROOT/'docs/fatigue-80-2026-10-25/cadence-delta-regularization-verifier-preparation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report),flush=True)
