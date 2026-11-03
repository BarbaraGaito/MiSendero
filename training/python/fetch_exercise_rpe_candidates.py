"""Bounded original public repository retrieval; never execute downloaded code."""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from public_sources import ROOT, digest

RECORD = 19387250
API = f"https://zenodo.org/api/records/{RECORD}"
DIRECTORY = ROOT/"training/data/raw/fatigue-research/fessler-exercise-rpe-v1"
PAPER = "https://bpspsychub.onlinelibrary.wiley.com/doi/10.1111/bjhp.70097"


def inventory():
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    path = DIRECTORY/"metadata.json"
    if not path.exists():
        request = urllib.request.Request(API,headers={"User-Agent":"MiSendero public RPE dataset eligibility review","Accept":"application/json"})
        with urllib.request.urlopen(request,timeout=40) as response:
            payload = response.read(2_000_001)
            if not response.url.startswith("https://"):
                raise ValueError("Public metadata left HTTPS")
        if len(payload) > 2_000_000:
            raise ValueError("Public metadata exceeds2MB bound")
        data = json.loads(payload)
        if int(data["id"]) != RECORD:
            raise ValueError("Repository returned a different record/version")
        path.write_bytes(payload)
    data = json.loads(path.read_text(encoding="utf-8"))
    metadata = data["metadata"]
    if int(data["id"]) != RECORD or metadata.get("access_right") != "open":
        raise ValueError("Only the identified openly available public record is eligible for review")
    files = data.get("files",[])
    if not 0 < len(files) <= 100 or len({f["key"] for f in files}) != len(files):
        raise ValueError("Unexpected or ambiguous public file inventory")
    result = {"version":1,"record":RECORD,"record_url":f"https://zenodo.org/records/{RECORD}","metadata_url":API,
        "metadata_sha256":digest(path),"code_sha256":digest(Path(__file__)),"paper":PAPER,"title":metadata["title"],
        "license":metadata.get("license"),"files":files,"metadata_only":True,"used_for_training":False,
        "original_nonimputed_targets_verified":False,"training_approved":False,
        "policy":"Paper reports multiple imputation for analyses. Only original actually observed cells may become targets or prior reports; never use imputed outcomes, standardized imputed tables or generated datasets. Downloaded scripts are review text only and are never executed. Verify instruments, identities, timing and license before fitting."}
    output = DIRECTORY/"inventory.json"
    if output.exists() and json.loads(output.read_text()) != result:
        raise ValueError("Preserve frozen repository inventory before accepting changes")
    output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"title":result["title"],"license":result["license"],"files":[{
        "filename":f["key"],"bytes":f["size"],"checksum":f["checksum"],"download":f["links"].get("self")} for f in files]},indent=2),flush=True)
    return result


def fetch_names(names):
    record = inventory()
    outputs = []
    for name in names:
        matches = [entry for entry in record["files"] if entry["key"] == name]
        if len(matches) != 1 or Path(name).name != name or "/" in name or "\\" in name or Path(name).suffix.lower() not in {
            ".csv",".tsv",".xlsx",".txt",".md",".json",".r",".rds",".rdata",".sav",".pdf",".docx",".zip"}:
            raise ValueError("Explicit unambiguous original data/document filename required")
        entry = matches[0]
        maximum = 100_000_000 if name.lower().endswith(".zip") else 20_000_000
        if not 0 < entry["size"] <= maximum or not re.fullmatch(r"md5:[0-9a-f]{32}",entry["checksum"]):
            raise ValueError("File exceeds the explicit retrieval bound or lacks repository MD5")
        url = entry["links"]["self"]
        if urllib.parse.urlparse(url).scheme != "https" or urllib.parse.urlparse(url).hostname != "zenodo.org":
            raise ValueError("File is outside the inspected public repository")
        target = DIRECTORY/"files"/name
        target.parent.mkdir(exist_ok=True)
        expected_md5 = entry["checksum"].split(":",1)[1]
        if target.exists():
            if target.stat().st_size != entry["size"] or digest(target,"md5") != expected_md5:
                raise ValueError("Previously saved original bytes differ from repository checksum")
        else:
            temporary = target.with_suffix(target.suffix+".part")
            request = urllib.request.Request(url,headers={"User-Agent":"MiSendero public RPE data provenance review"})
            size = 0
            with urllib.request.urlopen(request,timeout=40) as response,temporary.open("wb") as stream:
                if not response.url.startswith("https://"):
                    raise ValueError("Public file left HTTPS")
                for block in iter(lambda:response.read(1024*1024),b""):
                    size += len(block)
                    if size > entry["size"]:
                        raise ValueError("Public file exceeded its published byte count")
                    stream.write(block)
            if size != entry["size"] or digest(temporary,"md5") != expected_md5:
                raise ValueError("Downloaded bytes do not match the repository size/MD5")
            temporary.replace(target)
        outputs.append({"filename":name,"url":url,"bytes":target.stat().st_size,"repository_md5":expected_md5,"sha256":digest(target)})
    receipt = {"version":1,"inventory_sha256":digest(DIRECTORY/"inventory.json"),"code_sha256":digest(Path(__file__)),
        "retrieved_at":datetime.now(timezone.utc).isoformat(),"files":outputs,"repository_checksums_verified":True,
        "downloaded_code_executed":False,"used_for_training":False,"original_nonimputed_targets_verified":False}
    path = DIRECTORY/"files-receipt.json"
    if path.exists() and any(json.loads(path.read_text()).get(k) != v for k,v in receipt.items() if k != "retrieved_at"):
        raise ValueError("Preserve frozen original file receipt")
    if not path.exists():
        path.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(receipt,indent=2),flush=True)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--names",nargs="+")
    args = parser.parse_args()
    fetch_names(args.names) if args.names else inventory()
