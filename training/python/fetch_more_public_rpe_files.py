"""Retrieve bounded original public workbooks and resolve one concept DOI."""
from __future__ import annotations

import json
import re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request,urlopen

import fetch_more_public_rpe_metadata as metadata_source
from public_sources import digest

DIRECTORY = metadata_source.DIRECTORY
EXPECTED = {"hift":25858906,"runners":21779501,"motor_exercise":24319813}


def get(url,maximum):
    request = Request(url,headers={"User-Agent":"MiSendero public original-RPE provenance review"})
    with urlopen(request,timeout=45) as response:
        payload = response.read(maximum+1)
        if urlparse(response.url).scheme != "https":
            raise ValueError("Public repository retrieval left HTTPS")
    if len(payload)>maximum:
        raise ValueError("Public response exceeded explicit retrieval bound")
    return payload


def fetch():
    receipts = []
    for alias,identifier in EXPECTED.items():
        metadata_path = DIRECTORY/(alias+"-metadata.json")
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        if data["id"] != identifier or data["license"]["name"] not in ("CC BY 4.0","CC0"):
            raise ValueError("Inspected public dataset identity/license changed")
        target_directory = DIRECTORY/"files"/alias
        target_directory.mkdir(parents=True,exist_ok=True)
        for entry in data["files"]:
            name = entry["name"]
            if (Path(name).name != name or re.search(r'[\\/:\r\n]',name) or Path(name).suffix.lower() not in (".xlsx",".docx")
                or not 0 < entry["size"] <= 5_000_000 or not re.fullmatch(r"[a-f0-9]{32}",entry["computed_md5"])):
                raise ValueError("Only bounded unambiguous original workbook/context files may be retrieved")
            url = entry["download_url"]
            if urlparse(url).scheme != "https" or urlparse(url).hostname != "ndownloader.figshare.com":
                raise ValueError("Original file is outside the inspected public Figshare host")
            target = target_directory/name
            if target.parent.resolve() != target_directory.resolve():
                raise ValueError("Original filename escapes its dedicated workspace folder")
            if not target.exists():
                temporary = target.with_suffix(target.suffix+".part")
                temporary.write_bytes(get(url,entry["size"]))
                if temporary.stat().st_size != entry["size"] or digest(temporary,"md5") != entry["computed_md5"]:
                    raise ValueError("Original public file bytes differ from repository size/MD5")
                temporary.replace(target)
            if target.stat().st_size != entry["size"] or digest(target,"md5") != entry["computed_md5"]:
                raise ValueError("Saved original public workbook changed")
            receipts.append({"source":alias,"article_id":identifier,"metadata_sha256":digest(metadata_path),
                "filename":name,"bytes":target.stat().st_size,"repository_md5":entry["computed_md5"],
                "sha256":digest(target),"public_download_url":url,"license":data["license"]["name"]})
            print(json.dumps({"source":alias,"filename":name,"original_bytes_verified":True,"bytes":entry["size"]}),flush=True)
    report = {"version":1,"code_sha256":digest(Path(__file__)),"verified_at":datetime.now(timezone.utc).isoformat(),
        "files":receipts,"repository_checksums_verified":True,"downloaded_study_code_executed":False,
        "model_fitting_started":False,"original_individual_target_eligibility_verified":False,"synthetic_rows":0}
    receipt_path = DIRECTORY/"original-files-receipt.json"
    if receipt_path.exists():
        old = json.loads(receipt_path.read_text())
        if any(old.get(k) != v for k,v in report.items() if k != "verified_at"):
            raise ValueError("Preserve the frozen public original-file receipt")
    else:
        receipt_path.write_text(json.dumps(report,indent=2,ensure_ascii=True)+"\n",encoding="utf-8")
    response_path = DIRECTORY/"resistance-concept-response.json"
    if not response_path.exists():
        payload = get("https://zenodo.org/api/records/17259403",8_000_000)
        json.loads(payload)
        response_path.write_bytes(payload)
    response = json.loads(response_path.read_text(encoding="utf-8"))
    concept = response.get("conceptrecid")
    verified_relation = str(response["id"]) == "17259403" or str(concept) == "17259403"
    resolution = {"version":1,"code_sha256":digest(Path(__file__)),"requested_public_record":17259403,
        "returned_record_id":response["id"],"returned_concept_id":concept,"metadata_sha256":digest(response_path),
        "concept_or_exact_record_relation_verified":verified_relation,"title":response["metadata"]["title"],
        "license":response["metadata"].get("license"),"access_right":response["metadata"].get("access_right"),
        "files":[{"name":f["key"],"bytes":f["size"],"checksum":f["checksum"]} for f in response.get("files",[])],
        "resistance_raw_data_downloaded":False,"model_fitting_started":False,"training_approved":False}
    path = DIRECTORY/"resistance-concept-resolution.json"
    if path.exists() and json.loads(path.read_text()) != resolution:
        raise ValueError("Preserve the frozen public concept/version resolution")
    path.write_text(json.dumps(resolution,indent=2,ensure_ascii=True)+"\n",encoding="utf-8")
    print(json.dumps(resolution,ensure_ascii=True),flush=True)
    return report


if __name__ == "__main__":
    fetch()
