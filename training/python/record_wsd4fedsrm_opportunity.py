"""Link verified public shoulder-rotation originals without claiming new fits."""
import hashlib
import json
from pathlib import Path

from public_sources import digest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT/"docs/fatigue-80-2026-10-25"
RAW = ROOT/"training/data/raw/fatigue-research/wsd4fedsrm-8415066-v1"
archive,receipt_path,metadata_path = RAW/"WSD4FEDSRM.zip",RAW/"receipt.json",RAW/"metadata.json"
receipt,metadata = json.loads(receipt_path.read_text()),json.loads(metadata_path.read_text())
proof_path = DOCS/"wsd4fedsrm-original-inspection.json"
proof = json.loads(proof_path.read_text())
assert receipt["record_metadata_sha256"] == digest(metadata_path)
assert receipt["retrieval_code_sha256"] == digest(Path(__file__).with_name("retrieve_wsd4fedsrm_public.py"))
assert receipt["original_archive_complete_and_verified"] and receipt["record_id"] == metadata["id"] == 8415066
assert receipt["access"] == metadata["metadata"]["access_right"] == "open"
assert metadata["metadata"]["license"]["id"] == "cc-by-4.0"
original = next(row for row in metadata["files"] if row["key"] == "WSD4FEDSRM.zip")
assert original["size"] == receipt["bytes"] == archive.stat().st_size == 392734892
assert original["checksum"] == "md5:"+receipt["official_md5"] == "md5:1e5d9db1a0e3a53a4ef27bcd4464b60a"
with archive.open("rb") as stream:
    assert hashlib.file_digest(stream,"md5").hexdigest() == receipt["verified_md5"] == receipt["official_md5"]
assert digest(archive) == receipt["sha256"] == proof["original_archive_sha256"]
assert proof["inspection"] == "complete" and proof["original_receipt_sha256"] == digest(receipt_path)
assert proof["inspection_code_sha256"] == digest(Path(__file__).with_name("inspect_wsd4fedsrm_originals.py"))
assert proof["official_original_size_and_md5_verified"] and proof["archive_file_count"] == 8375
assert proof["sensor_csvs_read"] == 0 and not proof["sensor_annotation_temporal_join_verified"]
assert not any(proof[name] for name in ("native_target_merge","participant_partition_created","model_fitting_started",
    "included_code_executed","supplied_models_or_weights_loaded"))
annotation, = proof["annotation_files"]
counts = annotation["counts"]
assert annotation["original_people"] == 34 and annotation["schema"]["original_data_rows"] == 204
assert counts["original_nonempty_borg_cells"] == 1719 and annotation["known_distinct_timed_report_clocks"] == 1311
assert counts["before_task_in_documented_instrument"] == counts["terminal_in_documented_instrument"] == 204
assert counts["timed_ordered_pairs"] == 1107 and counts["timed_targets_with_two_actual_timed_priors"] == 904
review = DOCS/"next-public-momentary-rpe-source-review.md"
status_path = DOCS/"current-research-status.json"
status = json.loads(status_path.read_text())
assert status["completed_studies"] in (48,49) and status["goal_status"] == "active"
status["additional_public_candidate_inspections"][proof_path.name] = digest(proof_path)
status["wsd4fedsrm_original_opportunity"] = {"public_record":"https://zenodo.org/records/8415066",
    "primary_article":"https://www.nature.com/articles/s41597-024-03254-8","license":"CC BY4.0",
    "source_directory":RAW.name,"receipt_sha256":digest(receipt_path),"inspection":proof_path.name,
    "review":review.name,"review_sha256":digest(review),"original_people":34,"original_task_rows":204,
    "original_nonempty_borg_cells":1719,"known_clocked_original_reports":1311,
    "within_task_timed_pairs":1107,"timed_targets_with_two_actual_timed_priors":904,
    "before_task_cells_kept_separate":204,"terminal_cells_kept_separate":204,
    "original_outcome":"Borg6-20_separate_from_native0-10","participant_partition_created":False,
    "sensor_annotation_temporal_join_verified":False,"adapter_prepared":False,"model_fitting_started":False,
    "native_target_merge":False,"synthetic_rows":0}
status["other_new_public_candidates"]["shoulder_rotations"] = {"public_record":"https://zenodo.org/records/8415066",
    "status":"OriginalZIPchecksumverified and smallBorgCSVinspected:1311explicit-clock reports/34people,1107within-taskpairs. No split,adapter,sensor join or fits; original6-20outcome separate. Independent protocol/cell/time audit required before preparation.",
    "model_fitting_started":False,"inspection":proof_path.name}
for field in ("additional_scoped_verifications","additional_data_audits","additional_public_candidate_inspections"):
    assert all(digest(DOCS/name) == value for name,value in status[field].items())
status_path.write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")
print(json.dumps({"original_archive_integrity":"passed","known_clocked_original_reports":1311,
    "source_people":34,"within_task_timed_pairs":1107,"new_native_training_targets":0,
    "adapter_prepared":False,"model_fitting_started":False}),flush=True)
