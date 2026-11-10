"""Finite-support safeguards checked solely against actual public cases."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import torch

import fatigue_supported_physiology as study


@unittest.skipUnless(study.PREVIOUS_AUDIT.exists(), "Requires the audited actual public waveform study")
class SupportedPhysiologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()
        _, train, _, extra, arrays, lookup, manifest = cls.inputs
        people = sorted(set(train.group_key))
        cls.fitting = train[train.group_key.isin(people[:6])]
        cls.validation = train[train.group_key.eq(people[6])]
        cls.extra = extra[extra.group_key.isin(set(cls.fitting.group_key))]
        cls.specification = study.parent.core_candidate(manifest)
        cls.cache = study.parent.prepare_offsets(cls.fitting, cls.extra, cls.specification)
        cls.native_windows = study.parent.select_windows(arrays, lookup, cls.fitting.row_key)
        cls.extra_windows = study.parent.select_windows(arrays, lookup, cls.extra.row_key)
        cls.held_windows = study.parent.select_windows(arrays, lookup, cls.validation.row_key)

    def candidate(self, epochs=2, mass=.05):
        return {**study.plan()[7], "epochs": epochs, "anchor_uniform_mass": mass, "extra_report_weight": .1}

    def fit(self, epochs=2, mass=.05, observer=None):
        with patch("fatigue_prior_view_training.fitting_views", side_effect=AssertionError("Artificial histories prohibited")), patch("torch.rand", side_effect=AssertionError("Artificial input masks prohibited")):
            return study.SupportedPhysiologyBorg(self.candidate(epochs, mass)).fit(self.fitting, self.extra,
                self.native_windows, self.extra_windows, self.specification, self.cache, observer)

    def test_supported_probabilities_preserve_actual_initial_decisions_and_lower_bound(self):
        logits = torch.cat((self.cache["fit_logits"], self.cache["extra_logits"]))
        original = torch.softmax(logits, dim=1)
        supported = study.supported_anchor(logits, .05)
        torch.testing.assert_close(supported.exp(), .95*original+.05/21, rtol=1e-12, atol=1e-15)
        self.assertTrue((supported.exp() >= .05/21-1e-15).all())
        np.testing.assert_array_equal(logits.argmax(dim=1), supported.argmax(dim=1))
        self.assertTrue((original < 1e-10).any())
        self.assertEqual(len(study.plan()), 11)
        for mass in (0., .05):
            model = self.fit(0, mass)
            np.testing.assert_array_equal(model.predict(self.validation, self.held_windows), model.base.global_predict(self.validation))

    def test_backprop_receives_real_integer_targets_and_explicit_report_weights_without_smoothing(self):
        expected = pd.concat([self.fitting, self.extra], ignore_index=True)
        expected_target = torch.tensor(expected.label.str.removeprefix("Borg ").to_numpy(int)-expected.prior_borg.to_numpy(int)+10)
        calls = []
        def observe(features, windows, current, prior, weight):
            pd.testing.assert_frame_equal(features, expected[self.specification["features"]])
            for name in windows:
                np.testing.assert_array_equal(windows[name], np.concatenate([self.native_windows[name], self.extra_windows[name]]))
            np.testing.assert_array_equal(current, expected.label.str.removeprefix("Borg ").to_numpy(int))
            np.testing.assert_array_equal(prior, expected.prior_borg.to_numpy(int))
            np.testing.assert_array_equal(weight[:len(self.fitting)], np.ones(len(self.fitting)))
            np.testing.assert_array_equal(weight[len(self.fitting):], np.full(len(self.extra), .1))
            calls.append(len(current))
        real_loss = torch.nn.functional.cross_entropy
        with patch("torch.nn.functional.cross_entropy", wraps=real_loss) as loss:
            model = self.fit(observer=observe)
        self.assertEqual(calls, [len(expected)])
        self.assertEqual(loss.call_count, 2)
        for call in loss.call_args_list:
            torch.testing.assert_close(call.args[1], expected_target, rtol=0, atol=0)
            self.assertEqual(call.args[1].dtype, torch.long)
            self.assertFalse(call.kwargs.get("label_smoothing", 0))
        self.assertFalse(model.training_summary["label_smoothing"])
        self.assertEqual(model.training_summary["total_actual_targets"], len(expected))

    def test_correction_is_bounded_and_population_baseline_weights_stay_frozen(self):
        initial = self.fit(0)
        before = copy.deepcopy(initial.base.model.state_dict())
        fitted = self.fit()
        self.assertTrue(any(not torch.equal(v, fitted.network.state_dict()[k]) for k, v in initial.network.state_dict().items()))
        self.assertTrue(all(torch.equal(v, fitted.base.model.state_dict()[k]) for k, v in before.items()))
        context, raw_offsets = study.parent.base_features(fitted.base, self.validation)
        offsets = study.supported_anchor(raw_offsets, .05)
        normalized = study.parent.normalize_windows(self.held_windows, fitted.candidate)
        with torch.no_grad():
            correction = study.bounded_correction(fitted.network(normalized, context.float(), offsets), 3.)
        self.assertLessEqual(float(correction.abs().max()), 3.)
        self.assertTrue(all(not p.requires_grad and p.grad is None for p in fitted.network.parameters()))

    def test_reload_inference_excludes_current_truth_identifiers_and_report_pool(self):
        fitted = self.fit()
        expected = fitted.predict(self.validation, self.held_windows)
        runtime = self.validation[fitted.input_features]
        np.testing.assert_array_equal(fitted.predict(runtime, self.held_windows), expected)
        self.assertFalse(set(vars(fitted)) & {"fit_logits", "extra_logits", "inner_folds", "windows", "row_keys", "extra", "pool", "histories"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"supported-native.joblib"
            joblib.dump(fitted, path)
            np.testing.assert_array_equal(joblib.load(path).predict(runtime, self.held_windows), expected)


if __name__ == "__main__":
    unittest.main()
