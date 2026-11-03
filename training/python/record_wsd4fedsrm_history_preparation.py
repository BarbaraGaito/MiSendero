"""Record verified original reports and prepared real histories, without fits."""
import json
from pathlib import Path

import wsd4fedsrm_history_inputs as source
from public_sources import digest

proof = json.loads(source.AUDIT.read_text())
manifest_path = source.DIRECTORY/'provenance.json'
manifest = json.loads(manifest_path.read_text())
assert proof['verification'] == 'passed' and proof['original_timed_cells_independently_checked'] == 1311
assert proof['verification_code_sha256'] == digest(Path(__file__).with_name('audit_wsd4fedsrm_timed_reports.py'))
assert manifest['input_audit_sha256'] == digest(source.AUDIT)
assert manifest['preparation_code_sha256'] == digest(Path(source.__file__))
assert manifest['dataset_sha256'] == digest(source.DIRECTORY/'dataset.csv')
assert manifest['fitting_pairs'] == 920 and manifest['reserved_pairs'] == 187
assert manifest['fitting_actual_second_priors'] == 758 and not manifest['model_fitting_started']
path = source.DOCS/'current-research-status.json'
status = json.loads(path.read_text())
assert status['goal_status'] == 'active' and status['original_training_cases'] == 487 and status['original_test_cases'] == 179
status['additional_data_audits'][source.AUDIT.name] = digest(source.AUDIT)
status['wsd4fedsrm_history_preparation'] = {'source_directory':source.DIRECTORY.name,
    'original_report_verification':source.AUDIT.name,'original_report_verification_sha256':digest(source.AUDIT),
    'provenance_sha256':digest(manifest_path),'dataset_sha256':manifest['dataset_sha256'],
    'fitting_pairs':920,'reserved_pairs':187,'fitting_people':27,'reserved_people':7,
    'fitting_actual_second_priors':758,'reserved_actual_second_priors':146,
    'adapter_prepared':True,'independent_adapter_verification_completed':False,
    'model_fitting_started':False,'native_target_merge':False,'synthetic_rows':0}
status['next_evidence_based_direction'] = (
    'Complete the live study49independent audit before marking its16recipe comparison complete. '
    'The completed fitting-only diagnostic shows.03/900CV.637972versus.03/2700CV.603321despite fittingaccuracy rising.690934to.740121;do not repeat this grid. '
    'New WSDoriginal timed reports independently verified:1311cells/34people,with27people fixed for sourcefitting before pair eligibility and7reserved. '
    'Prepared1107actual within-task pairs:920fitting/187reserved,758fitting targets with two actual timed priors. '
    'Next independently verify the prepared adapter against original CSVcells and clocks before a bounded separate-output transfer study. '
    'Preserve original487/179native cases and.65CVtest gate. No terminal/before-taskclock assumptions,sensor joins,source-native label conversion or synthetic histories.80percent requires144of179from a frozen reloaded artifact;retained108.')
for field in ('additional_scoped_verifications','additional_data_audits','additional_public_candidate_inspections'):
    assert all(digest(source.DOCS/name) == expected for name,expected in status[field].items())
path.write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'original_report_audit':'passed','prepared_actual_pairs':1107,'fitting':920,'reserved':187,
    'independent_adapter_verification_pending':True,'model_fitting_started':False,'goal_achieved':False}))
