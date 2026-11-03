"""Canonical module entrypoint so saved estimator classes remain importable."""
import argparse

from fatigue_probability import evaluate, select


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluate", action="store_true")
    args = parser.parse_args()
    evaluate() if args.evaluate else select()
