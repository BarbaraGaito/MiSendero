"""Bounded public metadata discovery for gait datasets; no training merge."""
import json
import urllib.request
from datetime import datetime, timezone

from public_sources import ROOT, digest
from fetch_fatigue_extra import download

DIRECTORY = ROOT / "training/data/raw/fatigue-research/gait-candidates-80-v1"
URLS = {
    "sixmwt-collection.json": "https://api.figshare.com/v2/collections/7954157/articles?page_size=100",
    "whamap-page.html": "https://data.mendeley.com/datasets/8zt9g9g64c/1",
    "whamap-client.js": "https://data.mendeley.com/datasets/bundle.js?8533f74fd5ffa7f3d44f",
    "whamap-files.json": "https://data.mendeley.com/public-api/datasets/8zt9g9g64c/files?folder_id=root&version=1&$start=0&$limit=1000",
    "whamap-folders.json": "https://data.mendeley.com/public-api/datasets/8zt9g9g64c/folders/1",
    "whamap-top-files.json": "https://data.mendeley.com/public-api/datasets/8zt9g9g64c/files?folder_id=35b09264-0804-47a7-bb14-84d43bea8759&version=1&$start=0&$limit=1000",
    "whamap-data-files.json": "https://data.mendeley.com/public-api/datasets/8zt9g9g64c/files?folder_id=c329be93-f74d-499a-a943-4c667fb10e53&version=1&$start=0&$limit=1000",
}


def metadata(name, url):
    path = DIRECTORY / name
    if not path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "MiSendero public dataset eligibility audit"})
        with urllib.request.urlopen(request, timeout=40) as response:
            payload = response.read(2_000_001)
            if len(payload) > 2_000_000:
                raise ValueError("Metadata response exceeds 2 MB")
        if name.endswith(".json"):
            json.loads(payload)
        path.write_bytes(payload)
    return {"name": name, "url": url, "bytes": path.stat().st_size, "sha256": digest(path)}


def fetch():
    DIRECTORY.mkdir(exist_ok=True)
    receipt = {"version": 1, "metadata_only": True, "used_for_training": False,
               "retrieved_at": datetime.now(timezone.utc).isoformat(), "sources": [], "unavailable": []}
    for name, url in URLS.items():
        try:
            entry = metadata(name, url)
            receipt["sources"].append(entry)
            print(f"Verified metadata {name}: {entry['bytes']} bytes", flush=True)
        except (urllib.error.URLError, TimeoutError) as error:
            receipt["unavailable"].append({"name": name, "url": url, "error": str(error)})
            print(f"Metadata unavailable {name}: {error}", flush=True)
    collection = DIRECTORY / "sixmwt-collection.json"
    if collection.exists():
        articles = json.loads(collection.read_text(encoding="utf-8"))
        if not isinstance(articles, list) or len(articles) > 20:
            raise ValueError("Inspect the collection before retrieving an unexpected number of records")
        for article in articles:
            article_id = int(article["id"])
            entry = metadata(f"sixmwt-article-{article_id}.json", f"https://api.figshare.com/v2/articles/{article_id}")
            receipt["sources"].append(entry)
            original = json.loads((DIRECTORY / entry["name"]).read_text(encoding="utf-8"))
            print(json.dumps({"article": article_id, "title": original["title"], "license": original.get("license"),
                              "files": [{k: f.get(k) for k in ("id", "name", "size", "computed_md5", "download_url")} for f in original.get("files", [])]}, indent=2), flush=True)
    whamap_files = DIRECTORY / "whamap-top-files.json"
    if whamap_files.exists():
        listed = json.loads(whamap_files.read_text(encoding="utf-8"))
        entry = next(r for r in listed if r["filename"] == "README.md")["content_details"]
        if entry["size"] != 4699 or entry["sha256_hash"] != "5848ce67c2aec612995fc76dede71c5ede0eb454faf051e2b375e982bb916ab9":
            raise ValueError("WHAMAP README differs from inspected publisher metadata")
        path = download(entry["download_url"], DIRECTORY / "whamap-README.md", maximum_bytes=entry["size"],
                        expected_bytes=entry["size"], sha256=entry["sha256_hash"])
        receipt["sources"].append({"name": path.name, "url": entry["download_url"], "bytes": path.stat().st_size,
                                   "sha256": digest(path), "publisher_sha256_verified": True})
        print(f"Verified original WHAMAP README: {path.stat().st_size} bytes", flush=True)
    (DIRECTORY / "metadata-receipt.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    fetch()
