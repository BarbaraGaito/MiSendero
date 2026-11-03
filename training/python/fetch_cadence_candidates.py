"""Retrieve public CADENCE analytic tables for eligibility review only.

No target scale conversion, invented clocks, source fitting or execution of
downloaded code. Publisher checksums are not assumed when none are supplied.
"""
import json
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from public_sources import ROOT, digest

DIRECTORY = ROOT/"training/data/raw/fatigue-research/cadence-candidates-80-v1"
SOURCE = "https://pmc.ncbi.nlm.nih.gov/articles/PMC7877025/"
URLS = {"adult-relative.csv": "https://pmc.ncbi.nlm.nih.gov/articles/instance/7877025/bin/12966_2021_1096_MOESM1_ESM.csv",
        "adult-dictionary.xlsx": "https://pmc.ncbi.nlm.nih.gov/articles/instance/7877025/bin/12966_2021_1096_MOESM2_ESM.xlsx",
        "adult-protocol.html": SOURCE}


def fetch():
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    receipt_path = DIRECTORY/"receipt.json"
    previous = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    if previous and previous["all_requested_files_complete"]:
        if previous["code_sha256"] != digest(Path(__file__)) or any(digest(DIRECTORY/r["filename"]) != r["sha256"] for r in previous["files"]):
            raise ValueError("Frozen CADENCE source or retrieval code changed")
        return previous
    files, unavailable = [], []
    previous_files = {r["filename"]:r for r in previous["files"]} if previous else {}
    for filename, url in URLS.items():
        path = DIRECTORY/filename
        if filename in previous_files and path.exists() and digest(path) == previous_files[filename]["sha256"]:
            files.append(previous_files[filename])
            continue
        try:
            request = urllib.request.Request(url, headers={"User-Agent":"MiSendero public dataset eligibility review/1.0"})
            with urllib.request.urlopen(request, timeout=40) as response:
                payload = response.read(1_000_001)
                effective_url = response.url
                content_type = response.headers.get("Content-Type", "")
                etag = response.headers.get("ETag")
                modified = response.headers.get("Last-Modified")
            if len(payload) > 1_000_000 or not effective_url.startswith("https://"):
                raise ValueError("Source response exceeds1MB or leaves HTTPS")
            if filename.endswith(".csv"):
                beginning = payload[:500].lower()
                if b"<html" in beginning or b"<!doctype" in beginning or b"captcha" in beginning:
                    raise ValueError("HTML/browser challenge returned instead of an original CSV; not data")
                if b"," not in payload.splitlines()[0]:
                    raise ValueError("Unexpected original CSV delimiter/header")
            elif filename.endswith(".xlsx"):
                import io
                if not payload.startswith(b"PK"):
                    raise ValueError("Original XLSX was not returned; no challenge bypass attempted")
                with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                    if "xl/workbook.xml" not in archive.namelist():
                        raise ValueError("Not an original spreadsheet data dictionary")
            elif b"CADENCE" not in payload or b"01096" not in payload or b"Creative Commons" not in payload:
                raise ValueError("Original article/license text was not returned")
            path.write_bytes(payload)
            files.append({"filename":filename,"url":url,"effective_url":effective_url,"bytes":len(payload),"sha256":digest(path),
                "http_content_type":content_type,"http_etag":etag,"http_last_modified":modified,"publisher_checksum_provided":False})
            print(f"Retrieved original public candidate:{filename},{len(payload)} bytes",flush=True)
        except (OSError, ValueError) as error:
            unavailable.append({"filename":filename,"url":url,"reason":str(error)})
            print(f"Candidate retrieval unavailable:{filename}:{error}",flush=True)
    result = {"version":1,"source":SOURCE,"doi":"10.1186/s12966-021-01096-w", "retrieved_at":datetime.now(timezone.utc).isoformat(),
        "code_sha256":digest(Path(__file__)),"files":files,"unavailable":unavailable,"all_requested_files_complete":len(files)==len(URLS),
        "used_for_training":False,"training_merge_approved":False,"scale_conversion_approved":False,
        "policy":"Public original analytical data and dictionary only. Verify participant identifiers, original RPE cells, temporal order, aggregation and instrument before any fitting. Borg6-20 is not relabeled as CR10. HTTP metadata/localSHA256 pin the retrieved snapshot; no absent publisher checksum is invented. No CAPTCHA, login, embargo or data-request restriction is bypassed."}
    receipt_path.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2),flush=True)
    return result


if __name__ == "__main__":
    fetch()
