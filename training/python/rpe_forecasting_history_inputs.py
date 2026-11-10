"""One literal public RPE per unambiguous trial;never one target per stride."""
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
import openpyxl
import pandas as pd
import receive_rpe_forecasting_workbook as receiver
import review_rpe_forecasting_candidate as candidate
from fatigue_features import RESEARCH
from public_sources import digest

DIRECTORY = RESEARCH/'rpe-forecasting-history-inputs-80-v1'
RAW = candidate.DIRECTORY
INSPECTION = candidate.DOCS/'rpe-forecasting-candidate-inspection.json'
GAIT = ['mean_acceleration','max_acceleration','stride_duration']


def dependencies():
    inspection = json.loads(INSPECTION.read_text())
    paths = {'preparation_code':Path(__file__),'receiver_code':Path(receiver.__file__),
        'candidate_inspection':INSPECTION,'candidate_inspection_code':Path(candidate.__file__),
        'author_source_context':RAW/'source-context.Rmd',
        'public_real_data_policy':candidate.DOCS/'public-real-data-policy.json'}
    for row in inspection['case2_file_inventory']:
        if row['source_partition']=='fitting':
            path = RAW/'workbooks'/Path(row['path']).name
            paths[path.name] = path
            paths[path.with_suffix('.receipt.json').name] = path.with_suffix('.receipt.json')
    return {name:digest(path) for name,path in paths.items()}


def numeric(value):
    assert isinstance(value,(int,float)) and not isinstance(value,bool) and np.isfinite(value)
    return float(value)


