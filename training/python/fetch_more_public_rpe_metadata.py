"""Fetch only public metadata for four newly located actual-RPE candidates."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen

from public_sources import ROOT,digest

DIRECTORY = ROOT/"training/data/raw/fatigue-research/new-rpe-candidates-2026-10-27-v1"
SOURCES = {
    "hift":{"url":"https://api.figshare.com/v2/articles/25858906","id":25858906,"provider":"figshare"},
    "resistance":{"url":"https://zenodo.org/api/records/17259403","id":17259403,"provider":"zenodo"},
    "runners":{"url":"https://api.figshare.com/v2/articles/21779501","id":21779501,"provider":"figshare"},
    "motor_exercise":{"url":"https://api.figshare.com/v2/articles/24319813","id":24319813,"provider":"figshare"}}


def retrieve(item):
    key,source = item
    path = DIRECTORY/(key+"-metadata.json")
    try:
        if path.exists():
            metadata = json.loads(path.read_text(encoding="utf-8"))
        else:
            request = Request(source["url"],headers={"User-Agent":"MiSendero-public-data-research/1.0","Accept":"application/json"})
            with urlopen(request,timeout=45) as response:
                payload = response.read(8_000_001)
            if len(payload)>8_000_000:
                raise ValueError("Public metadata exceeded the bounded metadata request size")
            metadata = json.loads(payload)
            if str(metadata["id"]) != str(source["id"]):
                raise ValueError("Public repository returned a different dataset identity")
            path.write_text(json.dumps(metadata,indent=2,ensure_ascii=True)+"\n",encoding="utf-8")
        if str(metadata["id"]) != str(source["id"]):
            raise ValueError("Saved public dataset identity changed")
        fields = metadata["metadata"] if source["provider"] == "zenodo" else metadata
        files = metadata.get("files",[])
        info = {"key":key,"public_metadata_url":source["url"],"id":source["id"],"provider":source["provider"],
            "metadata_sha256":digest(path),"metadata_bytes":path.stat().st_size,"title":fields["title"],
            "license":fields.get("license"),"access_right":fields.get("access_right"),
            "files":[{"name":f.get("name",f.get("key")),"bytes":f.get("size"),
                "repository_checksum":f.get("computed_md5",f.get("checksum")),"public_download_url":f.get("download_url",f.get("links",{}).get("self"))}
                for f in files],"raw_data_downloaded":False,"model_fitting_started":False,"status":"metadata_verified"}
        return info
    except Exception as error:
        return {"key":key,"public_metadata_url":source["url"],"id":source["id"],"status":"retrieval_failed",
            "error_type":type(error).__name__,"error":str(error),"raw_data_downloaded":False,"model_fitting_started":False}


def main():
    DIRECTORY.mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(retrieve,SOURCES.items()))
    number = len(list(DIRECTORY.glob("metadata-attempt-*.json")))+1
    report = {"version":1,"code_sha256":digest(Path(__file__)),"retrieved_at":datetime.now(timezone.utc).isoformat(),
        "public_metadata_only":True,"synthetic_rows":0,"raw_data_downloaded":False,"model_fitting_started":False,"sources":results}
    path = DIRECTORY/f"metadata-attempt-{number}.json"
    path.write_text(json.dumps(report,indent=2,ensure_ascii=True)+"\n",encoding="utf-8")
    for result in results:
        print(json.dumps(result,ensure_ascii=True),flush=True)
    if any(r["status"] != "metadata_verified" for r in results):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
