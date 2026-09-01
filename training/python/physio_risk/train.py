"""Train the physiological-risk RandomForest classifier consumed by the mobile app."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.augment import augment_dataset  # noqa: E402
from common.evaluation import (  # noqa: E402
    evaluate_training_run,
    real_train_test_split,
    validate_training_frame,
)
from common.export_forest import export_random_forest  # noqa: E402
from common.privacy import assert_no_restricted_columns  # noqa: E402
from common.tuning import select_hyperparameters  # noqa: E402

FEATURE_COLUMNS = ["hr", "spo2", "speed_kmh", "elapsed_minutes", "elevation_gain_m", "fatigue_score"]
LABEL_COLUMN = "label"
DECLARED_SOURCE = "BIDMC (PhysioNet) + datos sinteticos fisiologicos documentados"
SOURCE_NOTE = (
    "Documento PFI seccion 2.1.6.3: BIDMC/PhysioNet aporta registros continuos "
    "de frecuencia cardiaca, frecuencia respiratoria y SpO2 de 53 sujetos; se "
    "complementa con datos sinteticos por falta de un dataset publico completo "
    "de riesgo en altitud."
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET_PATH = REPO_ROOT / "ai" / "datasets" / "physio_risk.csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def main() -> None:
    raw = pd.read_csv(DATASET_PATH)
    assert_no_restricted_columns(raw, DATASET_PATH.name)
    dataset = validate_training_frame(raw, FEATURE_COLUMNS, LABEL_COLUMN, DATASET_PATH.name)

    features = dataset[FEATURE_COLUMNS]
    labels = dataset[LABEL_COLUMN]

    x_train, x_test, y_train, y_test = real_train_test_split(features, labels)
    train_real = pd.concat(
        [x_train.reset_index(drop=True), y_train.reset_index(drop=True).rename(LABEL_COLUMN)],
        axis=1,
    )
    train_augmented = augment_dataset(
        train_real,
        LABEL_COLUMN,
        FEATURE_COLUMNS,
        target_rows_per_label=80,
    )
    synthetic_rows = len(train_augmented) - len(train_real)
    x_train_augmented = train_augmented[FEATURE_COLUMNS]
    y_train_augmented = train_augmented[LABEL_COLUMN]

    hyperparameters = select_hyperparameters(x_train, y_train)
    clf = RandomForestClassifier(
        n_estimators=hyperparameters["n_estimators"],
        max_depth=hyperparameters["max_depth"],
        min_samples_leaf=hyperparameters["min_samples_leaf"],
        class_weight="balanced",
        random_state=42,
    )
    clf.fit(x_train_augmented, y_train_augmented)

    classes = list(clf.classes_)
    metrics = evaluate_training_run(
        clf=clf,
        dataset_name="Riesgo fisiologico",
        declared_source=DECLARED_SOURCE,
        source_note=SOURCE_NOTE,
        feature_cols=FEATURE_COLUMNS,
        labels=classes,
        full_features=features,
        full_labels=labels,
        x_train=x_train_augmented,
        x_test=x_test,
        y_train=y_train_augmented,
        y_test=y_test,
        x_train_real=x_train,
        y_train_real=y_train,
        augmentation_used=True,
        synthetic_rows=synthetic_rows,
    )
    forest_json = export_random_forest(
        clf,
        FEATURE_COLUMNS,
        classes,
        metadata={
            "training_summary": {
                "declared_source": metrics["dataset"]["declared_source"],
                "dataset_rows": metrics["dataset"]["rows_total"],
                "synthetic_rows": metrics["augmentation"]["synthetic_rows"],
                "test_accuracy": metrics["metrics"]["test"]["accuracy"],
                "test_f1_macro": metrics["metrics"]["test"]["f1_macro"],
                "guardrail_status": metrics["guardrails"]["status"],
            }
        },
    )
    metrics["trained_at"] = forest_json["trained_at"]
    metrics["hyperparameters"] = hyperparameters

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (OUTPUT_DIR / "model.forest.json").write_text(json.dumps(forest_json, indent=2) + "\n")
    joblib.dump(clf, OUTPUT_DIR / "model.joblib")

    print(f"physio_risk: test_accuracy={metrics['metrics']['test']['accuracy']:.3f} "
          f"test_f1={metrics['metrics']['test']['f1_macro']:.3f} "
          f"real_train_rows={len(x_train)} synthetic_rows={synthetic_rows} "
          f"test_rows={len(x_test)}")
    print(f"physio_risk: guardrail_status={metrics['guardrails']['status']}")
    print(f"physio_risk: per-class test counts={y_test.value_counts().to_dict()}")


if __name__ == "__main__":
    main()
