"""Check that every tracked training CSV is free of personal or exact-location fields.

Run before committing a new dataset export or after editing `build_datasets.py`:

    py training/python/validate_datasets.py

This applies the same `assert_no_restricted_columns` denylist the `train.py`
scripts enforce at training time (see `training/python/common/privacy.py`),
but here it runs on demand against the tracked CSVs so a bad column is caught
before it ever reaches a commit or a training run.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from common.privacy import assert_no_restricted_columns

REPO_ROOT = Path(__file__).resolve().parents[2]

TRACKED_CSVS = [
    REPO_ROOT / "ai" / "datasets" / "fatigue_windows.csv",
    REPO_ROOT / "ai" / "datasets" / "physio_risk.csv",
    REPO_ROOT / "training" / "route-difficulty" / "datasets" / "route_difficulty_training.csv",
]


def main() -> None:
    failures: list[str] = []

    for path in TRACKED_CSVS:
        relative = path.relative_to(REPO_ROOT)
        if not path.exists():
            print(f"skip (not found): {relative}")
            continue

        df = pd.read_csv(path)
        try:
            assert_no_restricted_columns(df, path.name)
        except ValueError as error:
            failures.append(f"{relative}: {error}")
            print(f"FAIL: {relative} -> {error}")
            continue

        print(f"ok: {relative} ({len(df)} rows, columns={list(df.columns)})")

    if failures:
        raise SystemExit(f"{len(failures)} dataset(s) failed the anonymization check")

    print("all tracked datasets passed the anonymization check")


if __name__ == "__main__":
    main()
