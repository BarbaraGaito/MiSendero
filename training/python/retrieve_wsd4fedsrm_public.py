"""Retrieve one explicitly public original ZIP; never execute archive contents."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import datetime,timezone
from pathlib import Path

from public_sources import ROOT,digest

DIRECTORY = ROOT/"training/data/raw/fatigue-research/wsd4fedsrm-8415066-v1"
API = "https://zenodo.org/api/records/8415066"
TITLE = "WSD4FEDSRM (Wearable sensor data for fatigue estimation during shoulder rotation movements)"
FILENAME = "WSD4FEDSRM.zip"
SIZE = 392734892
MD5 = "1e5d9db1a0e3a53a4ef27bcd4464b60a"
SOURCE_URL = "https://zenodo.org/api/records/8415066/files/WSD4FEDSRM.zip/content"
HEADERS = {"User-Agent":"MiSendero-public-original-RPE-research/1.0"}


def fetch(metadata_only=False):
    DIRECTORY.mkdir(exist_ok=True)
    lock = DIRECTORY/"retrieval.lock"
    if lock.exists():
        raise ValueError("A retrieval lock exists; inspect the actual process before any second run")
    lock.write_text(datetime.now(timezone.utc).isoformat()+"\n",encoding="utf-8")
    try:
        request = urllib.request.Request(API,headers=HEADERS)
        with urllib.request.urlopen(request,timeout=30) as response:
            if response.status != 200:
                raise ValueError("The public record metadata did not return200")
            payload = response.read(2000001)
        if len(payload)>2000000:
            raise ValueError("Public record metadata exceeded the fixed2MBbound")
        record = json.loads(payload)
        metadata,files = record["metadata"],record["files"]
        if (record["id"] != 8415066 or metadata["title"] != TITLE or metadata["access_right"] != "open"
            or metadata["license"]["id"] != "cc-by-4.0" or len(files) != 1):
            raise ValueError("Original public source identity/access/license changed")
        source = files[0]
        if source["key"] != FILENAME or source["size"] != SIZE or source["checksum"] != "md5:"+MD5 or source["links"]["self"] != SOURCE_URL:
            raise ValueError("Original repository ZIPsize/checksum/URL changed")
        metadata_path = DIRECTORY/"metadata.json"
        if metadata_path.exists():
            original = json.loads(metadata_path.read_text())
            if (original["id"],original["metadata"]["title"],original["metadata"]["access_right"],original["metadata"]["license"],original["files"]) != (
                record["id"],metadata["title"],metadata["access_right"],metadata["license"],files):
                raise ValueError("Previously saved public source metadata identity changed")
        else:
            metadata_path.write_bytes(payload)
        print(json.dumps({"source":API,"access":"open","license":"CC BY4.0","original_filename":FILENAME,"bytes":SIZE,"official_md5":MD5,"metadata_sha256":digest(metadata_path)}),flush=True)
        if metadata_only:
            return
        final = DIRECTORY/FILENAME
        partial = DIRECTORY/(FILENAME+".part")
        start = time.monotonic()
        if not final.exists():
            have = partial.stat().st_size if partial.exists() else 0
            if have>SIZE:
                raise ValueError("Partial original ZIPexceeds its fixed officialsize")
            if have<SIZE:
                headers = {**HEADERS,**({"Range":f"bytes={have}-"} if have else {})}
                with urllib.request.urlopen(urllib.request.Request(SOURCE_URL,headers=headers),timeout=60) as response:
                    if have:
                        expected = f"bytes {have}-{SIZE-1}/{SIZE}"
                        if response.status != 206 or response.headers.get("Content-Range") != expected:
                            raise ValueError("The server did not confirm the exact verified originalZIPresume range")
                    elif response.status != 200:
                        raise ValueError("The original public ZIP did not return200")
                    if response.headers.get("Content-Length") and int(response.headers["Content-Length"]) != SIZE-have:
                        raise ValueError("The public ZIPresponse length differs from fixed originalsize")
                    with partial.open("ab" if have else "wb") as output:
                        next_progress = have+8*1024*1024
                        while block := response.read(1024*1024):
                            if have+len(block)>SIZE:
                                raise ValueError("The originalZIPresponse exceeds its officialsize")
                            output.write(block)
                            have += len(block)
                            if have>=next_progress:
                                print(json.dumps({"downloaded_bytes":have,"expected_bytes":SIZE,"percent":round(100*have/SIZE,2),"elapsed_seconds":round(time.monotonic()-start,1)}),flush=True)
                                next_progress = have+8*1024*1024
            if partial.stat().st_size != SIZE or digest(partial,"md5") != MD5:
                raise ValueError("Original ZIPsize/official MD5verification failed; preserve partial bytes")
            partial.rename(final)
        if final.stat().st_size != SIZE or digest(final,"md5") != MD5:
            raise ValueError("Previously complete original ZIPchanged")
        receipt = {"version":1,"retrieved_at":datetime.now(timezone.utc).isoformat(),"retrieval_code_sha256":digest(Path(__file__)),
            "record_id":8415066,"record_url":"https://zenodo.org/records/8415066","record_metadata_sha256":digest(metadata_path),
            "source_url":SOURCE_URL,"official_original_filename":FILENAME,"local_filename":FILENAME,"license":"CC BY4.0","access":"open",
            "bytes":SIZE,"official_md5":MD5,"verified_md5":digest(final,"md5"),"sha256":digest(final),
            "original_archive_complete_and_verified":True,"included_code_executed":False,"supplied_models_or_weights_loaded":False,
            "model_fitting_started":False}
        path = DIRECTORY/"receipt.json"
        if path.exists():
            previous = json.loads(path.read_text())
            if any(previous[k] != v for k,v in receipt.items() if k != "retrieved_at"):
                raise ValueError("Saved original ZIPreceipt changed")
        else:
            path.write_text(json.dumps(receipt,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        print(json.dumps({"retrieval":"complete","original_bytes_verified":SIZE,"official_md5_verified":True,"sha256":receipt["sha256"],"included_code_executed":False,"model_fitting_started":False}),flush=True)
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-only",action="store_true")
    fetch(parser.parse_args().metadata_only)
