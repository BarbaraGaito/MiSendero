"""Retrieve selected CADENCE supplements through NLM's public cloud service.

Uses the documented2026 article-version listing and repository MD5 URLs,
without authentication, CAPTCHA handling, target conversion or model fitting.
"""
import hashlib
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from public_sources import ROOT, digest

DIRECTORY = ROOT/"training/data/raw/fatigue-research/cadence-cloud-v1"
BUCKET = "https://pmc-oa-opendata.s3.amazonaws.com/"
ARTICLES = ("PMC7877025", "PMC10688086")
NAMESPACE = {"s3":"http://s3.amazonaws.com/doc/2006-03-01/"}


def retrieve(url, path, maximum, expected_md5=None):
    if path.exists():
        if expected_md5 and digest(path, "md5") != expected_md5:
            raise ValueError("Frozen public cloud file differs from repositoryMD5")
        return path
    request = urllib.request.Request(url, headers={"User-Agent":"MiSendero public CADENCE data eligibility audit/1.0"})
    with urllib.request.urlopen(request, timeout=40) as response:
        data = response.read(maximum+1)
        if not response.url.startswith(BUCKET):
            raise ValueError("Repository retrieval left the documented public cloud")
    if len(data) > maximum:
        raise ValueError("Public cloud object exceeds bounded retrieval size")
    if expected_md5 and hashlib.md5(data).hexdigest() != expected_md5:
        raise ValueError("Downloaded original supplement fails repositoryMD5")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def fetch():
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    receipt_path = DIRECTORY/"receipt.json"
    if receipt_path.exists():
        previous = json.loads(receipt_path.read_text())
        if previous["code_sha256"] != digest(Path(__file__)) or any(digest(DIRECTORY/r["local_path"]) != r["sha256"] for r in previous["files"]):
            raise ValueError("Frozen cloud source snapshot/code changed")
        return previous
    files, versions = [], []
    readme = retrieve(BUCKET+"README.txt", DIRECTORY/"repository-README.txt", 100_000)
    files.append({"local_path":readme.name,"url":BUCKET+"README.txt","sha256":digest(readme),"bytes":readme.stat().st_size})
    for article in ARTICLES:
        listing_url = BUCKET+"?"+urllib.parse.urlencode({"list-type":2,"prefix":article+".","delimiter":"/","max-keys":20})
        listing = retrieve(listing_url, DIRECTORY/(article+"-versions.xml"), 100_000)
        root = ET.fromstring(listing.read_bytes())
        prefixes = [entry.text for entry in root.findall("s3:CommonPrefixes/s3:Prefix",NAMESPACE)]
        if not prefixes or len(prefixes) > 5 or any(not re.fullmatch(article+r"\.\d+/",p) for p in prefixes):
            raise ValueError("Inspect unexpected public CADENCE article-version inventory")
        files.append({"local_path":listing.name,"url":listing_url,"sha256":digest(listing),"bytes":listing.stat().st_size})
        for prefix in prefixes:
            version = prefix.rstrip("/")
            metadata_url = BUCKET+prefix+version+".json"
            metadata_path = retrieve(metadata_url, DIRECTORY/(version+".json"), 300_000)
            metadata = json.loads(metadata_path.read_text())
            license_code = re.sub(r"[^a-z0-9]","",str(metadata.get("license_code","")).lower())
            if license_code not in {"cc0","ccby"} or str(metadata.get("is_retracted","")).lower() not in {"false","no"}:
                raise ValueError("Unexpected source license or article retraction status")
            if metadata.get("pmcid") != article or "cadence" not in metadata.get("title","").lower():
                raise ValueError("Public source metadata identifies another article")
            files.append({"local_path":metadata_path.name,"url":metadata_url,"sha256":digest(metadata_path),"bytes":metadata_path.stat().st_size})
            requested = [metadata["xml_url"],metadata["text_url"]]
            requested += [url for url in metadata.get("media_urls",[]) if re.search(r"MOESM[12]_ESM\.(csv|xlsx)$",urllib.parse.urlparse(url).path,re.I)]
            if not 2 <= len(requested) <= 5:
                raise ValueError("Inspect unexpected number of requested data/dictionary objects")
            retrieved = []
            for url in requested:
                original_uri = url
                parsed = urllib.parse.urlparse(url)
                if parsed.scheme == "s3" and parsed.netloc == "pmc-oa-opendata":
                    url = BUCKET+parsed.path.lstrip("/")+("?"+parsed.query if parsed.query else "")
                    parsed = urllib.parse.urlparse(url)
                if not url.startswith(BUCKET+prefix):
                    raise ValueError("Source URL leaves the enumerated public article version")
                md5 = urllib.parse.parse_qs(parsed.query).get("md5",[None])[0]
                if not md5 or not re.fullmatch(r"[0-9a-f]{32}",md5):
                    raise ValueError("Repository object lacks its documentedMD5")
                name = Path(parsed.path).name
                path = retrieve(url, DIRECTORY/version/name, 2_000_000, md5)
                if name.lower().endswith(".csv") and (b"<html" in path.read_bytes()[:500].lower() or b"," not in path.read_bytes().splitlines()[0]):
                    raise ValueError("Original CSV was not returned")
                files.append({"local_path":path.relative_to(DIRECTORY).as_posix(),"url":url,"original_repository_uri":original_uri,"sha256":digest(path),
                              "bytes":path.stat().st_size,"repository_md5":md5,"repository_md5_verified":True})
                retrieved.append(name)
                print(f"Verified public cloud object:{version}/{name},{path.stat().st_size} bytes",flush=True)
            versions.append({"article":article,"version":metadata.get("version"),"doi":metadata.get("doi"),"title":metadata.get("title"),
                "license_code":metadata.get("license_code"),"is_manuscript":metadata.get("is_manuscript"),"objects_retrieved":retrieved,
                "available_media_names":[Path(urllib.parse.urlparse(url).path).name for url in metadata.get("media_urls",[])]})
    result = {"version":1,"retrieved_at":datetime.now(timezone.utc).isoformat(),"code_sha256":digest(Path(__file__)),
        "repository":"NIH NLM NCBI PMC Article Datasets on AWS", "documentation":"https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/",
        "versions":versions,"files":files,"training_merge_approved":False,"used_for_training":False,
        "synthetic_data_permitted":False,"source_instrument_conversion_permitted":False,
        "policy":"Public anonymous cloud retrieval through the official current NLM interface. Selected original CSV/dictionary and articleXML/TXT only; original repositoryMD5 verified. No source labels, cohorts, cadence/RPE scale or report timestamps are inferred from the metadata alone. No model fitting or source-generalization claim until cell/identity/time eligibility review."}
    receipt_path.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2),flush=True)
    return result


if __name__ == "__main__":
    fetch()
