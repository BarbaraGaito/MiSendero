"""Independently rebuild report/pair provenance directly from original XLSX XML."""
import json
import math
import posixpath
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
import pandas as pd
import rpe_forecasting_history_inputs as prepared
from public_sources import digest

NS = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def xml_rows(path):
    with zipfile.ZipFile(path) as archive:
        assert sum(entry.file_size for entry in archive.infolist())<5_000_000
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        sheets = workbook.findall('s:sheets/s:sheet',NS)
        assert len(sheets)==1
        relations = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        relationship_id = sheets[0].attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        relationship = next(row for row in relations if row.attrib['Id']==relationship_id)
        assert relationship.attrib.get('TargetMode')!='External'
        target = relationship.attrib['Target']
        target = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        assert target.startswith('xl/worksheets/') and '..' not in target
        sheet = ET.fromstring(archive.read(target))
        rows = {}
        for node in sheet.findall('s:sheetData/s:row',NS):
            number = int(node.attrib['r'])
            values = [None]*5
            for cell in node.findall('s:c',NS):
                assert cell.find('s:f',NS) is None,'Source formulas are not observed targets'
                match = re.fullmatch(r'([A-E])([0-9]+)',cell.attrib['r'])
                assert match and int(match[2])==number
                value = cell.find('s:v',NS)
                if value is not None and value.text is not None:
                    assert cell.attrib.get('t','n')=='n'
                    values[ord(match[1])-65] = float(value.text)
                    assert math.isfinite(values[ord(match[1])-65])
            rows[number] = values
    return sheets[0].attrib['name'],rows


