"""Retrieve the fixed public archive for original-annotation review only."""
import json
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request,urlopen

import fetch_more_public_rpe_metadata as source
from public_sources import digest


def fetch():
    directory = source.DIRECTORY
    resolution_path = directory/"resistance-concept-resolution.json"
    metadata_path = directory/"resistance-concept-response.json"
    resolution = json.loads(resolution_path.read_text())
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert resolution["concept_or_exact_record_relation_verified"]
    assert resolution["metadata_sha256"] == digest(metadata_path)
    assert str(metadata["id"]) == "17259404" and str(metadata["conceptrecid"]) == "17259403"
    assert metadata["metadata"]["license"]["id"] == "cc-by-4.0" and metadata["metadata"]["access_right"] == "open"
    assert len(metadata["files"]) == 1
    entry = metadata["files"][0]
    assert entry["key"] == "j-tom03/IMU-EMG-RPE-Estimation-v1.1.zip"
    assert entry["size"] == 47_902_219 and entry["checksum"] == "md5:580ac3dea08ec34dff9f74f51edbd624"
    url = entry["links"]["self"]
    assert urlparse(url).scheme == "https" and urlparse(url).hostname == "zenodo.org"
    target_directory = directory/"files/resistance"
    target_directory.mkdir(parents=True,exist_ok=True)
    target = target_directory/"original-repository-v1.1.zip"
    if not target.exists():
        temporary = target.with_suffix(".zip.part")
        request = Request(url,headers={"User-Agent":"MiSendero original public RPE annotation audit"})
        size = 0
        with urlopen(request,timeout=45) as response,temporary.open("wb") as stream:
            assert response.url.startswith("https://")
            for block in iter(lambda:response.read(1024*1024),b""):
                size += len(block)
                if size>entry["size"]:
                    raise ValueError("Public archive exceeded its fixed published byte count")
                stream.write(block)
        assert size == entry["size"] and digest(temporary,"md5") == entry["checksum"].split(":")[1]
        temporary.replace(target)
    assert target.stat().st_size == entry["size"] and digest(target,"md5") == entry["checksum"].split(":")[1]
    receipt = {"version":1,"code_sha256":digest(Path(__file__)),"retrieved_at":datetime.now(timezone.utc).isoformat(),
        "requested_concept_id":17259403,"fixed_version_record_id":17259404,"original_filename":entry["key"],
        "local_filename":str(target.relative_to(directory)).replace("\\","/"),"metadata_sha256":digest(metadata_path),
        "concept_resolution_sha256":digest(resolution_path),"bytes":target.stat().st_size,"repository_md5":digest(target,"md5"),
        "sha256":digest(target),"public_download_url":url,"license":"CC BY4.0","downloaded_code_executed":False,
        "pretrained_weights_loaded":False,"training_approved":False,"model_fitting_started":False,
        "policy":"Original raw manual RPE annotations must be distinguished from the article's SMOTE/jitter examples and learned EMG labels. Inspect archive text/spreadsheets only; execute no downloaded code and load no supplied model/pickle weights. Only direct actually reported RPE cells can become source targets after independent review."}
    output = directory/"resistance-archive-receipt.json"
    if output.exists():
        old = json.loads(output.read_text())
        assert all(old.get(k) == v for k,v in receipt.items() if k != "retrieved_at")
    else:
        output.write_text(json.dumps(receipt,indent=2,ensure_ascii=True)+"\n",encoding="utf-8")
    print(json.dumps({"original_archive":"verified","bytes":entry["size"],"fixed_public_record":17259404,
        "downloaded_code_executed":False,"pretrained_weights_loaded":False,"model_fitting_started":False}),flush=True)


if __name__ == "__main__":
    fetch()
