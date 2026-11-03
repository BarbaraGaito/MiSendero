"""Retrieve the older-cohort dictionary explicitly listed in NLM metadata."""
import json
import urllib.parse
from pathlib import Path

import fetch_cadence_cloud as cloud
from public_sources import digest


def fetch():
    path = cloud.DIRECTORY/"PMC10688086.1.json"
    metadata = json.loads(path.read_text())
    name = "12966_2023_1543_MOESM3_ESM.xlsx"
    matches = [url for url in metadata["media_urls"] if Path(urllib.parse.urlparse(url).path).name == name]
    if len(matches) != 1:
        raise ValueError("Expected one original older-cohort data dictionary")
    uri = matches[0]
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme != "s3" or parsed.netloc != "pmc-oa-opendata" or not parsed.path.startswith("/PMC10688086.1/"):
        raise ValueError("Dictionary URI leaves the inspected public article version")
    url = cloud.BUCKET+parsed.path.lstrip("/")+"?"+parsed.query
    md5 = urllib.parse.parse_qs(parsed.query)["md5"][0]
    target = cloud.DIRECTORY/"PMC10688086.1"/name
    cloud.retrieve(url,target,300_000,md5)
    receipt = {"version":1,"code_sha256":digest(Path(__file__)),"article_metadata_sha256":digest(path),
        "url":url,"repository_uri":uri,"repository_md5":md5,"repository_md5_verified":True,
        "local_path":target.relative_to(cloud.DIRECTORY).as_posix(),"bytes":target.stat().st_size,"sha256":digest(target),
        "used_for_training":False}
    destination = cloud.DIRECTORY/"older-dictionary-receipt.json"
    if destination.exists() and json.loads(destination.read_text()) != receipt:
        raise ValueError("Preserve the frozen dictionary receipt before accepting changes")
    destination.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(receipt,indent=2))


if __name__ == "__main__":
    fetch()
