"""Inspect fitting-person signal schema/duration without inventing report joins."""
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path
import numpy as np
from public_sources import digest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT/'docs/fatigue-80-2026-10-25'
RAW = ROOT/'training/data/raw/fatigue-research/wsd4fedsrm-8415066-v1'
CONDITIONS = {'task1_35i':'30-40_ internal rotation','task2_45i':'40-50_ internal rotation',
    'task3_55i':'50-60_ internal rotation','task4_35e':'30-40_ external rotation',
    'task5_45e':'40-50_ external rotation','task6_55e':'50-60_ external rotation'}


def inspect():
    archive = RAW/'WSD4FEDSRM.zip'
    receipt = json.loads((RAW/'receipt.json').read_text())
    assert digest(archive)==receipt['sha256']
    audit_path = DOCS/'wsd4fedsrm-timed-report-verification.json'
    audit = json.loads(audit_path.read_text())
    fitting,reserved = set(audit['fitting_people']),set(audit['reserved_people'])
    assert len(fitting)==27 and len(reserved)==7 and fitting.isdisjoint(reserved)
    records = []
    with zipfile.ZipFile(archive) as original:
        description_blob = original.read('WSD4FEDSRM/description.txt')
        description = description_blob.decode('cp1252')
        assert '200 Hz' in description and all(task in description for task in CONDITIONS)
        borg_blob = original.read('WSD4FEDSRM/Borg data/borg_data.csv')
        rows = list(csv.DictReader(io.StringIO(borg_blob.decode('utf-8-sig'))))
        person = None
        for row in rows:
            if row['subject']:
                person = row['subject']
            if person not in fitting:
                continue
            assert person not in reserved
            number = person.split('_')[1]
            task = row['task_order']
            member = f'WSD4FEDSRM/EMG, IMU, and PPG data/{CONDITIONS[task]}/Subject {number}/PPG data/ppg.csv'
            payload = original.read(member)
            raw = list(csv.reader(io.StringIO(payload.decode('utf-8-sig'))))
            assert raw[0]==['PPG(Volt)'] and all(len(values)==1 for values in raw)
            signal = np.asarray([float(values[0]) for values in raw[1:]])
            assert len(signal)>0 and np.isfinite(signal).all()
            reported_length = float(row['length_of_trial_(sec)'])
            records.append({'original_person':person,'original_condition':task,'member':member,
                'member_sha256':hashlib.sha256(payload).hexdigest(),'original_header':raw[0],
                'samples':len(signal),'nominal_documented_sampling_hz':200,
                'duration_at_nominal_sampling_seconds':len(signal)/200.,'recorded_trial_length_seconds':reported_length,
                'nominal_duration_minus_recorded_length_seconds':len(signal)/200.-reported_length,
                'sample_timestamps_released':False,'report_signal_onset_offset_verified':False})
    assert len(records)==162 and len({r['original_person'] for r in records})==27
    errors = np.asarray([r['nominal_duration_minus_recorded_length_seconds'] for r in records])
    report = {'inspection':'complete','inspection_code_sha256':digest(Path(__file__)),
        'original_archive_sha256':receipt['sha256'],'original_report_partition_sha256':digest(audit_path),
        'original_description_sha256':hashlib.sha256(description_blob).hexdigest(),
        'original_borg_annotation_sha256':hashlib.sha256(borg_blob).hexdigest(),
        'primary_protocol':'https://pmc.ncbi.nlm.nih.gov/articles/PMC11055894/',
        'condition_mapping_from_original_description':CONDITIONS,'source_fitting_people':27,'source_fitting_ppg_files':162,
        'reserved_person_signals_read':0,'schema_has_sample_timestamp_column':False,
        'nominal_duration_error_seconds':{'minimum':float(errors.min()),'median':float(np.median(errors)),
            'maximum':float(errors.max()),'absolute_error_over_one_second':int((abs(errors)>1).sum()),
            'absolute_error_over_five_seconds':int((abs(errors)>5).sum())},
        'original_file_schema_and_lengths':records,'ppg_to_report_temporal_join_verified':False,
        'source_windows_created':0,'heart_rate_values_derived':0,'new_predictive_models_fitted':0,'synthetic_rows':0,
        'decision':'Preserve genuine source signals but do not join sample_index/200to Borgreport clocks as verified elapsedtime. Original CSVhas only voltage; nominal length agreement is not a measured onset marker. Description24-hourtime belongs to demographics,not individual PPGsamples. Need primary evidence for signal/task onset before creating pre-report labels/windows; do not rescale samples to trial length or invent offsets.'}
    output = DOCS/'wsd4fedsrm-ppg-clock-inspection.json'
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('inspection','source_fitting_people','source_fitting_ppg_files',
        'reserved_person_signals_read','nominal_duration_error_seconds','ppg_to_report_temporal_join_verified')}),flush=True)


if __name__=='__main__':
    inspect()
