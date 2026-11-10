"""Learning invariants exercised exclusively on existing public observations."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import torch

import fatigue_physiology_pair_learning as study


@unittest.skipUnless(study.INPUT_AUDIT.exists(), "Requires independently verified actual public waveforms")
class PhysiologyLearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        _, train, _, extra, cls.arrays, cls.lookup, manifest = cls.inputs
        people = sorted(set(train.group_key))
        cls.fitting = train[train.group_key.isin(people[:6])]
        cls.validation = train[train.group_key.eq(people[6])]
        cls.extra = extra[extra.group_key.isin(set(cls.fitting.group_key))]
        cls.specification = study.core_candidate(manifest)
        cls.cache = study.prepare_offsets(cls.fitting, cls.extra, cls.specification)
        cls.fitting_windows = study.select_windows(cls.arrays, cls.lookup, cls.fitting.row_key)
        cls.extra_windows = study.select_windows(cls.arrays, cls.lookup, cls.extra.row_key)
        cls.validation_windows = study.select_windows(cls.arrays, cls.lookup, cls.validation.row_key)

    def candidate(self, epochs=2, extra=True):
        return {**study.plan()[-1], "epochs": epochs, "include_extra_actual_reports": extra}

    def fit(self, epochs=2, extra=True, observer=None):
        with patch("fatigue_prior_view_training.fitting_views", side_effect=AssertionError("Artificial histories prohibited")), patch("torch.rand", side_effect=AssertionError("Artificial waveform masks prohibited")):
            return study.PhysiologyPairBorg(self.candidate(epochs, extra)).fit(self.fitting, self.extra,
                self.fitting_windows, self.extra_windows, self.specification, self.cache, observer)

    def test_nested_offsets_exclude_each_real_native_and_extra_person(self):
        groups = pd.concat([self.fitting, self.extra]).set_index("row_key").group_key.to_dict()
        native, extra = [], []
        for fold in self.cache["inner_folds"]:
            held = fold["validation_row_keys"]+fold["extra_validation_row_keys"]
            self.assertFalse({groups[k] for k in held} & {groups[k] for k in fold["fit_row_keys"]})
            native.extend(fold["validation_row_keys"])
            extra.extend(fold["extra_validation_row_keys"])
        self.assertEqual(sorted(native), sorted(self.fitting.row_key))
        self.assertEqual(sorted(extra), sorted(self.extra.row_key))
        initial = self.fit(0)
        np.testing.assert_array_equal(initial.predict(self.validation, self.validation_windows), initial.base.global_predict(self.validation))

    def test_normalization_preserves_actual_observation_masks_and_missing_values(self):
        normalized = study.normalize_windows(self.fitting_windows, self.candidate())
        for name, tensor in normalized.items():
            real = self.fitting_windows[name]
            self.assertTrue(torch.isfinite(tensor).all())
            np.testing.assert_array_equal(tensor.numpy()[:, 2:], real[:, 2:])
            self.assertFalse(tensor.numpy()[:, :2][real[:, 2:] == 0].any())
            self.assertLessEqual(float(tensor[:, :2].abs().max()), 20.)
        self.assertEqual(len(study.plan()), 10)
        self.assertFalse(set(self.specification["features"]) & {"label", "row_key", "group_key"})

    def test_backprop_sees_exact_actual_inputs_targets_and_leaves_the_baseline_unchanged(self):
        calls = []
        expected_frame = pd.concat([self.fitting, self.extra], ignore_index=True)
        def observe(frame, windows, current, prior):
            pd.testing.assert_frame_equal(frame, expected_frame[self.specification["features"]])
            for name in windows:
                np.testing.assert_array_equal(windows[name], np.concatenate([self.fitting_windows[name], self.extra_windows[name]]))
            np.testing.assert_array_equal(current, expected_frame.label.str.removeprefix("Borg ").to_numpy(int))
            np.testing.assert_array_equal(prior, expected_frame.prior_borg.to_numpy(int))
            calls.append(len(current))
        initial = self.fit(0)
        base_before = copy.deepcopy(initial.base.model.state_dict())
        fitted = self.fit(observer=observe)
        self.assertEqual(calls, [len(expected_frame)])
        self.assertTrue(any(not torch.equal(v, fitted.network.state_dict()[k]) for k, v in initial.network.state_dict().items()))
        self.assertTrue(all(torch.equal(v, fitted.base.model.state_dict()[k]) for k, v in base_before.items()))
        self.assertEqual(fitted.training_summary["additional_actual_targets"], len(self.extra))
        self.assertEqual(self.fit(extra=False).training_summary["additional_actual_targets"], 0)
        self.assertTrue(all(not p.requires_grad and p.grad is None for p in fitted.network.parameters()))

    def test_reloaded_prediction_needs_no_current_truth_identifiers_or_stored_observations(self):
        model = self.fit()
        expected = model.predict(self.validation, self.validation_windows)
        runtime = self.validation[model.input_features]
        np.testing.assert_array_equal(model.predict(runtime, self.validation_windows), expected)
        self.assertFalse(set(vars(model)) & {"fit_logits", "extra_logits", "inner_folds", "windows", "row_keys", "extra", "pool", "histories"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"actual-physiology-model.joblib"
            joblib.dump(model, path)
            np.testing.assert_array_equal(joblib.load(path).predict(runtime, self.validation_windows), expected)


if __name__ == "__main__":
    unittest.main()
