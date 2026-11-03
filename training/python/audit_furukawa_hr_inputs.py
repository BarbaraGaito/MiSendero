"""Independently rebuild the runner HR adapter from original XLSX XML cells."""
from __future__ import annotations

import json
import math
import posixpath
import re
import statistics
import zipfile
from datetime import datetime,timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

import fatigue_furukawa_hr_inputs as prepared
from public_sources import digest,group_key

S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def clock(value):
    if isinstance(value,str) and re.fullmatch(r"\d{2}:[0-5]\d:[0-5]\d",value):
        h,m,s = map(int,value.split(":"))
        if h > 23:
            raise ValueError("Invalid explicit original workbook clock")
        return h*3600+m*60+s
    if isinstance(value,float) and 0 <= value < 1:
        seconds = value*86400
        if abs(seconds-round(seconds)) < 1e-6:
            return int(round(seconds))
    raise ValueError("Unsupported original explicit XLSX elapsed clock")


def xml_workbook(path):
    with zipfile.ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(n.text or "" for n in si.iter(S+"t")) for si in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        relations = {v.attrib["Id"]:v.attrib["Target"] for v in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        sheets = {}
        for entry in ET.fromstring(archive.read("xl/workbook.xml")).find(S+"sheets"):
            target = relations[entry.attrib[R+"id"]]
            member = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/"+target)
            cells = {}
            for c in ET.fromstring(archive.read(member)).iter(S+"c"):
                if c.find(S+"f") is not None:
                    raise ValueError("Formula results cannot replace source observed values")
                if c.attrib.get("t") == "inlineStr":
                    value = "".join(n.text or "" for n in c.iter(S+"t"))
                else:
                    node = c.find(S+"v")
                    if node is None:
                        continue
                    value = strings[int(node.text)] if c.attrib.get("t") == "s" else float(node.text)
                cells[c.attrib["r"]] = value
            sheets[entry.attrib["name"].strip()] = {"original_sheet":entry.attrib["name"],"cells":cells}
    return sheets


def validate():
    provenance_path = prepared.DIRECTORY/"provenance.json"
    provenance = json.loads(provenance_path.read_text())
    assert provenance["dependencies_sha256"] == prepared.dependencies()
    assert provenance["dataset_sha256"] == digest(prepared.DIRECTORY/"dataset.csv")
    source_proof = json.loads(prepared.AUDIT.read_text())
    assert source_proof["verification"] == "passed" and source_proof["audit_code_sha256"] == digest(Path(prepared.original.__file__))
    sheets = {}
    for kind in ("rpe","hr"):
        item = source_proof["original_files"][kind]
        path = prepared.original.repository.DIRECTORY/"files/runners"/item["filename"]
        assert digest(path) == item["sha256"] and digest(path,"md5") == item["repository_md5"]
        sheets[kind] = xml_workbook(path)
        assert set(sheets[kind]) == prepared.original.CONDITIONS
        for values in sheets[kind].values():
            assert values["cells"]["B1"] == prepared.original.UNITS[kind]
            assert [values["cells"][chr(66+i)+"2"] for i in range(16)] == prepared.original.PEOPLE
    people = np.asarray([f"p{i}" for i in range(1,17)])
    fit,res = next(GroupShuffleSplit(n_splits=1,test_size=.2,random_state=42).split(people,groups=people))
    fitting,reserved = set(people[fit]),set(people[res])
    assert sorted(fitting) == source_proof["whole_person_split"]["fitting_original_people"]
    assert sorted(reserved) == source_proof["whole_person_split"]["reserved_original_people"]
    frame = pd.read_csv(prepared.DIRECTORY/"dataset.csv")
    expected_keys,checked_cells = set(),set()
    by_row = {r["row_key"]:r for r in provenance["response_lineage"]}
    for row in frame.to_dict("records"):
        person,condition,stamp = row["original_person_header"],row["original_condition"],int(row["elapsed_seconds"])
        assert person in fitting|reserved and condition in sheets["rpe"] and stamp in (60,180,300)
        column = chr(65+int(person[1:]))
        targets,hr = sheets["rpe"][condition],sheets["hr"][condition]
        rpe_times = {clock(value):int(coord[1:]) for coord,value in targets["cells"].items() if re.fullmatch(r"A\d+",coord) and int(coord[1:])>=3}
        hr_times = {clock(value):int(coord[1:]) for coord,value in hr["cells"].items() if re.fullmatch(r"A\d+",coord) and int(coord[1:])>=3}
        assert sorted(rpe_times) == [60,180,300] and sorted(hr_times) == list(range(10,311,10))
        tcell = column+str(rpe_times[stamp])
        assert row["original_rpe_cell"] == tcell and row["original_rpe_points"] == targets["cells"][tcell]
        checked_cells.add((condition,tcell))
        key = group_key(f"Furukawa2023-original-exp2:{condition}:{person}:RPE:{stamp}")
        assert row["row_key"] == key and key not in expected_keys
        expected_keys.add(key)
        assert row["group_key"] == group_key(f"Furukawa2023-original-exp2-person:{person}")
        assert row["sequence_key"] == group_key(f"Furukawa2023-original-exp2-condition:{condition}:person:{person}")
        assert row["source_partition"] == ("fitting" if person in fitting else "reserved")
        assert row["source_domain"] == "furukawa_exp2_original_points"
        earlier = sorted(t for t in rpe_times if t < stamp)
        for prefix,old in (("prior",earlier[-1] if earlier else None),("second_prior",earlier[-2] if len(earlier)>1 else None)):
            if old is None:
                assert pd.isna(row[prefix+"_rpe_points"]) and pd.isna(row[prefix+"_rpe_elapsed_seconds"])
            else:
                assert row[prefix+"_rpe_points"] == targets["cells"][column+str(rpe_times[old])]
                assert row[prefix+"_rpe_elapsed_seconds"] == old
        if earlier:
            assert row["prior_rpe_age_minutes"] == (stamp-earlier[-1])/60
        else:
            assert pd.isna(row["prior_rpe_age_minutes"])
        past = sorted(t for t in hr_times if t < stamp)
        recent = [t for t in past if t >= stamp-60]
        old_times = [] if not earlier else sorted(t for t in hr_times if earlier[-1]-60 <= t < earlier[-1])
        def values(times):
            return [hr["cells"][column+str(hr_times[t])] for t in times]
        current_mean = statistics.fmean(values(recent))
        old_mean = statistics.fmean(values(old_times)) if old_times else np.nan
        expected = {"hr_last_before_report":values([past[-1]])[0],"hr_recent_60s_mean":current_mean,
            "hr_history_mean":statistics.fmean(values(past)),"hr_first_pre_report_mean":statistics.fmean(values([t for t in hr_times if t < 60])),
            "prior_report_hr_recent_mean":old_mean,"hr_recent_minus_prior_report_mean":current_mean-old_mean,
            "hr_recent_samples":len(recent),"hr_history_samples":len(past),"hr_last_elapsed_seconds":past[-1]}
        for name,value in expected.items():
            np.testing.assert_allclose(row[name],value,rtol=0,atol=1e-12,equal_nan=True)
        lineage = by_row[key]
        assert lineage["original_rpe_sheet"] == targets["original_sheet"] and lineage["original_hr_sheet"] == hr["original_sheet"]
        assert lineage["original_rpe_cell"] == tcell
        for field,times in (("strictly_preceding_hr_cells",past),("hr_recent_60s_cells",recent),("prior_report_hr_recent_cells",old_times)):
            assert lineage[field] == [column+str(hr_times[t]) for t in times]
        assert lineage["maximum_hr_elapsed_seconds"] == past[-1] < stamp == lineage["current_rpe_elapsed_seconds"]
    assert len(frame) == len(expected_keys) == len(checked_cells) == len(by_row) == 336
    fitting_frame,reserved_frame = frame[frame.source_partition.eq("fitting")],frame[frame.source_partition.eq("reserved")]
    assert (len(fitting_frame),fitting_frame.group_key.nunique(),len(reserved_frame),reserved_frame.group_key.nunique()) == (252,12,84,4)
    assert not set(fitting_frame.group_key)&set(reserved_frame.group_key)
    assert (fitting_frame.prior_rpe_points.notna().sum(),fitting_frame.second_prior_rpe_points.notna().sum()) == (168,84)
    assert not set(frame)&{"label","borg_native","current_rpe","rest_hr","age"}
    return {"version":1,"verification":"passed","verified_at":datetime.now(timezone.utc).isoformat(),
        "audit_code_sha256":digest(Path(__file__)),"source_preparation_code_sha256":digest(Path(prepared.__file__)),
        "source_provenance_sha256":digest(provenance_path),"original_report_verification_sha256":digest(prepared.AUDIT),
        "original_rpe_cells_independently_read_from_xlsx_xml":336,"all_pre_report_hr_features_independently_recomputed":True,
        "source_fitting_targets":252,"source_fitting_people":12,"source_reserved_targets":84,"source_reserved_people":4,
        "source_fitting_adjacent_pairs":168,"source_fitting_second_actual_priors":84,
        "original_outcome_points_preserved_separately":True,"source_person_split_independently_reproduced_before_eligibility":True,
        "all_sensor_timestamps_strictly_before_current_rpe":True,"cross_experiment_or_cross_condition_histories":False,
        "first_minute_hr_not_interpreted_as_rest":True,"source_target_conversion_or_pooling":False,
        "synthetic_rows":0,"imputed_sensor_points_or_targets":0,"new_native_targets":0,"model_fitting_started":False,
        "scope":"Independent raw XLSX XML reconstruction,without calling the preparation reader or feature builder.336original experiment2reported points,252/84responses by12/4people,168fitting adjacent pairs and84actual second priors. All causal HRfeature values,missing histories,original sourcecell coordinates,person namespaces and whole-person split verified. No source label conversion,extra nativecases,rest assumption,interpolation or across-condition/experiment histories."}


if __name__ == "__main__":
    report = validate()
    output = prepared.DOCS/"furukawa-pre-report-hr-input-verification.json"
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("verification","original_rpe_cells_independently_read_from_xlsx_xml","source_fitting_targets","source_reserved_targets","all_sensor_timestamps_strictly_before_current_rpe","model_fitting_started")}),flush=True)
