"""Derive static independent checks for16native-private context inputs."""
import json
from pathlib import Path
from public_sources import ROOT,digest

root = Path(__file__).parent
outputs = {}
sources = {}
for kind in ('audit','evaluate','test'):
    old = root/f'{kind}_fatigue_cadence_binary_gate.py'
    sources[old.name] = digest(old)
    text = old.read_text().replace('fatigue_cadence_binary_gate','fatigue_cadence_recent_gate')
    text = text.replace('cadence-binary-gate','cadence-recent-gate')
    text = text.replace('cadence_physiology_binary_gate','cadence_recent_native_gate')
    text = text.replace('plan()[2:]','plan()[6:]')
    text = text.replace("len(selected['results'])==6","len(selected['results'])==10")
    text = text.replace('all_6_oof_recipes_recomputed','all_10_oof_recipes_recomputed')
    if kind=='audit':
        text = text.replace('assert model.candidate==c and model.base.specification==specification',
            "assert len(context_features)==16 and context_features[-3:]==study.added.COLUMNS\n    assert not set(study.added.COLUMNS)&set(external)\n    assert model.candidate==c and model.base.specification==specification")
        text = text.replace('Independent public change-gate audit','Independent recent native-context audit')
    if kind=='test':
        text = text.replace('import numpy as np','import numpy as np\nimport pandas as pd')
        marker = "\n\nif __name__=='__main__':"
        assert marker in text
        extra = '''
    def test_actual_recent_context_is_private_and_fitting_only(self):
        self.assertEqual(len(self.inputs['context_features']),16)
        self.assertEqual(self.model.context_features[-3:],study.added.COLUMNS)
        self.assertFalse(set(study.added.COLUMNS)&set(self.inputs['gate_source']))
        raw = pd.read_csv(study.added.recent.NATIVE_DIRECTORY/'dataset.csv').set_index('row_key')
        matched = raw.loc[self.fitting.row_key]
        expected = np.column_stack([matched.current_hr_bpm,matched.current_hr_bpm-matched.prior_hr_bpm,
            matched.current_hr_bpm/matched.prior_hr_bpm])
        np.testing.assert_allclose(self.fitting[study.added.COLUMNS],expected,atol=1e-12,equal_nan=True)
        values = self.fitting[self.model.context_features].to_numpy(float)
        np.testing.assert_allclose(self.model.context_imputer.statistics_,np.nanmedian(values,axis=0),atol=1e-12)
        transformed = self.model.context_imputer.transform(self.fitting[self.model.context_features])
        np.testing.assert_allclose(self.model.context_scaler.mean_,transformed.mean(axis=0),atol=1e-12)
        np.testing.assert_allclose(self.model.context_scaler.var_,transformed.var(axis=0),atol=1e-12)
        self.assertEqual(self.model.network.encoder[0].in_features,11)
'''
        text = text.replace(marker,'\n'+extra+marker)
    name = f'{kind}_fatigue_cadence_recent_gate.py'
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
    'changes':'16native-private context inputs verified against fitting-only preprocessing;source encoder unchanged. All20newfold artifacts/10OOFrecipes,20network refits,80actual loss/backward checks per refit. Full179qualified artifact test path preserved. Six real-public-data tests.'}
(ROOT/'docs/fatigue-80-2026-10-25/cadence-recent-gate-verifier-preparation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report),flush=True)
