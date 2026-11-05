"""Independently rebuild the new source-pair expansion from original CSV cells."""
import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

import fatigue_resistance_history_inputs as source
from public_sources import digest,group_key


def verify():
    provenance_path = source.DIRECTORY/"provenance.json"
    provenance = json.loads(provenance_path.read_text())
    assert provenance["dependencies_sha256"] == source.dependencies()
    assert provenance["dataset_sha256"] == digest(source.DIRECTORY/"dataset.csv")
    proof = json.loads(source.AUDIT.read_text())
    assert proof["verification"] == "passed" and proof["audit_code_sha256"] == digest(Path(__file__).with_name("audit_resistance_reported_rpe.py"))
    receipt = json.loads((source.repository.DIRECTORY/"resistance-archive-receipt.json").read_text())
    archive_path = source.repository.DIRECTORY/receipt["local_filename"]
    assert digest(archive_path) == receipt["sha256"] == proof["original_archive_sha256"]
    with zipfile.ZipFile(archive_path) as archive:
        payload = archive.read(proof["original_annotation_member"])
    assert hashlib.sha256(payload).hexdigest() == proof["original_annotation_member_sha256"]
    raw = list(csv.reader(io.StringIO(payload.decode("utf-8-sig"))))
    people = sorted({name.split("_")[0] for name in raw[0]})
    fit,held = next(GroupShuffleSplit(n_splits=1,test_size=.2,random_state=42).split(people,groups=people))
    fitting_people,reserved_people = {people[i] for i in fit},{people[i] for i in held}
    assert fitting_people == set(proof["whole_person_split"]["fitting_original_people"])
    assert reserved_people == set(proof["whole_person_split"]["reserved_original_people"])
    expected = []
    for column,set_id in enumerate(raw[0]):
        person = set_id.split("_")[0]
        sequence = {index:float(Decimal(row[column])) for index,row in enumerate(raw[2:]) if len(row)>column and row[column].strip()}
        assert sorted(sequence) == list(range(len(sequence)))
        for index in range(1,len(sequence)):
            expected.append({"source_domain":"resistance","source_partition":"fitting" if person in fitting_people else "reserved",
                "row_key":group_key(f"Resistance-original-RPE:{set_id}:{index}"),"group_key":group_key(f"Resistance-original-participant:{person}"),
                "sequence_key":group_key(f"Resistance-original-set:{set_id}"),"original_set_id":set_id,
                "original_repetition_index_zero_based":index,"original_resistance_rpe":sequence[index],
                source.PRIOR:sequence[index-1],source.SECOND:sequence.get(index-2,np.nan),
                "prior_row_key":group_key(f"Resistance-original-RPE:{set_id}:{index-1}"),
                "public_ordered_second_prior_row_key":None if index == 1 else group_key(f"Resistance-original-RPE:{set_id}:{index-2}"),
                "original_rpe_csv_line":index+3,"original_rpe_csv_column":column+1})
    expected = pd.DataFrame(expected)
    frame = pd.read_csv(source.DIRECTORY/"dataset.csv")
    additional = frame[frame.source_domain.eq("resistance")].reset_index(drop=True)
    pd.testing.assert_frame_equal(additional[expected.columns],expected,check_dtype=False,rtol=0,atol=0)
    old = pd.read_csv(source.previous.DIRECTORY/"dataset.csv")
    pd.testing.assert_frame_equal(frame[frame.source_domain.ne("resistance")][old.columns].reset_index(drop=True),old,check_dtype=False,rtol=0,atol=1e-12)
    assert len(frame) == 1541 and frame.row_key.is_unique and len(additional) == 934
    assert additional.group_key.nunique() == 5 and additional.sequence_key.nunique() == 69
    assert additional[source.SECOND].isna().sum() == 69
    assert not additional[["borg_native","current_rpe","hr_last","hr_history_mean"]].notna().any().any()
    assert not frame[frame.source_domain.ne("resistance")].original_resistance_rpe.notna().any()
    fitting,reserved = frame[frame.source_partition.eq("fitting")],frame[frame.source_partition.eq("reserved")]
    assert len(fitting) == 1416 and len(reserved) == 125 and set(fitting.group_key).isdisjoint(reserved.group_key)
    assert fitting[source.SECOND].notna().sum() == 1169
    assert fitting.groupby("source_domain").size().to_dict() == {"emap":248,"worker":253,"sts":49,"resistance":866}
    assert reserved.groupby("source_domain").size().to_dict() == {"emap":57,"resistance":68}
    assert provenance["synthetic_rows"] == provenance["imputed_targets"] == provenance["invented_source_ages_or_phase_mapping"] == 0
    assert provenance["new_sensor_joins"] == provenance["new_native_borg_targets"] == 0 and provenance["source_outcomes_must_remain_separate"]
    report = {"version":1,"verification":"passed","verified_at":datetime.now(timezone.utc).isoformat(),
        "audit_code_sha256":digest(Path(__file__)),"source_preparation_code_sha256":digest(Path(source.__file__)),
        "source_provenance_sha256":digest(provenance_path),"original_report_verification_sha256":digest(source.AUDIT),
        "previous_provenance_sha256":digest(source.previous.DIRECTORY/"provenance.json"),"original_annotation_cells_used_for_new_pairs":1003,
        "actual_resistance_pairs_independently_rebuilt":934,"resistance_fitting_pairs":866,"resistance_reserved_pairs":68,
        "resistance_fitting_people":4,"resistance_reserved_people":1,"resistance_genuine_second_priors":865,
        "previous_source_pairs_preserved":607,"previous_source_fitting_targets_preserved":550,"combined_source_fitting_targets":1416,
        "combined_stored_reserved_targets":125,"combined_source_fitting_actual_second_priors":1169,
        "original_source_current_targets_preserved":True,"source_outcomes_kept_separate":True,
        "source_person_split_independently_reproduced_before_eligibility":True,"synthetic_rows":0,"imputed_targets":0,
        "invented_source_clocks_or_phase_mapping":0,"new_sensor_joins":0,"new_native_targets":0,"model_fitting_started":False,
        "scope":"Independent original CSV-cell reconstruction of934genuine within-set resistance pairs,866fitting/68reserved by whole original person. All607previous public pairs and550fitting targets preserved. Additional1-10reported outcomes stay in their separate source head; no native label conversion. Both previous reports are actually measured,69naturally unavailable second priors retained. No SMOTE/jitter rows,learned EMG labels,generated examples,inferred times/sensors or changed native487/179cases."}
    output = source.DOCS/"resistance-history-input-verification.json"
    output.write_text(json.dumps(report,indent=2,ensure_ascii=True,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(report),flush=True)
    return report


if __name__ == "__main__":
    verify()
