"""Rebuild all prepared histories independently from original CSV cells."""
import csv
import io
import json
import re
import zipfile
from pathlib import Path

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
import wsd4fedsrm_history_inputs as source
from public_sources import digest


def verify():
    raw = source.ROOT/'training/data/raw/fatigue-research/wsd4fedsrm-8415066-v1'
    receipt = json.loads((raw/'receipt.json').read_text())
    archive = raw/'WSD4FEDSRM.zip'
    assert digest(archive) == receipt['sha256']
    with zipfile.ZipFile(archive) as original:
        rows = list(csv.reader(io.StringIO(original.read('WSD4FEDSRM/Borg data/borg_data.csv').decode('utf-8-sig'))))
    header,data = rows[0],rows[1:]
    assert len(data) == 204 and len(header) == 30
    people = [r[0] for r in data if r[0]]
    assert len(people) == len(set(people)) == 34
    fit,held = next(GroupShuffleSplit(n_splits=1,test_size=.2,random_state=42).split(people,groups=people))
    fitting = {people[i] for i in fit}
    reserved = {people[i] for i in held}
    proof = json.loads(source.AUDIT.read_text())
    assert fitting == set(proof['fitting_people']) and reserved == set(proof['reserved_people'])
    timed_columns = [(i,int(m.group(1))) for i,h in enumerate(header) if (m:=re.fullmatch(r'(\d+)_sec',h.strip()))]
    expected = []
    known = 0
    for block in range(34):
        task_rows = data[block*6:(block+1)*6]
        person = task_rows[0][0]
        assert person == people[block] and all(not r[0] for r in task_rows[1:])
        assert len({r[1] for r in task_rows}) == 6
        for offset,row in enumerate(task_rows):
            line = 2+block*6+offset
            end = float(row[header.index('length_of_trial_(sec)')])
            history = [(seconds,float(row[col]),header[col]) for col,seconds in timed_columns if row[col].strip()]
            assert all(seconds <= end and 6 <= value <= 20 for seconds,value,_ in history)
            known += len(history)
            for index,(seconds,value,column) in enumerate(history):
                if not index:
                    continue
                prior_seconds,prior_value,prior_column = history[index-1]
                second = history[index-2] if index >= 2 else None
                assert prior_seconds < seconds and (second is None or second[0] < prior_seconds)
                expected.append({'row_key':f'wsd:{person}:{row[1]}:{column.strip()}',
                    'group_key':'wsd:'+person,'task_key':row[1],
                    'source_partition':'fitting' if person in fitting else 'reserved',
                    'original_rpe_points':value,'prior_rpe_points':prior_value,
                    'second_prior_rpe_points':None if second is None else second[1],
                    'elapsed_seconds':seconds,'prior_elapsed_seconds':prior_seconds,
                    'second_prior_elapsed_seconds':None if second is None else second[0],
                    'prior_age_minutes':(seconds-prior_seconds)/60.,
                    'second_prior_age_minutes':None if second is None else (seconds-second[0])/60.,
                    'original_csv_line':line,'current_original_header':column,'prior_original_header':prior_column,
                    'second_prior_original_header':None if second is None else second[2]})
    assert known == 1311 and len(expected) == 1107
    original_pairs = pd.read_csv(io.StringIO(pd.DataFrame(expected).to_csv(index=False)))
    prepared = pd.read_csv(source.DIRECTORY/'dataset.csv')
    pd.testing.assert_frame_equal(prepared,original_pairs,check_dtype=False,rtol=0,atol=1e-12)
    provenance = json.loads((source.DIRECTORY/'provenance.json').read_text())
    assert provenance['preparation_code_sha256'] == digest(Path(source.__file__))
    assert provenance['input_audit_sha256'] == digest(source.AUDIT)
    assert provenance['dataset_sha256'] == digest(source.DIRECTORY/'dataset.csv')
    for part,n,p,second in [('fitting',920,27,758),('reserved',187,7,146)]:
        subset = prepared[prepared.source_partition.eq(part)]
        assert (len(subset),subset.group_key.nunique(),subset.second_prior_rpe_points.notna().sum()) == (n,p,second)
    report = {'verification':'passed','audit_code_sha256':digest(Path(__file__)),
        'source_preparation_code_sha256':digest(Path(source.__file__)),
        'source_provenance_sha256':digest(source.DIRECTORY/'provenance.json'),
        'source_dataset_sha256':digest(source.DIRECTORY/'dataset.csv'),
        'original_report_verification_sha256':digest(source.AUDIT),'original_archive_sha256':digest(archive),
        'all_original_pairs_independently_rebuilt':1107,'source_fitting_targets':920,'source_reserved_targets':187,
        'source_fitting_people':27,'source_reserved_people':7,'source_fitting_actual_second_priors':758,
        'all_history_values_and_clocks_checked_against_original_cells':True,
        'person_partition_before_pair_eligibility':True,'natural_missing_second_priors_preserved':True,
        'terminal_or_before_task_rows_used':0,'cross_task_histories_created':0,'sensor_joins':0,
        'source_outcomes_kept_separate':True,'native_target_merge':False,'synthetic_rows':0,'model_fitting_started':False}
    output = source.DOCS/'wsd4fedsrm-history-input-verification.json'
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    verify()
