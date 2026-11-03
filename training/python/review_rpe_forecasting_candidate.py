"""Inspect pinned public source context and reserve people before label review."""
import hashlib
import json
from pathlib import Path
import numpy as np
from sklearn.model_selection import GroupShuffleSplit
from public_sources import ROOT,digest

DIRECTORY = ROOT/'training/data/raw/fatigue-research/rpe-forecasting-2e2233a6-v1'
DOCS = ROOT/'docs/fatigue-80-2026-10-25'
REVISION = '2e2233a6a755b05dc4dc0404d580d401ff7d520e'


def git_blob(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def review():
    repository = json.loads((DIRECTORY/'repository.json').read_text())
    branch = json.loads((DIRECTORY/'branch.json').read_text())
    tree = json.loads((DIRECTORY/'tree.json').read_text())
    assert repository['full_name']=='sahand-hajifar/RPE_Forecasting' and not repository['private']
    assert branch['commit']['sha']==REVISION and not tree['truncated']
    context_entry = next(v for v in tree['tree'] if v['path']=='RPE_Prediction/RPE_Forecasting.Rmd')
    path = DIRECTORY/'source-context.Rmd'
    context_bytes = path.read_bytes()
    if git_blob(context_bytes)!=context_entry['sha']:
        # apply_patch added one terminal LF;remove it only if the published Git blob proves exact identity.
        assert context_bytes.endswith(b'\n') and git_blob(context_bytes[:-1])==context_entry['sha']
        context_bytes = context_bytes[:-1]
        path.write_bytes(context_bytes)
    assert len(context_bytes)==context_entry['size']==38140 and git_blob(context_bytes)==context_entry['sha']
    context = context_bytes.decode('utf-8')
    assert 'normalizing the length of the time series by percentile and then denoising by median filter' in context
    assert 'one RPE value reported for each period of squatting exercise' in context
    assert 'N_sub = 24' in context and 'last stride for each walking' in context
    files = [v for v in tree['tree'] if v['type']=='blob' and v['path'].startswith('Case 2 Data/') and v['path'].endswith('.xlsx')]
    lookup = {int(Path(v['path']).stem.removeprefix('ID').removesuffix('GaitFeatures')):v for v in files}
    assert len(lookup)==24 and set(lookup)==set(range(1,25))
    people = np.arange(1,25)
    fit,reserved = next(GroupShuffleSplit(n_splits=1,test_size=.2,random_state=42).split(people,groups=people))
    fit_people,reserved_people = people[fit].tolist(),people[reserved].tolist()
    assert len(fit_people)==19 and len(reserved_people)==5 and set(fit_people).isdisjoint(reserved_people)
    inventory = []
    for person,row in sorted(lookup.items()):
        inventory.append({'person':person,'group_key':f'RPE_Forecasting_Case2:{person}',
            'source_partition':'fitting' if person in fit_people else 'reserved',
            'path':row['path'],'bytes':row['size'],'git_blob_sha1':row['sha'],
            'raw_url':f'https://raw.githubusercontent.com/sahand-hajifar/RPE_Forecasting/{REVISION}/'+row['path'].replace(' ','%20')})
    report = {'inspection':'passed','inspection_code_sha256':digest(Path(__file__)),
        'repository':'https://github.com/sahand-hajifar/RPE_Forecasting','revision':REVISION,
        'snapshot_sha256':{name:digest(DIRECTORY/name) for name in ('repository.json','branch.json','tree.json','source-context.Rmd')},
        'source_context_git_blob_sha1':context_entry['sha'],'source_context_original_bytes_verified':True,
        'repository_public':True,'repository_license_field':repository.get('license'),
        'case1_use_for_fitting_approved':False,'case1_exclusion_reason':'Author context states percentile rescaling and median-filter preprocessing;these values are not approved as untouched original self-reports.',
        'case2_available_people':24,'case2_fitting_people':fit_people,'case2_reserved_people':reserved_people,
        'participant_split_frozen_before_original_target_review':True,'partition_random_seed':42,
        'case2_file_inventory':inventory,'case2_total_workbook_bytes':sum(v['bytes'] for v in inventory),
        'case2_protocol_context':'One reported RPE per squatting period;authors select last stride per following walking period. Repeated stride rows are not independent RPE reports.',
        'case2_instrument_scale_verified':False,'case2_raw_target_cells_verified':False,
        'case2_actual_report_order_verified':False,'case2_original_workbooks_downloaded':0,
        'case2_training_merge_approved':False,'new_native_borg_cases':0,
        'new_predictive_estimator_fits':0,'new_test_predictions_computed':0,
        'downloaded_author_code_executed':False,
        'next_required_evidence':'Retrieve only the19fitting original workbooks from the pinned revision,verify Git blob hashes,inspect raw headers/cells and protocol scale/order. Do not create ratings from duplicated strides or apply Case1rescaling/filters. Reserved5people stay excluded from fitting. Keep this external instrument separate from native exact Borg until compatibility is established.'}
    output = DOCS/'rpe-forecasting-candidate-inspection.json'
    if output.exists():
        assert json.loads(output.read_text())==report
    else:
        output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='case2_file_inventory'}),flush=True)
    return report


if __name__=='__main__':
    review()
