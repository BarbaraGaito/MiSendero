"""Technical fixtures for observed previous Borg and portable calibration."""
import unittest

import numpy as np
import pandas as pd

from common.calibrated_forest import export_calibrated_forest, predict_calibrated_json, transformed_features
from fatigue_calibrated import previous_reports
from fatigue_experiment import estimator_for


class CalibratedFatigueTests(unittest.TestCase):
    def test_current_future_stale_and_previous_session_reports_are_not_predictors(self):
        now = pd.Timestamp("2020-01-01T12:30:00Z")
        reports = pd.DataFrame({"time": [now-pd.Timedelta(minutes=i) for i in (40, 20, 15, 5, 1, 0, -1)],
                                "borg_scale": [1, 2, 3, 4, 5, 6, 7]})
        result = previous_reports(reports, now, now-pd.Timedelta(minutes=12))
        self.assertEqual(result["borg_scale"].tolist(), [4, 5])
        self.assertTrue((result["time"] < now).all())

    def build_payload(self, mode):
        x = pd.DataFrame({"prior_borg": [2., 3., 4., 5.] * 4, "prior_age_minutes": [5.] * 16,
                          "hr": [100., np.nan, 110., 120.] * 4})
        candidate = {"algorithm": "extra_trees", "params": {"n_estimators": 3, "max_depth": 2},
                     "features": list(x), "target_mode": mode}
        y = np.asarray([2, 3, 5, 5] * 4)
        head = y - x["prior_borg"].to_numpy(dtype=int) if mode == "change_from_prior" else y
        classifier = estimator_for(candidate)
        classifier.fit(x, head.astype(str))
        contract = {"minimum_prior_age_minutes": 1, "maximum_prior_age_minutes": 15}
        payload = export_calibrated_forest(classifier, candidate, contract, {"deployment_approved": False})
        return x, classifier, payload

    def test_portable_median_imputation_and_transition_match_sklearn_exactly(self):
        for mode in ("absolute_borg", "change_from_prior"):
            x, classifier, payload = self.build_payload(mode)
            expected = classifier.predict(x).astype(int)
            if mode == "change_from_prior":
                expected = np.clip(expected + x["prior_borg"].to_numpy(dtype=int), 0, 10)
            self.assertEqual(predict_calibrated_json(payload, x).tolist(), [f"Borg {value}" for value in expected])
            transformed, _ = transformed_features(payload, x)
            np.testing.assert_allclose(transformed, classifier.steps[0][1].transform(x))

    def test_missing_current_future_or_expired_prior_is_never_imputed_as_real_calibration(self):
        x, _, payload = self.build_payload("change_from_prior")
        for column, value in (("prior_borg", np.nan), ("prior_borg", 2.5), ("prior_borg", 11),
                              ("prior_age_minutes", 0), ("prior_age_minutes", -1), ("prior_age_minutes", 16)):
            bad = x.copy()
            bad.loc[0, column] = value
            with self.subTest(column=column, value=value), self.assertRaises(ValueError):
                predict_calibrated_json(payload, bad)


if __name__ == "__main__":
    unittest.main()
