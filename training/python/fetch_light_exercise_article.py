"""Retrieve one public university article candidate, without assuming a data link."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from public_sources import ROOT, digest

DIRECTORY = ROOT/"training/data/raw/fatigue-research/light-exercise-article-v1"
URL = "https://repositorio.uam.es/bitstreams/861e2496-6d06-4b2d-9d2f-a05e2970e103/download"
MAXIMUM_BYTES = 5_000_000


def fetch():
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    path = DIRECTORY/"article-candidate.pdf"
    result = {"version":1,"retrieved_at":datetime.now(timezone.utc).isoformat(),"code_sha256":digest(Path(__file__)),
        "url":URL,"candidate_article_doi":"10.1016/j.ctcp.2024.101880","dataset_doi":"10.17632/kcff3z6wjb.1",
        "dataset_to_article_link_confirmed":False,"training_approved":False,
        "reason":"Author,16-week protocol and exercise-group size suggest a possible relationship. This is a documentation candidate, not a proven mapping of the source workbook."}
    try:
        if not path.exists():
            request = urllib.request.Request(URL,headers={"User-Agent":"MiSendero public dataset documentation review"})
            with urllib.request.urlopen(request,timeout=40) as response:
                body = response.read(MAXIMUM_BYTES+1)
                if not response.url.startswith("https://"):
                    raise ValueError("Public article left HTTPS")
                result["resolved_url"] = response.url
            if len(body) > MAXIMUM_BYTES or not body.startswith(b"%PDF-"):
                raise ValueError("Response is not a bounded public PDF; do not parse or treat it as data")
            path.write_bytes(body)
        result.update(status="public_pdf_retrieved",bytes=path.stat().st_size,sha256=digest(path),publisher_checksum_available=False)
    except (urllib.error.URLError,OSError,ValueError) as error:
        result.update(status="not_retrieved",error_type=type(error).__name__,error=str(error))
    (DIRECTORY/"receipt.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2),flush=True)
    return result


if __name__ == "__main__":
    fetch()
