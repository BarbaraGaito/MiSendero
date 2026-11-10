"""Bounded retrieval of original public longitudinal exercise data for review."""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from fetch_fatigue_extra import download
from public_sources import ROOT, digest

DATASET = "kcff3z6wjb"
PAGE = f"https://data.mendeley.com/datasets/{DATASET}/1"
DIRECTORY = ROOT/"training/data/raw/fatigue-research/light-exercise-v1"


def metadata(name, url):
    path = DIRECTORY/name
    if not path.exists():
        request = urllib.request.Request(url,headers={"User-Agent":"MiSendero public dataset eligibility review",
            "Accept":"application/vnd.mendeley-public-dataset.1+json" if name.endswith(".json") else "text/html"})
        with urllib.request.urlopen(request,timeout=40) as response:
            payload = response.read(2_000_001)
            if not response.url.startswith("https://"):
                raise ValueError("Public metadata left HTTPS")
        if len(payload) > 2_000_000:
            raise ValueError("Metadata exceeds 2MB bound")
        if name.endswith(".json"):
            json.loads(payload)
        path.write_bytes(payload)
    return {"path":name,"url":url,"bytes":path.stat().st_size,"sha256":digest(path)}


def inventory():
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    entries = [metadata("page.html",PAGE),metadata("folders.json",f"https://data.mendeley.com/public-api/datasets/{DATASET}/folders/1")]
    html = (DIRECTORY/"page.html").read_text(encoding="utf-8")
    state,_ = json.JSONDecoder().raw_decode(html.split("window.INITIAL_STATE = ",1)[1])
    source = state["dataset"]["snapshot"]
    if source["version"] != 1 or source["is_confidential"] or source["licence"]["short_name"] != "CC BY 4.0":
        raise ValueError("Expected public version1 CC BY4.0 source")
    folders = json.loads((DIRECTORY/"folders.json").read_text())
    if not isinstance(folders,list) or len(folders) > 20:
        raise ValueError("Unexpected folder inventory")
    listed = []
    for folder in [{"id":"root","name":"root"}]+folders:
        folder_id = folder["id"]
        if not re.fullmatch(r"[A-Za-z0-9-]+",folder_id):
            raise ValueError("Unexpected source folder identifier")
        url = f"https://data.mendeley.com/public-api/datasets/{DATASET}/files?"+urllib.parse.urlencode(
            {"folder_id":folder_id,"version":1,"$start":0,"$limit":1000})
        entry = metadata(f"files-{folder_id}.json",url)
        entries.append(entry)
        values = json.loads((DIRECTORY/entry["path"]).read_text())
        if not isinstance(values,list) or len(values) > 300:
            raise ValueError("Unexpected source file count")
        listed.extend({"id":item["id"],"filename":item["filename"],"folder_id":folder_id,
                       "folder_name":folder["name"],"content_details":item["content_details"]} for item in values)
    if len({row["id"] for row in listed}) != len(listed):
        raise ValueError("Duplicate original file identities")
    result = {"version":1,"source":PAGE,"doi":source["doi"],"title":source["name"],"license":source["licence"],
        "metadata":entries,"files":listed,"metadata_only":True,"used_for_training":False,"code_sha256":digest(Path(__file__)),
        "policy":"Inspect original measured responses, scale, missing-value definitions, participant identities and timing before training. No invented times, repeated-cell inflation, synthetic rows or source/native label conversion."}
    path = DIRECTORY/"inventory.json"
    if path.exists() and json.loads(path.read_text()) != result:
        raise ValueError("Preserve the frozen inventory before changing retrieval")
    path.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"title":result["title"],"doi":result["doi"],"files":[{"filename":r["filename"],
        "bytes":r["content_details"]["size"],"folder":r["folder_name"]} for r in listed]},indent=2),flush=True)
    return result


def fetch_names(names):
    record = inventory()
    files = []
    for name in names:
        matches = [row for row in record["files"] if row["filename"] == name]
        if len(matches) != 1 or Path(name).name != name or "/" in name or "\\" in name or Path(name).suffix.lower() not in {".csv",".txt",".xlsx",".xls",".sav",".pdf",".docx",".md"}:
            raise ValueError("Explicit unambiguous original data/document name required")
        entry = matches[0]
        details = entry["content_details"]
        if not 0 < details["size"] <= 20_000_000 or not re.fullmatch(r"[0-9a-f]{64}",details["sha256_hash"]):
            raise ValueError("File exceeds20MB bound or lacks publisher SHA256")
        if not details["download_url"].startswith(f"https://data.mendeley.com/public-files/datasets/{DATASET}/"):
            raise ValueError("Download leaves the inspected public dataset")
        path = download(details["download_url"],DIRECTORY/"files"/name,maximum_bytes=details["size"],
                        expected_bytes=details["size"],sha256=details["sha256_hash"])
        if path.stat().st_size != details["size"] or digest(path) != details["sha256_hash"]:
            raise ValueError("Original measured data bytes changed")
        files.append({"filename":name,"source_file_id":entry["id"],"url":details["download_url"],"bytes":details["size"],
                      "published_sha256":details["sha256_hash"],"sha256":digest(path)})
    result = {"version":1,"inventory_sha256":digest(DIRECTORY/"inventory.json"),"code_sha256":digest(Path(__file__)),
              "files":files,"publisher_hashes_verified":True,"used_for_training":False,"native_target_merge_approved":False,
              "synthetic_rows_permitted":False}
    path = DIRECTORY/"files-receipt.json"
    if path.exists() and json.loads(path.read_text()) != result:
        raise ValueError("Preserve the frozen file receipt")
    path.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2),flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--names",nargs="+")
    args = parser.parse_args()
    fetch_names(args.names) if args.names else inventory()
