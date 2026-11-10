"""Transfer safeguards using only actual frozen public observations."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd

import fatigue_walking_source_teachers as study


@unittest.skipUnless((study.source.DIRECTORY/"provenance.json").exists(), "Requires the audited real public source union")
class WalkingTeacherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        parents, cls.combined, _, _ = cls.inputs
        _, train, _, members, _, _, _, _ = parents
        people = sorted(set(train.group_key))
        cls.fitting = train[train.group_key.isin(people[:6])]
        cls.validation = train[train.group_key.eq(people[6])]
        cls.specifications = members["member_specifications"]
        cls.walking = study.fit_walking_teachers(cls.combined, "ridge")
        cls.existing = joblib.load(study.parent.DIRECTORY/"teachers/ridge.joblib")

    def candidate(self, existing=False, member="core"):
        return next(c for c in study.plan()[10:] if c["teacher_algorithm"] == "ridge"
                    and c["include_existing_borg_teachers"] == existing and c["member"] == member)

    def fit(self, existing=False, member="core", observer=None):
        with patch("fatigue_prior_view_training.fitting_views", side_effect=AssertionError("Artificial history rows prohibited")):
            return study.WalkingSourceBorg(self.candidate(existing, member), self.walking, self.existing).fit(self.fitting, self.specifications, observer)

    def test_union_preserves_each_instrument_and_omits_unidentified_walking_sensors(self):
        self.assertEqual(len(self.combined), 458)
        self.assertEqual(self.combined.groupby("source_domain").size().to_dict(), {"worker":253,"sts":49,"walking_spe":156})
        walking = self.combined[self.combined.source_domain.eq("walking_spe")]
        self.assertEqual(walking.group_key.nunique(), 1)
        self.assertEqual(walking.sequence_key.nunique(), 52)
        self.assertTrue(walking[["hr_last", "hr_history_mean", "borg_native"]].isna().all().all())
        self.assertEqual(len(study.plan()), 22)
        self.assertEqual(len(self.inputs[0][1]), 487)
        self.assertEqual(len(self.inputs[0][2]), 179)

    def test_source_fit_uses_only_actual_earlier_spe_nominal_times_and_original_targets(self):
        seen = []
        targets = []
        from sklearn.linear_model import Ridge
        real_fit = Ridge.fit
        def observe(condition, inputs, current, prior):
            expected = self.combined[self.combined.source_condition.eq(condition)]
            pd.testing.assert_frame_equal(inputs, expected[study.FEATURES])
            np.testing.assert_array_equal(current, expected.spe_native.to_numpy())
            np.testing.assert_array_equal(prior, expected.prior_spe.to_numpy())
            targets.append(current-prior)
            seen.append(condition)
        calls = []
        def fit(model, inputs, target, **kwargs):
            np.testing.assert_array_equal(target, targets[len(calls)])
            self.assertEqual(len(inputs), 39)
            calls.append(1)
            return real_fit(model, inputs, target, **kwargs)
        with patch.object(Ridge, "fit", new=fit):
            teachers = study.fit_walking_teachers(self.combined, "ridge", observe)
        self.assertEqual(seen, list(study.source.walking.CONDITIONS))
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(int(model[-2].n_samples_seen_) == 39 for model in teachers.values()))
        self.assertFalse(set(study.FEATURES) & {"spe_native", "row_key", "group_key", "hr_last"})

    def test_native_fit_keeps_actual_rows_labels_and_uses_only_computed_source_features(self):
        for existing in (False, True):
            calls = []
            def observe(features, labels):
                pd.testing.assert_series_equal(labels, self.fitting.label)
                original = list(dict.fromkeys(self.specifications["core"]["features"]+study.parent.parent.FEATURES+["prior2_borg", "elapsed_minutes"]))
                pd.testing.assert_frame_equal(features[original], self.fitting[original])
                self.assertTrue(np.isfinite(features[study.OUTPUTS].to_numpy()).all())
                self.assertEqual(len(features), len(self.fitting))
                calls.append(1)
            model = self.fit(existing=existing, observer=observe)
            self.assertEqual(calls, [1])
            self.assertEqual(bool(model.existing_teachers), existing)
            self.assertFalse(set(model.input_features) & {"label", "row_key", "group_key"})
            expected = study.query_source_features(self.validation)
            np.testing.assert_array_equal(expected.prior_spe, self.validation.prior_borg)
            np.testing.assert_array_equal(expected.prior2_spe, self.validation.prior2_borg)
            np.testing.assert_array_equal(expected.nominal_elapsed_minutes, self.validation.elapsed_minutes)

    def test_serialized_core_and_cat_prediction_need_no_current_truth_or_identifiers(self):
        for member in ("core", "cat"):
            model = self.fit(existing=True, member=member)
            predicted = model.predict(self.validation)
            runtime = self.validation[model.input_features]
            np.testing.assert_array_equal(model.predict(runtime), predicted)
            self.assertFalse(set(vars(model)) & {"frame", "combined", "histories", "pool", "row_keys"})
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/"actual-walking-transfer.joblib"
                joblib.dump(model, path)
                np.testing.assert_array_equal(joblib.load(path).predict(runtime), predicted)


if __name__ == "__main__":
    unittest.main()
