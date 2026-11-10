"""Fetch SHA256-pinned original OxBioZ data; default is one small schema probe.

Read-only public downloads. HDF5 is inspected as data, with no source scripts
executed. The 1.25 GB cohort is opt-in only after the schema probe is audited.
"""
import argparse
import json
from pathlib import Path

from fetch_fatigue_extra import download
from public_sources import ROOT, digest

DIRECTORY = ROOT / "training/data/raw/fatigue-research/oxbioz-v1"
REVISION = "2ff7c33f5582fce5a8257320d3995c267a08d323"
FILES = {
    "fabric": ("OxBioZ_fabric_electrodes.hdf5", 66136520, "13d31d990e950b90359e54777ea01506e44f473a09d311787a9cdc3089932b1e"),
    "gel": ("OxBioZ_gel_electrodes.hdf5", 1248390800, "2f205e82e7b7043a2a20bb077f917d8b5e26a3253205d51fa4aaca575077da88"),
}


def fetch(cohort):
    DIRECTORY.mkdir(exist_ok=True)
    for name in ("README.md", "LICENSE"):
        download(f"https://raw.githubusercontent.com/XinyuHou97/OxBioZ/{REVISION}/{name}", DIRECTORY / name, maximum_bytes=100000)
    name, size, sha256 = FILES[cohort]
    pointer = download(f"https://raw.githubusercontent.com/XinyuHou97/OxBioZ/{REVISION}/data/{name}", DIRECTORY / (name + ".lfs"), maximum_bytes=1000)
    if pointer.read_text(encoding="utf-8") != f"version https://git-lfs.github.com/spec/v1\noid sha256:{sha256}\nsize {size}\n":
        raise ValueError("Published OxBioZ LFS pointer differs from inspected pinned source")
    path = download(f"https://media.githubusercontent.com/media/XinyuHou97/OxBioZ/{REVISION}/data/{name}", DIRECTORY / name,
                    maximum_bytes=size, expected_bytes=size, sha256=sha256)
    if path.stat().st_size != size or digest(path) != sha256:
        raise ValueError("OxBioZ dataset differs from publisher SHA256")
    report = {"source": "https://github.com/XinyuHou97/OxBioZ", "revision": REVISION, "cohort": cohort,
              "filename": name, "bytes": size, "sha256": sha256, "publisher_lfs_sha256_verified": True,
              "readme_sha256": digest(DIRECTORY / "README.md"), "license_sha256": digest(DIRECTORY / "LICENSE"),
              "training_merge_approved": False, "pending": "Verify actual Borg labels, native scale and timing before any fitting."}
    (DIRECTORY / (cohort + "-receipt.json")).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", choices=FILES, default="fabric")
    fetch(parser.parse_args().cohort)
