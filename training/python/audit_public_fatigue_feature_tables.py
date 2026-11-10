"""Inspect original feature-table schemas without inventing Borg responses."""
import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from fetch_public_fatigue_feature_tables import DIRECTORY, FILES
from public_sources import ROOT, digest


def validate():
    snapshot = DIRECTORY/"feature-table-fetch-source-v1.py"
    current = Path(__file__).with_name("fetch_public_fatigue_feature_tables.py")
    if ast.dump(ast.parse(snapshot.read_text())) != ast.dump(ast.parse(current.read_text())):
        raise ValueError("Feature table fetcher differs from its recorded source beyond comments")
    sources = []
    for name, article, filename, size in FILES:
        folder = DIRECTORY/name
        metadata_path, receipt_path = folder/f"article-{article}.json", folder/"table-receipt.json"
        metadata, receipt = json.loads(metadata_path.read_text()), json.loads(receipt_path.read_text())
        entry = next(r for r in metadata["files"] if r["name"] == filename)
        path = folder/filename
        if (metadata["id"] != article or metadata["is_embargoed"] or metadata["license"]["name"] != "CC BY 4.0"
                or receipt["metadata_sha256"] != digest(metadata_path) or receipt["fetch_code_sha256"] != digest(snapshot)
                or receipt["sha256"] != digest(path) or path.stat().st_size != size
                or digest(path,"md5") != entry["computed_md5"] or len(entry["computed_md5"]) != 32):
            raise ValueError("Original public feature table metadata/checksum/code evidence changed")
        if name == "fourth-fatigue-v1":
            book = pd.ExcelFile(path,engine="openpyxl")
            if book.sheet_names != ["Sheet1"]:
                raise ValueError("Unexpected walking feature workbook structure")
            data = pd.read_excel(book,sheet_name="Sheet1")
            if data.shape != (2919,45) or data.columns[-1] != "labels" or data.iloc[:,0].tolist() != list(range(2919)):
                raise ValueError("Walking feature table/index changed")
            labels = data["labels"]
            expected = {1:953,2:771,3:732,4:463}
            columns = data.columns.tolist()
            primary = "https://doi.org/10.3390/s21196401"
            schema = "One sequential row index, 43 gait/lower-back/EMG features and one four-state class. The paper's measured HR and original numeric Borg are not columns of this published workbook."
        else:
            data = pd.read_csv(path,sep=r"\s+",header=None)
            if data.shape != (1240,64) or data.isna().any().any():
                raise ValueError("Biceps original feature table schema changed")
            labels, expected = data.iloc[:,-1], {1:460,2:338,3:442}
            columns = [f"feature_{i+1}" for i in range(63)]+["three_state_class"]
            primary = "https://doi.org/10.3390/s23229291"
            schema = "Headerless table of 63 per-repetition features and a three-state class. The original paper's Table 2 identifies the final three features as EMG frequencies, not numeric Borg. No HR, participant ID or response timestamp column is present."
        if labels.value_counts().sort_index().to_dict() != expected:
            raise ValueError("Published source class distribution changed")
        sources.append({"name":name,"article_id":article,"doi":metadata["doi"],"primary_protocol":primary,
            "file_sha256":digest(path),"metadata_sha256":digest(metadata_path),"receipt_sha256":digest(receipt_path),
            "publisher_md5_verified":entry["computed_md5"],"publisher_md5_padding_applied":False,
            "rows":len(data),"columns":columns,"source_class_counts":{str(k):v for k,v in expected.items()},
            "schema_interpretation":schema,"original_numeric_borg_column_available":False,
            "source_person_and_response_clock_available":False,"compatible_native_target_merge":False,
            "used_for_training":False,"new_native_borg_targets":0,
            "reason":"Class bands are not exact native Borg responses. Neither original response clocks nor verified common HR features are available in these published feature tables. Do not invent Borg values, participant IDs, response times or raw waveforms from row positions or summary features. A separate auxiliary representation would require a defensible shared feature pipeline."})
    return {"version":1,"verified_at":datetime.now(timezone.utc).isoformat(),"verification_code_sha256":digest(Path(__file__)),
        "fetch_source_snapshot_sha256":digest(snapshot),"fetch_current_code_semantics_equal_to_snapshot":True,
        "original_public_feature_tables":sources,"downloaded_public_data_bytes":sum(r[3] for r in FILES),
        "generated_or_synthetic_samples_downloaded_or_fitted":0,"original_native_training_cases":487,
        "original_native_test_cases":179,"new_native_borg_targets":0,"scope":"Only actual publisher data files were downloaded and inspected. No included models or scripts executed, no class-to-Borg conversion, and no fitting on these tables."}


if __name__ == "__main__":
    result = validate()
    path = ROOT/"docs/fatigue-80-2026-10-25/feature-table-eligibility.json"
    path.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"original_public_tables_verified":2,"native_target_merge":False,"new_native_borg_targets":0}))
