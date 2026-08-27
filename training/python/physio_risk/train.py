"""Train the physiological-risk RandomForest classifier consumed by the mobile app."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.augment import augment_dataset  # noqa: E402
from common.export_forest import export_metrics, export_random_forest  # noqa: E402
from common.privacy import assert_no_restricted_columns  # noqa: E402

FEATURE_COLUMNS = ["hr", "speed_kmh", "elapsed_minutes", "elevation_gain_m", "fatigue_score"]
LABEL_COLUMN = "label"

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET_PATH = REPO_ROOT / "ai" / "datasets" / "physio_risk.csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def main() -> None:
    raw = pd.read_csv(DATASET_PATH)
    assert_no_restricted_columns(raw, DATASET_PATH.name)
    augmented = augment_dataset(raw, LABEL_COLUMN, FEATURE_COLUMNS, target_rows_per_label=80)

    features = augmented[FEATURE_COLUMNS]
    labels = augmented[LABEL_COLUMN]

    x_train, x_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.25, stratify=labels, random_state=42
    )

    clf = RandomForestClassifier(n_estimators=50, max_depth=6, random_state=42)
    clf.fit(x_train, y_train)

    y_pred = clf.predict(x_test)
    classes = list(clf.classes_)
    metrics = export_metrics(y_test, y_pred, classes)
    forest_json = export_random_forest(clf, FEATURE_COLUMNS, classes)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (OUTPUT_DIR / "model.forest.json").write_text(json.dumps(forest_json, indent=2) + "\n")
    joblib.dump(clf, OUTPUT_DIR / "model.joblib")

    print(f"physio_risk: accuracy={metrics['accuracy']:.3f} "
          f"train_rows={len(x_train)} test_rows={len(x_test)}")
    print(f"physio_risk: per-class test counts={y_test.value_counts().to_dict()}")


if __name__ == "__main__":
    main()
