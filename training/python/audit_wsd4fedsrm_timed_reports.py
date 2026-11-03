"""Independently read original timed Borg cells; freeze people before eligibility."""
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from public_sources import digest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT/'docs/fatigue-80-2026-10-25'
RAW = ROOT/'training/data/raw/fatigue-research/wsd4fedsrm-8415066-v1'


def audit():
    archive = RAW/'WSD4FEDSRM.zip'
    receipt = json.loads((RAW/'receipt.json').read_text())
    previous_path = DOCS/'wsd4fedsrm-original-inspection.json'
    previous = json.loads(previous_path.read_text())
    assert archive.stat().st_size == receipt['bytes'] == 392734892
    assert digest(archive) == receipt['sha256'] == previous['original_archive_sha256']
    assert previous['inspection_code_sha256'] == digest(Path(__file__).with_name('inspect_wsd4fedsrm_originals.py'))
    annotation, = previous['annotation_files']
    with zipfile.ZipFile(archive) as original:
        blob = original.read(annotation['member'])
    assert hashlib.sha256(blob).hexdigest() == annotation['member_sha256']
    frame = pd.read_csv(io.BytesIO(blob),dtype=str,keep_default_na=False,encoding='utf-8-sig')
    assert len(frame) == 204 and frame.columns.is_unique
    subjects = frame.subject[frame.subject.ne('')].tolist()
    assert len(subjects) == len(set(subjects)) == 34
    # Partition all original identities before selecting usable report pairs.
    fit,held = next(GroupShuffleSplit(n_splits=1,test_size=.2,random_state=42).split(subjects,groups=subjects))
    fit_people = {subjects[i] for i in fit}
    held_people = {subjects[i] for i in held}
    assert (len(fit_people),len(held_people)) == (27,7) and not fit_people&held_people
    old = {(c['original_csv_line'],c['original_header']):c for c in annotation['original_cell_lineage'] if c['category'] == 'timed'}
    timed = [(column,int(re.fullmatch(r'(\d+)_sec',column.strip()).group(1)))
             for column in frame if re.fullmatch(r'\d+_sec',column.strip())]
    assert [seconds for _,seconds in timed] == list(range(10,251,10))
    tasks = set(frame.task_order)
    assert len(tasks) == 6
    records = []
    for start in range(0,204,6):
        block = frame.iloc[start:start+6]
        person = block.iloc[0].subject
        assert person == subjects[start//6] and block.subject.iloc[1:].eq('').all()
        assert set(block.task_order) == tasks and block.task_order.nunique() == 6
        for index,row in block.iterrows():
            history = []
            end = float(row['length_of_trial_(sec)'])
            for column,seconds in timed:
                if row[column] == '':
                    continue
                value = float(row[column])
                assert 6 <= value <= 20 and seconds <= end
                prior = old[(index+2,column)]
                assert (prior['original_person_from_verified_explicit_block'],prior['original_task_identifier'],
                        prior['numeric_value'],prior['timed_header_seconds']) == (person,row.task_order,value,seconds)
                record = {'person':person,'task':row.task_order,'csv_line':index+2,'original_header':column,
                    'elapsed_seconds':seconds,'original_borg_points':value,
                    'partition':'fitting' if person in fit_people else 'reserved',
                    'prior_timed_report':history[-1] if history else None,
                    'second_prior_timed_report':history[-2] if len(history)>1 else None}
                records.append(record)
                history.append({'elapsed_seconds':seconds,'original_borg_points':value,'original_header':column})
    assert len(records) == 1311 and sum(r['prior_timed_report'] is not None for r in records) == 1107
    assert sum(r['second_prior_timed_report'] is not None for r in records) == 904
    totals = {part:{'people':len(fit_people if part == 'fitting' else held_people),
        'timed_reports':sum(r['partition'] == part for r in records),
        'timed_pairs':sum(r['partition'] == part and r['prior_timed_report'] is not None for r in records),
        'two_timed_priors':sum(r['partition'] == part and r['second_prior_timed_report'] is not None for r in records)}
        for part in ('fitting','reserved')}
    report = {'verification':'passed','verification_code_sha256':digest(Path(__file__)),
        'original_inspection_sha256':digest(previous_path),'original_receipt_sha256':digest(RAW/'receipt.json'),
        'original_archive_sha256':digest(archive),'original_annotation_sha256':annotation['member_sha256'],
        'independent_reader':'pandas_csv_instead_of_original_inspector_csv_reader',
        'original_timed_cells_independently_checked':1311,'within_task_pairs':1107,'two_prior_targets':904,
        'person_partition_before_pair_eligibility':True,'partition_seed':42,
        'fitting_people':sorted(fit_people),'reserved_people':sorted(held_people),'partitions':totals,
        'before_task_and_terminal_cells_used_as_timed_reports':False,'cross_task_chronology_inferred':False,
        'sensor_join_verified':False,'source_native_outcomes_pooled':False,'synthetic_rows':0,
        'model_fitting_started':False,'original_timed_cell_lineage':records}
    output = DOCS/'wsd4fedsrm-timed-report-verification.json'
    if output.exists():
        assert json.loads(output.read_text()) == report,'Preserve the frozen timed-report audit'
    else:
        output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'verification':'passed','timed_cells':1311,'partitions':totals,'model_fitting_started':False}),flush=True)


if __name__ == '__main__':
    audit()
