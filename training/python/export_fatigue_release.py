"""Export the frozen, verified calibrated MLP into a portable data-only JSON."""
import json

import joblib
import numpy as np

from common.calibrated_network import export_calibrated_network, predict_calibrated_network, predict_head_proba
from fatigue_calibrated_ensemble import load_inputs
from fatigue_features import RESEARCH
from public_sources import digest


def main():
    directory = RESEARCH / "calibrated-alternatives-v1/evaluation"
    metadata_path = directory / "metrics.json"
    metrics = json.loads(metadata_path.read_text(encoding="utf-8"))
    artifact = directory / metrics["model_artifact"]["path"]
    if digest(artifact) != metrics["model_artifact"]["sha256"]:
        raise ValueError("Locally trained model changed after evaluation")
    model = joblib.load(artifact)  # Only this task's pinned, locally fitted model.
    frame, _, _, _, _ = load_inputs()
    payload = export_calibrated_network(model, metrics["evaluation_validity"], metrics["input_contract"])
    x = frame[payload["feature_order"]]
    if not np.array_equal(predict_calibrated_network(payload, x), model.predict(frame)):
        raise AssertionError("Portable network decisions differ from the fitted model")
    if not np.allclose(predict_head_proba(payload, x), model.model.predict_proba(x), atol=1e-10, rtol=1e-10):
        raise AssertionError("Portable network probabilities differ from the fitted model")
    path = directory / "model.calibrated.json"
    content = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != content:
        raise ValueError("A different portable release already exists; preserve prior evidence")
    path.write_text(content, encoding="utf-8")
    metrics["portable_model_artifact"] = {"path": path.name, "sha256": digest(path), "format": payload["type"],
                                           "verified_against_fitted_model_on_all_rows": len(frame)}
    metadata_path.write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Verified portable calibrated MLP on all {len(frame)} original observations: {path}")


if __name__ == "__main__":
    main()
