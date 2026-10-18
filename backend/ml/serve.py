"""Private bounded JSONL worker. No HTTP listener, DB, network, prompts or training."""
import argparse
import json
import os
import sys
from pathlib import Path

from ranking import load_artifact, matrix


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--synthetic-technical-test", action="store_true")
    args = parser.parse_args()
    if args.synthetic_technical_test and os.environ.get("NODE_ENV") != "test":
        raise ValueError("Technical test mode is forbidden outside tests")
    model, meta = load_artifact(args.model_dir, synthetic_test=args.synthetic_technical_test)
    def emit(value):
        print(json.dumps(value, allow_nan=False), flush=True)
    emit({"type": "ready", "modelVersion": meta["modelVersion"], "featureSchemaVersion": meta["featureSchemaVersion"]})
    while True:
        line = sys.stdin.buffer.readline(2 * 1024 * 1024 + 1)
        if not line:
            return
        if len(line) > 2 * 1024 * 1024 or not line.endswith(b"\n"):
            raise ValueError("Oversize or incomplete frame")
        message = json.loads(line)
        if not isinstance(message, dict) or set(message) != {"id", "features"} or type(message["id"]) is not int or not 0 < message["id"] <= 2 ** 53 - 1:
            raise ValueError("Invalid worker frame")
        scores = model.predict(matrix(message["features"])).tolist()
        emit({"id": message["id"], "scores": scores})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never echo data, filesystem paths, credentials or pickled object errors over the protocol.
        print("Trail ranking worker unavailable", file=sys.stderr)
        sys.exit(1)
