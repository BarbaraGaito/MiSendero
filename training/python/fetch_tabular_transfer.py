"""Inspect official package/model metadata before local tabular transfer.

Uses the public, ungated TabPFN v2 model only. Never logs in, accepts gated
terms, sends training data, or runs a remotely downloaded study notebook.
"""
import hashlib
import json
import argparse
import urllib.request
from pathlib import Path

from public_sources import ROOT, digest

DIRECTORY = ROOT / "training/data/raw/fatigue-research/tabular-transfer-v1"
SOURCES = {
    "package": "https://pypi.org/pypi/tabpfn/json",
    "model": "https://huggingface.co/api/models/Prior-Labs/TabPFN-v2-clf?blobs=true",
}


def model_file(filename):
    metadata = json.loads((DIRECTORY / "model.json").read_text(encoding="utf-8"))
    if metadata.get("gated") is not False or metadata.get("private"):
        raise ValueError("Only the public ungated v2 model is permitted")
    entry = next(f for f in metadata["siblings"] if f["rfilename"] == filename)
    if entry["size"] > 32_000_000 or Path(filename).name != filename:
        raise ValueError("Model file exceeds the audited size/path bound")
    url = f"https://huggingface.co/Prior-Labs/TabPFN-v2-clf/resolve/{metadata['sha']}/{filename}?download=true"
    path = DIRECTORY / filename
    if not path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "MiSendero-Borg-research/1.0"})
        temporary = path.with_suffix(path.suffix + ".part")
        size = 0
        with urllib.request.urlopen(request, timeout=45) as response, temporary.open("wb") as output:
            if not response.url.startswith("https://"):
                raise ValueError("Model file redirected outside HTTPS")
            for block in iter(lambda: response.read(65536), b""):
                size += len(block)
                if size > entry["size"]:
                    raise ValueError("Model file exceeded its published size")
                output.write(block)
        temporary.rename(path)
    content = path.read_bytes()
    if len(content) != entry["size"]:
        raise ValueError("Model file size differs from published metadata")
    if "lfs" in entry:
        if digest(path) != entry["lfs"]["sha256"]:
            raise ValueError("Model weights differ from publisher Git LFS SHA256")
    else:
        blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if blob != entry["blobId"]:
            raise ValueError("Model documentation differs from pinned revision")
    print(json.dumps({"filename": filename, "bytes": len(content), "sha256": digest(path), "revision": metadata["sha"]}))


def main(model_docs=False, weights=False):
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        path = DIRECTORY / f"{name}.json"
        if not path.exists():
            request = urllib.request.Request(url, headers={"User-Agent": "MiSendero-Borg-research/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read(2_000_001)
            if len(content) > 2_000_000:
                raise ValueError("Official metadata exceeds the bounded size")
            json.loads(content)
            path.write_bytes(content)
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if name == "package":
            print(json.dumps({"source": url, "metadata_sha256": digest(path), "version": metadata["info"]["version"],
                              "requires_python": metadata["info"]["requires_python"], "dependencies": metadata["info"]["requires_dist"],
                              "wheels": [{"filename": f["filename"], "size": f["size"], "sha256": f["digests"]["sha256"]} for f in metadata["urls"] if f["packagetype"] == "bdist_wheel"]}, indent=2))
        else:
            print(json.dumps({"source": url, "metadata_sha256": digest(path), "gated": metadata.get("gated"),
                              "private": metadata.get("private"), "revision": metadata.get("sha"),
                              "files": [{k: f[k] for k in ("rfilename", "size", "lfs") if k in f} for f in metadata.get("siblings", []) if "v2_default" in f["rfilename"] or f["rfilename"].lower().startswith(("license", "readme"))]}, indent=2))
    if model_docs or weights:
        model_file("LICENSE.txt")
        model_file("README.md")
    if weights:
        model_file("tabpfn-v2-classifier-v2_default.ckpt")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-docs", action="store_true")
    parser.add_argument("--weights", action="store_true")
    args = parser.parse_args()
    main(args.model_docs, args.weights)
