"""Preserve source-access/clock evidence and fitting-only causal-memory coverage."""
import hashlib
import json
from pathlib import Path
from public_sources import digest,ROOT

DOCS = ROOT/'docs/fatigue-80-2026-10-25'
RAW = ROOT/'training/data/raw/fatigue-research/bbex-dryad-fbg79cp45-v1'
clock_path = DOCS/'wsd4fedsrm-ppg-clock-inspection.json'
clock = json.loads(clock_path.read_text())
assert clock['inspection']=='complete' and clock['source_fitting_ppg_files']==162 and clock['source_fitting_people']==27
assert clock['inspection_code_sha256']==digest(Path(__file__).with_name('inspect_wsd4fedsrm_ppg_clocks.py'))
assert clock['reserved_person_signals_read']==0 and not clock['ppg_to_report_temporal_join_verified']
metadata_paths = [RAW/name for name in ('dataset-metadata.json','version-metadata.json','file-metadata.json')]
dataset,version,files = [json.loads(path.read_text()) for path in metadata_paths]
assert dataset['identifier']=='doi:10.5061/dryad.fbg79cp45' and dataset['license']=='https://spdx.org/licenses/CC0-1.0.html'
entries = files['_embedded']['stash:files']
assert len(entries)==7 and sum(row['path'].endswith('.zip') for row in entries)==6
api_log,public_log = DOCS/'bbex-archive-index-inspection.log',DOCS/'bbex-public-archive-index-inspection.log'
assert 'HTTP Error 401' in api_log.read_text(errors='replace') and 'HTTP Error 403' in public_log.read_text(errors='replace')
bbex = {'inspection':'metadata_verified_data_download_unavailable','record':'https://doi.org/10.5061/dryad.fbg79cp45',
    'recording_code_sha256':digest(Path(__file__)),'public_license':dataset['license'],
    'official_metadata_sha256':{path.name:digest(path) for path in metadata_paths},
    'official_archive_count':6,'official_archive_total_bytes':sum(row['size'] for row in entries if row['path'].endswith('.zip')),
    'official_files':[{key:row[key] for key in ('path','size','digest','digestType')} for row in entries],
    'api_download_http_status':401,'public_link_download_http_status':403,
    'api_attempt_log_sha256':digest(api_log),'public_attempt_log_sha256':digest(public_log),
    'original_bundles_downloaded':0,'original_workbook_cells_verified':0,'model_fitting_started':False,
    'decision':'Official public metadata/CC0license verified. Both documented API and public-site download attempts were denied; no credentials or access-control bypass attempted. Do not treat workbook cells as available or train from website summaries. Do not repeat unchanged download retries.'}
bbex_path = DOCS/'bbex-public-access-inspection.json'
bbex_path.write_text(json.dumps(bbex,indent=2)+'\n',encoding='utf-8')
coverage_path = DOCS/'causal-native-memory-coverage.json'
coverage = json.loads(coverage_path.read_text())
assert coverage['diagnostic']=='passed' and coverage['original_fitting_rows']==487 and coverage['original_fitting_people']==28
assert coverage['diagnostic_code_sha256']==digest(Path(__file__).with_name('diagnose_causal_native_memory_coverage.py'))
assert coverage['predictive_estimator_fits']==coverage['native_test_predictions_computed']==0
assert coverage['scope_coverage']['session']['queries_with_any_earlier_eligible_report']==455
status_path = DOCS/'current-research-status.json'
status = json.loads(status_path.read_text())
assert status['completed_studies']==51 and status['goal_status']=='active'
for path in (clock_path,bbex_path):
    status['additional_public_candidate_inspections'][path.name] = digest(path)
status['wsd4fedsrm_ppg_clock_review'] = {'document':clock_path.name,'sha256':digest(clock_path),
    'source_fitting_ppg_files':162,'reserved_person_signals_read':0,'sensor_report_join_verified':False,'model_fitting_started':False}
status['other_new_public_candidates']['bbex'] = {'public_record':bbex['record'],'license':bbex['public_license'],
    'metadata_verified':True,'access_inspection':bbex_path.name,'original_bundles_downloaded':0,
    'status':'API401/public-link403;originalworkbooksnotavailable;no fitting,no unchanged download retry',
    'model_fitting_started':False}
status['causal_native_memory_coverage'] = {'document':coverage_path.name,'sha256':digest(coverage_path),
    'fitting_only':True,'fitting_rows':487,'fitting_people':28,'session_queries_with_prior_reports':455,
    'task_queries_with_prior_reports':391,'new_predictive_models_fitted':0,'native_test_predictions_computed':0}
status['next_evidence_based_direction'] = (
    'Study51completed10predictor-normalization recipes/20independent joint refits; retained native test108/179and globalCV.637972. Neither50nor51sourcehistorytransfer improved the incumbent; do not repeat those weights/normalization/epoch grids. '
    'WSD162fitting-person PPGfiles have voltageonly,no sampletimestamps/onsetmarker; nominal durations differ from trial lengths(-5.71to+5.75s). No verified pre-report sensor join;do not invent offsets/rescale timelines. '
    'BBEXofficial metadata/CC0verified but API401/publiclink403deny originalbundle access; no workbookdata acquired. Do not retry unchanged requests or train from website summaries. '
    'Next predeclare nonparametric causal individual-memory retrieval on original native cases with matched population-only controls. Fitting-only coverage:455of487session queries have genuine earlier eligible selfreports,423haveatleasttwo;391task queries havepriorreports. Existing populationKNN,online ridge/SGDadaptation are already studied; do not repeat them. '
    'A distinct kernel-weighted observed-transition distribution may use only strictly earlier same-person/session reports,with distance/statistics fitted on outertrainingpeople; no current/future targets or stored held-person history in populationartifact. All this is an untested mechanism,not an achieved accuracy. '
    'Retain original487/179cases,public-real-only policy and.65CVgate;80percent requires144of179from a frozen reloaded artifact. No synthetic observations or test-directed tuning.')
for field in ('additional_scoped_verifications','additional_data_audits','additional_public_candidate_inspections'):
    assert all(digest(DOCS/name)==expected for name,expected in status[field].items())
status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'source_clock_review':'not_join_verified','bbex_access':'metadata_only_API401_public403',
    'genuine_native_session_memory_coverage':'455of487fittingqueries','completed_studies':51,
    'new_predictive_models_fitted':0,'best_verified_test_correct':status['best_verified_test_correct'],'goal_achieved':status['goal_achieved']}),flush=True)