def verify():
    pairs,reports,manifest = prepared.load()
    inspection = json.loads(prepared.INSPECTION.read_text())
    directory = prepared.RAW/'workbooks'
    entries = [row for row in inspection['case2_file_inventory'] if row['source_partition']=='fitting']
    assert len(entries)==19 and {path.name for path in directory.glob('*.xlsx')}=={Path(row['path']).name for row in entries}
    source_hashes = {}
    rebuilt,original_lines,per_file = {},{},{}
    physical_nonempty,unassigned_count,inversion_count = 0,0,0
    for entry in entries:
        path = directory/Path(entry['path']).name
        content = path.read_bytes()
        assert len(content)==entry['bytes'] and prepared.candidate.git_blob(content)==entry['git_blob_sha1']
        receipt = json.loads(path.with_suffix('.receipt.json').read_text())
        assert receipt['sha256']==digest(path) and receipt['receiver_code_sha256']==digest(Path(prepared.receiver.__file__))
        source_hashes[path.name],source_hashes[path.with_suffix('.receipt.json').name] = digest(path),digest(path.with_suffix('.receipt.json'))
        sheet,rows = xml_rows(path)
        grouped = defaultdict(list)
        unassigned,sequence,inversions = [],[],[]
        for number,values in sorted(rows.items()):
            if all(value is None for value in values):
                continue
            physical_nonempty += 1
            if values[0] is None:
                unassigned.append({'worksheet_row':number,'values':values})
                unassigned_count += 1
                continue
            assert values[0]==int(values[0]) and values[0]>=1
            trial = int(values[0])
            if sequence and trial<sequence[-1]:
                inversions.append({'worksheet_row':number,'previous_trial':sequence[-1],'trial':trial})
            sequence.append(trial)
            grouped[trial].append((number,values))
        inversion_count += len(inversions)
        for trial,part in sorted(grouped.items()):
            cells = [{'cell':f'B{number}','worksheet_row':number,'value':values[1]} for number,values in part if values[1] is not None]
            unique = sorted(set(cell['value'] for cell in cells))
            assert unique and all(6<=value<=20 for value in unique)
            key = (entry['person'],trial)
            consistent = len(unique)==1
            last = cells[-1] if consistent else None
            rebuilt[key] = {'value':last['value'] if last else None,'cell':last['cell'] if last else None,
                'row_key':f"RPE_Forecasting_Case2:{entry['person']}:trial:{trial}",
                'group_key':entry['group_key'],'status':'one_consistent_report' if consistent else 'conflicting_original_rpe_cells',
                'last_row':part[-1][0],'gait':part[-1][1][2:],'file':path.name,'sheet':sheet,'values':unique,'cells':cells}
            original_lines[key] = rows
        per_file[entry['person']] = {'unassigned':unassigned,'inversions':inversions,'trials':len(grouped)}
    assert len(rebuilt)==434 and physical_nonempty==6147 and unassigned_count==40 and inversion_count==1
    assert len([row for row in rebuilt.values() if row['value'] is not None])==432
    by_id = reports.set_index('row_key')
    assert len(by_id)==434 and reports.row_key.is_unique
    lines = {(row['person'],row['trial']):row for row in manifest['report_lineage']}
    for key,row in rebuilt.items():
        saved = by_id.loc[row['row_key']]
        assert saved.group_key==row['group_key'] and saved.rpe_status==row['status']
        if row['value'] is None:
            assert pd.isna(saved.current_rpe)
        else:
            assert saved.current_rpe==row['value']
        np.testing.assert_allclose(saved[prepared.GAIT].to_numpy(float),[v if v is not None else np.nan for v in row['gait']],atol=1e-12,equal_nan=True)
        line = lines[key]
        assert line['rpe_cells']==row['cells'] and line['selected_rpe_cell']==row['cell'] and line['selected_rpe_value']==row['value']
        assert line['observed_values']==row['values'] and line['last_identified_stride_row']==row['last_row']
    for summary in manifest['source_file_summaries']:
        actual = per_file[summary['person']]
        assert summary['unassigned_nonempty_rows']==actual['unassigned']
        assert summary['physical_row_trial_inversions']==actual['inversions'] and summary['identified_trials']==actual['trials']
    expected = {}
    for (person,trial),row in rebuilt.items():
        old,older = rebuilt.get((person,trial-1)),rebuilt.get((person,trial-2))
        if row['value'] is None or old is None or old['value'] is None:
            continue
        expected[row['row_key']] = (row,old,older if older is not None and older['value'] is not None else None)
    assert len(expected)==410 and set(expected)==set(pairs.row_key)
    assert list(pairs)==['row_key','group_key','source_domain','source_partition','current_rpe','prior','second']
    pair_lines = {row['row_key']:row for row in manifest['pair_lineage']}
    for row in pairs.itertuples():
        current,old,older = expected[row.row_key]
        assert row.current_rpe==current['value'] and row.prior==old['value']
        assert row.group_key==current['group_key']==old['group_key'] and row.source_partition=='fitting'
        if older is None:
            assert pd.isna(row.second)
        else:
            assert row.second==older['value']
        line = pair_lines[row.row_key]
        assert line['current_trial']==line['prior_trial']+1
        assert line['current_rpe_cell']==current['cell'] and line['prior_rpe_cell']==old['cell']
        assert line['second_rpe_cell']==(older['cell'] if older else None)
        if older:
            assert line['second_trial']==line['current_trial']-2
        assert not line['absolute_report_clocks_known'] and not line['measured_report_ages_invented']
    assert pairs.second.notna().sum()==388 and pairs.current_rpe.eq(pairs.prior).sum()==158
    assert pairs.current_rpe.ne(pairs.prior).sum()==252 and pairs.current_rpe.lt(pairs.prior).sum()==0
    assert not manifest['any_gait_feature_used_as_model_predictor'] and not manifest['target_rounding_or_scale_conversion']
    assert not manifest['source_targets_pooled_as_native_borg'] and manifest['synthetic_targets']==manifest['synthetic_rows']==0
    assert manifest['reserved_people_not_received']==[1,9,12,17,19]
    report = {'verification':'passed','verification_code_sha256':digest(Path(__file__)),
        'preparation_code_sha256':digest(Path(prepared.__file__)),'provenance_sha256':digest(prepared.DIRECTORY/'provenance.json'),
        'reports_sha256':digest(prepared.DIRECTORY/'reports.csv'),'pairs_sha256':digest(prepared.DIRECTORY/'pairs.csv'),
        'candidate_inspection_sha256':digest(prepared.INSPECTION),'original_source_artifact_hashes':source_hashes,
        'independently_parsed_original_workbooks':19,'independently_parsed_stride_rows':6147,
        'identified_person_trial_reports':434,'unambiguous_original_reports':432,'conflicting_original_trials_excluded':2,
        'unassigned_nonempty_rows_preserved_in_provenance':40,'physical_row_order_inversions_preserved':1,
        'independently_rebuilt_actual_adjacent_pairs':410,'actual_second_priors':388,'fitting_people':19,
        'original_equal_pairs':158,'original_unequal_pairs':252,'reserved_people_received':0,
        'approved_for_separate_original_unequal_binary_head':True,
        'source_quantitative_target_merge_into_native_approved':False,'source_gait_predictor_alignment_approved':False,
        'invented_clocks_or_report_ages':0,'synthetic_targets':0,'target_rounding_or_conversion':False,
        'new_native_borg_cases':0,'new_predictive_estimator_fits':0,'new_test_predictions_computed':0}
    output = prepared.candidate.DOCS/'rpe-forecasting-history-input-verification.json'
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='original_source_artifact_hashes'}),flush=True)
    return report


if __name__=='__main__':
    verify()