def prepare():
    assert not DIRECTORY.exists(),'Preserve frozen preparation'
    inspection = json.loads(INSPECTION.read_text())
    assert inspection['inspection']=='passed' and inspection['inspection_code_sha256']==digest(Path(candidate.__file__))
    assert inspection['participant_split_frozen_before_original_target_review']
    expected = {Path(row['path']).name for row in inspection['case2_file_inventory'] if row['source_partition']=='fitting'}
    assert {path.name for path in (RAW/'workbooks').glob('*.xlsx')}==expected and len(expected)==19
    reports,lineage,summaries = [],[],[]
    for entry in inspection['case2_file_inventory']:
        if entry['source_partition']!='fitting':
            continue
        path = RAW/'workbooks'/Path(entry['path']).name
        content = path.read_bytes()
        receipt = json.loads(path.with_suffix('.receipt.json').read_text())
        assert len(content)==entry['bytes'] and candidate.git_blob(content)==entry['git_blob_sha1']
        assert receipt['sha256']==digest(path) and receipt['receiver_code_sha256']==digest(Path(receiver.__file__))
        assert receipt['person']==entry['person'] and receipt['source_partition']=='fitting'
        book = openpyxl.load_workbook(path,read_only=True,data_only=False)
        assert len(book.worksheets)==1
        sheet = book.worksheets[0]
        assert sheet.max_column==5
        grouped = defaultdict(list)
        blank,unassigned,known_sequence,inversions = [],[],[],[]
        for number,row in enumerate(sheet.iter_rows(values_only=True),1):
            assert len(row)==5 and not any(isinstance(v,str) for v in row)
            if all(value is None for value in row):
                blank.append(number)
                continue
            if row[0] is None:
                unassigned.append({'worksheet_row':number,'values':list(row)})
                continue
            trial = numeric(row[0])
            assert trial==int(trial) and trial>=1
            if known_sequence and int(trial)<known_sequence[-1]:
                inversions.append({'worksheet_row':number,'previous_trial':known_sequence[-1],'trial':int(trial)})
            grouped[int(trial)].append((number,row))
            known_sequence.append(int(trial))
        per_person = {}
        ambiguous = []
        for trial,rows in sorted(grouped.items()):
            cells = [{'cell':f'B{n}','worksheet_row':n,'value':numeric(row[1])} for n,row in rows if row[1] is not None]
            values = sorted(set(cell['value'] for cell in cells))
            assert cells and all(6<=value<=20 for value in values)
            consistent = len(values)==1
            if not consistent:
                ambiguous.append({'trial':trial,'observed_values':values,'rpe_cells':cells})
            selected = cells[-1] if consistent else None
            last_number,last_row = rows[-1]
            row_key = f"RPE_Forecasting_Case2:{entry['person']}:trial:{trial}"
            report = {'row_key':row_key,'group_key':entry['group_key'],'source_domain':'gait_forecasting',
                'source_partition':'fitting','person':entry['person'],'trial':trial,
                'current_rpe':selected['value'] if selected else np.nan,
                'rpe_status':'one_consistent_report' if consistent else 'conflicting_original_rpe_cells',
                **{name:numeric(value) if value is not None else np.nan for name,value in zip(GAIT,last_row[2:])}}
            reports.append(report)
            line = {'row_key':row_key,'group_key':entry['group_key'],'person':entry['person'],'trial':trial,
                'original_file':path.name,'sheet':sheet.title,'original_file_sha256':digest(path),
                'rpe_cells':cells,'selected_rpe_cell':selected['cell'] if selected else None,
                'selected_rpe_value':selected['value'] if selected else None,
                'last_identified_stride_row':last_number,'observed_values':values,'consistent_report':consistent}
            lineage.append(line)
            per_person[trial] = report,line
        summaries.append({'person':entry['person'],'original_file':path.name,'worksheet_rows':sheet.max_row,
            'known_trial_rows':len(known_sequence),'identified_trials':len(grouped),'blank_worksheet_rows':blank,
            'unassigned_nonempty_rows':unassigned,'ambiguous_trials':ambiguous,'physical_row_trial_inversions':inversions,
            'missing_trial_ids':[n for n in range(1,max(grouped)+1) if n not in grouped]})
        book.close()
    report_frame = pd.DataFrame(reports)
    by_key = {(row['person'],row['trial']):row for row in reports}
    line_by_key = {(row['person'],row['trial']):row for row in lineage}
    pairs,pair_lineage,excluded = [],[],[]
    for row in reports:
        person,trial = row['person'],row['trial']
        prior = by_key.get((person,trial-1))
        older = by_key.get((person,trial-2))
        reason = ('ambiguous_current_report' if not np.isfinite(row['current_rpe']) else
            'no_identified_adjacent_prior_report' if prior is None else
            'ambiguous_adjacent_prior_report' if not np.isfinite(prior['current_rpe']) else None)
        if reason:
            excluded.append({'row_key':row['row_key'],'reason':reason})
            continue
        second = older['current_rpe'] if older is not None and np.isfinite(older['current_rpe']) else np.nan
        pairs.append({'row_key':row['row_key'],'group_key':row['group_key'],'source_domain':'gait_forecasting',
            'source_partition':'fitting','current_rpe':row['current_rpe'],'prior':prior['current_rpe'],'second':second})
        current_line,prior_line = line_by_key[person,trial],line_by_key[person,trial-1]
        second_line = line_by_key.get((person,trial-2))
        pair_lineage.append({'row_key':row['row_key'],'group_key':row['group_key'],'person':person,
            'current_trial':trial,'prior_trial':trial-1,'second_trial':trial-2 if np.isfinite(second) else None,
            'original_file':current_line['original_file'],'current_rpe_cell':current_line['selected_rpe_cell'],
            'prior_rpe_cell':prior_line['selected_rpe_cell'],
            'second_rpe_cell':second_line['selected_rpe_cell'] if np.isfinite(second) else None,
            'prior_gait_row_not_used_as_predictor':prior_line['last_identified_stride_row'],
            'absolute_report_clocks_known':False,'measured_report_ages_invented':False})
    frame = pd.DataFrame(pairs)
    assert len(report_frame)==434 and report_frame.current_rpe.notna().sum()==432
    assert len(frame)==410 and frame.second.notna().sum()==388 and frame.group_key.nunique()==19
    assert set(frame.current_rpe.ne(frame.prior))=={False,True}
    DIRECTORY.mkdir()
    report_frame.to_csv(DIRECTORY/'reports.csv',index=False)
    frame.to_csv(DIRECTORY/'pairs.csv',index=False)
    manifest = {'version':1,'dependencies_sha256':dependencies(),
        'reports_sha256':digest(DIRECTORY/'reports.csv'),'pairs_sha256':digest(DIRECTORY/'pairs.csv'),
        'original_workbooks':19,'original_bytes':sum(row['bytes'] for row in inspection['case2_file_inventory'] if row['source_partition']=='fitting'),
        'identified_trial_reports':434,'unambiguous_original_reports':432,'ambiguous_trial_reports':2,
        'eligible_original_adjacent_pairs':410,'actual_second_priors':388,'source_people':19,
        'reserved_people_not_received':inspection['case2_reserved_people'],
        'source_original_value_range':[float(report_frame.current_rpe.min()),float(report_frame.current_rpe.max())],
        'fractional_current_reports':int(((report_frame.current_rpe.dropna()%1)!=0).sum()),
        'actual_equal_pairs':int(frame.current_rpe.eq(frame.prior).sum()),
        'actual_unequal_pairs':int(frame.current_rpe.ne(frame.prior).sum()),
        'actual_decreasing_pairs':int(frame.current_rpe.lt(frame.prior).sum()),
        'synthetic_targets':0,'synthetic_rows':0,'target_rounding_or_scale_conversion':False,
        'missing_trial_ids_filled':False,'last_rpe_carried_into_missing_trials':False,
        'absolute_report_clocks_known':False,'measured_report_ages_assumed':False,
        'current_target_stride_features_approved_for_pretarget_prediction':False,
        'any_gait_feature_used_as_model_predictor':False,
        'report_order_source':'Original numeric trial indices and author group-by-trial forecasting extraction;not physical worksheet row position. Absolute times and within-trial gait alignment remain unverified.',
        'physical_row_trial_inversions':sum(len(row['physical_row_trial_inversions']) for row in summaries),
        'source_gait_units_or_placement_equated_to_native':False,
        'source_targets_pooled_as_native_borg':False,'binary_separate_head_eligibility_pending_independent_audit':True,
        'source_scale_note':'Original literal RPE values preserved;author forecasting framework describes6-20. Case2raw observed range6-18.5. No equivalence with native0-10 is assumed;binary unequal-current/prior predicate does not convert scales.',
        'author_protocol_urls':['https://github.com/sahand-hajifar/RPE_Forecasting/blob/2e2233a6a755b05dc4dc0404d580d401ff7d520e/RPE_Prediction/RPE_Forecasting.Rmd',
            'https://pubmed.ncbi.nlm.nih.gov/33393439/','https://repository.rit.edu/theses/10275/'],
        'new_predictive_estimator_fits':0,'new_native_borg_cases':0,'new_test_predictions_computed':0,
        'source_file_summaries':summaries,'report_lineage':lineage,'pair_lineage':pair_lineage,'excluded_pair_candidates':excluded}
    (DIRECTORY/'provenance.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({key:value for key,value in manifest.items() if key not in ('dependencies_sha256','source_file_summaries','report_lineage','pair_lineage','excluded_pair_candidates')}),flush=True)


def load():
    manifest = json.loads((DIRECTORY/'provenance.json').read_text())
    assert manifest['dependencies_sha256']==dependencies()
    assert manifest['reports_sha256']==digest(DIRECTORY/'reports.csv') and manifest['pairs_sha256']==digest(DIRECTORY/'pairs.csv')
    reports,pairs = pd.read_csv(DIRECTORY/'reports.csv'),pd.read_csv(DIRECTORY/'pairs.csv')
    assert len(reports)==434 and len(pairs)==410 and pairs.second.notna().sum()==388
    assert pairs.source_partition.eq('fitting').all() and pairs.group_key.nunique()==19
    return pairs,reports,manifest


if __name__=='__main__':
    prepare()
