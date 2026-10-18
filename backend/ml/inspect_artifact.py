"""Operator smoke check, does not start a listener or connect to RDS."""
import argparse
import json
from pathlib import Path
from ranking import load_artifact

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        _, meta = load_artifact(args.directory)
        print(json.dumps({"status": "ready", "modelVersion": meta["modelVersion"]}))
    except Exception:
        print(json.dumps({"status": "unavailable", "fallback": "baseline"}))
        raise SystemExit(1)
