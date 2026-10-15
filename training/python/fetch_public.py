"""Fetch pinned public files, refusing silently changed source snapshots."""
import argparse
import json
import urllib.request

from public_sources import ADAPTERS, OUTPUT, RAW, digest, verify_source_snapshot


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=list(ADAPTERS), action="append")
    args = parser.parse_args()
    prefixes = {"fatigue": ("geofatigue/",), "physio_risk": ("11505046/",),
                "route_difficulty": ("osm/", "ign/"), "apn_route_difficulty": ("apn/",)}
    chosen = tuple(prefix for name in args.model or ADAPTERS for prefix in prefixes[name])
    lock = json.loads((OUTPUT / "sources.lock.json").read_text())
    for entry in lock["files"]:
        if not entry["path"].startswith(chosen):
            continue
        path = (RAW / entry["path"]).resolve()
        if not path.is_relative_to(RAW.resolve()):
            raise ValueError("Source path escapes raw directory")
        if path.exists() and digest(path) == entry["sha256"]:
            print(f"cached: {entry['path']}", flush=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".download")
        request = urllib.request.Request(entry["url"], headers={"User-Agent": "MiSendero/1.0 public source audit"})
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            for block in iter(lambda: response.read(1024 * 1024), b""):
                output.write(block)
        if digest(temporary) != entry["sha256"]:
            raise ValueError(f"Public snapshot changed: {entry['path']}. Keep cached originals or audit a new version. Lock was not updated.")
        temporary.replace(path)
        print(f"verified download: {entry['path']}", flush=True)
    for model in args.model or ADAPTERS:
        verify_source_snapshot(model)
