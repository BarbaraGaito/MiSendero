import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from fatigue_gaussian_process import GaussianBorg, bounded_lml, fitting_reports


class GaussianBorgTests(unittest.TestCase):
    def fixture(self):
        frame = pd.DataFrame({"prior_borg": np.tile([1., 2., 3., 4.], 6),
            "prior_age_minutes": 5., "elapsed_minutes": np.arange(1., 25.),
            "row_key": [f"q{i}" for i in range(24)], "group_key": [f"p{i//4}" for i in range(24)],
            "label": [f"Borg {1+i%4+(i//4)%2}" for i in range(24)]})
        extra = pd.DataFrame([{**frame.iloc[0].to_dict(), "row_key": "additional-observation", "label": "Borg 2"},
            {**frame.iloc[0].to_dict(), "row_key": "reserved-observation", "group_key": "reserved-person", "label": "unavailable_current_label", "prior_borg": np.nan}])
        return frame, extra

    def test_excluded_person_is_filtered_before_reading_extra_values(self):
        frame, extra = self.fixture()
        data, target, summary = fitting_reports(frame, extra, True)
        self.assertEqual(len(data), 25)
        self.assertEqual(summary["additional_actual_reports"], 1)
        self.assertNotIn("reserved-person", data.group_key.tolist())
        np.testing.assert_array_equal(target[-1:], [2])
        data, _, summary = fitting_reports(frame, extra, False)
        self.assertEqual(len(data), 24)
        self.assertEqual(summary["additional_actual_reports"], 0)

    def test_fractional_targets_and_duplicate_measured_reports_are_rejected(self):
        frame, extra = self.fixture()
        bad = extra.iloc[:1].copy()
        bad["label"] = "Borg 2.5"
        with self.assertRaisesRegex(ValueError, "no rescaling or rounding"):
            fitting_reports(frame, bad, True)
        bad["row_key"] = frame.iloc[0]["row_key"]
        with self.assertRaisesRegex(ValueError, "unique actually observed"):
            fitting_reports(frame, bad, True)

    def test_bounded_likelihood_optimizer_respects_parameter_bounds(self):
        def objective(x):
            error = x-np.array([2., -3.])
            return float(error @ error), 2*error
        theta, loss = bounded_lml(objective, np.array([0., 0.]), [(-1., 1.), (-1., 1.)])
        np.testing.assert_allclose(theta, [1., -1.], atol=1e-8)
        self.assertAlmostEqual(loss, 5.)

    def test_gp_persistence_and_inference_ignore_current_outcome_and_identifiers(self):
        frame, extra = self.fixture()
        features = ["prior_borg", "prior_age_minutes", "elapsed_minutes"]
        for kernel, mode in [("rbf", "absolute_borg"), ("matern_1.5", "change_from_prior")]:
            candidate = {"features": features, "kernel": kernel, "target_mode": mode, "include_extra": True}
            model = GaussianBorg(candidate).fit(frame, extra)
            expected = model.predict(frame)
            self.assertEqual(expected.shape, (24,))
            self.assertTrue(set(expected) <= {f"Borg {i}" for i in range(11)})
            changed = frame.assign(label="unknown current outcome", row_key="unused", group_key="unused")
            np.testing.assert_array_equal(model.predict(changed), expected)
            np.testing.assert_array_equal(model.predict(frame[features]), expected)
            self.assertNotIn("history", vars(model))
            self.assertEqual(model.training_summary["total_actual_reports"], 25)
            self.assertTrue(np.isfinite(model.training_diagnostics["log_marginal_likelihood"]))
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder)/"model.joblib"
                joblib.dump(model, path)
                np.testing.assert_array_equal(joblib.load(path).predict(changed), expected)
            with self.assertRaises(ValueError):
                model.predict(frame.assign(prior_age_minutes=0.))


if __name__ == "__main__":
    unittest.main()
