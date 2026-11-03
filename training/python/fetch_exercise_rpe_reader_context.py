"""Retrieve public analysis context and an isolated checksummed XLS reader."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import fetch_exercise_rpe_candidates as source
from public_sources import digest


def get(url,limit):
    request = urllib.request.Request(url,headers={"User-Agent":"MiSendero original RPE provenance review"})
    with urllib.request.urlopen(request,timeout=40) as response:
        content = response.read(limit+1)
        if not response.url.startswith("https://"):
            raise ValueError("Public reader/context retrieval left HTTPS")
    if len(content) > limit:
        raise ValueError("Public context exceeds explicit byte bound")
    return content


def fetch():
    inventory_path = source.DIRECTORY/"inventory.json"
    inventory = json.loads(inventory_path.read_text())
    if inventory["code_sha256"] != digest(Path(source.__file__)) or inventory["record"] != source.RECORD:
        raise ValueError("Frozen public source inventory changed")
    entry = next(r for r in inventory["files"] if r["key"] == "Data_analyses_v2.zip")
    if entry["size"] != 2229049 or entry["checksum"] != "md5:7f0b561fe19752861a7a39e819b43eb0":
        raise ValueError("Original public analysis context changed")
    target = source.DIRECTORY/"files"/entry["key"]
    if not target.exists():
        payload = get(entry["links"]["self"],entry["size"])
        temporary = target.with_suffix(".zip.part")
        temporary.write_bytes(payload)
        if len(payload) != entry["size"] or digest(temporary,"md5") != entry["checksum"].split(":")[1]:
            raise ValueError("Analysis context byte count/MD5 differs from repository")
        temporary.replace(target)
    if target.stat().st_size != entry["size"] or digest(target,"md5") != entry["checksum"].split(":")[1]:
        raise ValueError("Saved original analysis context changed")
    runtime = source.DIRECTORY/"isolated-xls-reader"
    runtime.mkdir(exist_ok=True)
    metadata_path = runtime/"xlrd-2.0.2-pypi.json"
    if not metadata_path.exists():
        data = get("https://pypi.org/pypi/xlrd/2.0.2/json",1_000_000)
        json.loads(data)
        metadata_path.write_bytes(data)
    metadata = json.loads(metadata_path.read_text())
    if metadata["info"]["name"] != "xlrd" or metadata["info"]["version"] != "2.0.2":
        raise ValueError("Expected fixed pure-Python XLS reader")
    wheels = [r for r in metadata["urls"] if r["packagetype"] == "bdist_wheel" and r["filename"].endswith("-none-any.whl")]
    if len(wheels) != 1 or wheels[0]["size"] > 500_000 or not wheels[0]["url"].startswith("https://files.pythonhosted.org/"):
        raise ValueError("Unexpected XLS reader artifact")
    wheel = wheels[0]
    wheel_path = runtime/wheel["filename"]
    if not wheel_path.exists():
        wheel_path.write_bytes(get(wheel["url"],wheel["size"]))
    if wheel_path.stat().st_size != wheel["size"] or digest(wheel_path) != wheel["digests"]["sha256"]:
        raise ValueError("XLS reader bytes differ from official PyPI SHA256")
    receipt = {"version":1,"code_sha256":digest(Path(__file__)),"source_inventory_sha256":digest(inventory_path),
        "analysis_context":{"filename":target.name,"bytes":target.stat().st_size,"repository_md5":digest(target,"md5"),"sha256":digest(target)},
        "isolated_xls_reader":{"filename":wheel_path.name,"relative_path":str(wheel_path.relative_to(source.DIRECTORY)).replace("\\","/"),
            "version":"2.0.2","bytes":wheel_path.stat().st_size,"published_sha256":wheel["digests"]["sha256"],
            "sha256":digest(wheel_path),"official_metadata_sha256":digest(metadata_path)},
        "training_environment_modified":False,"downloaded_study_code_executed":False,"used_for_model_fitting":False,
        "policy":"Reader wheel is isolated and checksum-verified; it will be imported only by the data-review process. Public study scripts are inspected as text, never executed. No imputed/generated study table is approved as an observed target source."}
    path = source.DIRECTORY/"reader-context-receipt.json"
    if path.exists() and json.loads(path.read_text()) != receipt:
        raise ValueError("Preserve frozen reader/context provenance")
    path.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(receipt,indent=2),flush=True)


if __name__ == "__main__":
    fetch()
