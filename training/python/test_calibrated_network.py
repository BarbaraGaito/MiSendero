"""Verify portable neural inference and the observed-calibration contract."""
import json
import unittest

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from common.calibrated_network import export_calibrated_network, predict_calibrated_network, predict_head_proba
from fatigue_calibrated_alternatives import CalibratedClassifier


class CalibratedNetworkTests(unittest.TestCase):
    def build_model(self, mode, labels):
        frame = pd.DataFrame({"prior_borg": [2., 4., 5., 7.] * 6,
                              "prior_age_minutes": [1., 5., 10., 15.] * 6,
                              "context": [np.nan, 1., 2., 3.] * 6,
                              "label": [f"Borg {i}" for i in labels] * 6})
        candidate = {"algorithm": "mlp", "features": ["prior_borg", "prior_age_minutes", "context"],
                     "params": {"hidden_layer_sizes": [8], "solver": "lbfgs", "alpha": 10., "max_iter": 1000},
                     "target_mode": mode}
        with threadpool_limits(limits=1):
            trained = CalibratedClassifier(candidate).fit(frame)
        payload = export_calibrated_network(trained, {"deployment_approved": False},
                                           {"minimum_prior_age_minutes": 1, "maximum_prior_age_minutes": 15})
        # Exercise the actual JSON boundary, not just the in-memory exporter.
        return frame, trained, json.loads(json.dumps(payload, allow_nan=False))

    def test_binary_and_multiclass_heads_match_fitted_probabilities_and_native_decisions(self):
        for mode, labels in (("absolute_borg", [3, 3, 6, 6]),
                             ("absolute_borg", [1, 3, 6, 8]),
                             ("change_from_prior", [2, 5, 4, 7])):
            with self.subTest(mode=mode, labels=labels):
                frame, trained, payload = self.build_model(mode, labels)
                x = frame[payload["feature_order"]]
                np.testing.assert_allclose(predict_head_proba(payload, x), trained.model.predict_proba(x), rtol=1e-10, atol=1e-10)
                np.testing.assert_array_equal(predict_calibrated_network(payload, x), trained.predict(frame))
                self.assertFalse(payload["evaluation_validity"]["deployment_approved"])
                frame["label"] = "Borg 10"
                np.testing.assert_array_equal(predict_calibrated_network(payload, x), trained.predict(frame))

    def test_invalid_or_unobserved_prior_cannot_be_replaced_by_imputation(self):
        frame, _, payload = self.build_model("change_from_prior", [2, 5, 4, 7])
        for column, value in (("prior_borg", np.nan), ("prior_borg", 1.5), ("prior_borg", -1),
                              ("prior_borg", 11), ("prior_age_minutes", np.nan), ("prior_age_minutes", 0),
                              ("prior_age_minutes", -1), ("prior_age_minutes", 16), ("context", np.inf)):
            bad = frame[payload["feature_order"]].copy()
            bad.loc[0, column] = value
            with self.subTest(column=column, value=value), self.assertRaises(ValueError):
                predict_calibrated_network(payload, bad)
        with self.assertRaises(ValueError):
            predict_calibrated_network(payload, frame[["prior_borg"]])


if __name__ == "__main__":
    unittest.main()
