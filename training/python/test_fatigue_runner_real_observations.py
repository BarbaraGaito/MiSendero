"""Policy/inference checks using only the actual pinned public snapshots."""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import torch

import fatigue_runner_real_observations as study


@unittest.skipUnless((study.helpers.WINDOWS/"source.npz").exists(), "Requires the verified actual public signal snapshots")
class RealPublicRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = study.load_inputs()

    def test_actual_source_batches_are_unmodified_and_each_original_window_is_used_once(self):
        _, _, _, _, source, states, people, _, _ = self.inputs
        before = hashlib.sha256(source.tobytes()).hexdigest()
        seen = []
        def observer(epoch, indexes, batch, labels):
            self.assertEqual(epoch, 0)
            np.testing.assert_array_equal(batch, source[indexes])
            np.testing.assert_array_equal(labels, states[indexes])
            seen.extend(indexes.tolist())
        c = {**study.encoder_plan()[1], "epochs": 1}
        with patch("torch.rand", side_effect=AssertionError("Artificial input masking is prohibited")), patch.object(study.helpers.FrozenRunnerEncoder, "fit", side_effect=AssertionError("Archived masked-input fitting is prohibited")):
            fitted = study.RealRunnerEncoder(c).fit(source, states, people, observer)
        self.assertEqual(sorted(seen), list(range(330)))
        self.assertEqual(hashlib.sha256(source.tobytes()).hexdigest(), before)
        self.assertEqual(fitted.source_summary["artificial_sensor_rows"], 0)
        self.assertFalse(fitted.source_summary["source_input_masking"])
        self.assertEqual(fitted.source_summary["native_borg_targets_used"], 0)
        self.assertTrue(np.isfinite(fitted.extract(self.inputs[7])).all())

    def test_random_control_is_frozen_and_source_only_retraining_is_reproducible(self):
        source, states, people = self.inputs[4:7]
        c = study.encoder_plan()[0]
        a = study.RealRunnerEncoder(c).fit(source, states, people)
        b = study.RealRunnerEncoder(c).fit(source, states, people)
        self.assertEqual(a.source_summary["gradient_steps"], 0)
        self.assertEqual(a.source_summary["source_windows_used_for_gradient_updates"], 0)
        for key, value in a.network.state_dict().items():
            self.assertTrue(torch.equal(value, b.network.state_dict()[key]))
        self.assertTrue(all(not p.requires_grad and p.grad is None for p in a.network.parameters()))
        np.testing.assert_array_equal(a.extract(self.inputs[7]), b.extract(self.inputs[7]))

    def test_actual_native_fit_does_not_duplicate_reports_or_change_source_weights(self):
        _, train, _, members, source, states, people, windows, _ = self.inputs
        groups = sorted(set(train.group_key))
        fitting = train[train.group_key.isin(groups[:4])]
        validation = train[train.group_key.eq(groups[4])]
        self.assertTrue(len(fitting) > 0 and len(validation) > 0)
        encoder = study.RealRunnerEncoder(study.encoder_plan()[0]).fit(source, states, people)
        before = copy.deepcopy(encoder.network.state_dict())
        candidate = study.plan()[2]
        original_fit = study.helpers.DynamicsClassifier.fit
        def observed_fit(model, frame):
            np.testing.assert_array_equal(frame.row_key, fitting.row_key)
            np.testing.assert_array_equal(frame.label, fitting.label)
            pd.testing.assert_frame_equal(frame[study.helpers.GENERATED], study.helpers.add_features(fitting, windows[fitting.index], encoder)[study.helpers.GENERATED])
            return original_fit(model, frame)
        with patch("fatigue_prior_view_training.fitting_views", side_effect=AssertionError("Artificial history rows prohibited")), patch.object(study.helpers.DynamicsClassifier, "fit", observed_fit):
            model = study.RealRunnerBorg(candidate, encoder).fit(fitting, windows[fitting.index], members["member_specifications"])
        predicted = model.predict(validation, windows[validation.index])
        np.testing.assert_array_equal(model.predict(validation[model.input_features], windows[validation.index]), predicted)
        # Removing metadata/current labels checks inference, not fabricated
        # research training observations or replacement supervision.
        self.assertEqual(set(vars(model)), {"candidate", "encoder", "input_features", "model"})
        for key, value in before.items():
            self.assertTrue(torch.equal(value, encoder.network.state_dict()[key]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"real-public.joblib"
            joblib.dump(model, path)
            np.testing.assert_array_equal(joblib.load(path).predict(validation[model.input_features], windows[validation.index]), predicted)

    def test_plan_and_real_public_snapshots_preserve_the_original_task_and_people(self):
        _, train, test, members, source, states, people, windows, evidence = self.inputs
        self.assertEqual((len(train), len(test), len(windows)), (487, 179, 666))
        self.assertFalse(set(train.group_key) & set(test.group_key))
        self.assertEqual(len(source), 330)
        self.assertEqual(set(people), study.helpers.ALLOWED_PEOPLE)
        self.assertEqual(set(states), {0, 1})
        self.assertFalse(evidence["interpolated_signals"])
        self.assertEqual(evidence["native_borg_targets_stored"], 0)
        self.assertEqual(len(study.plan()), 17)
        self.assertTrue(all(c["artificial_input_transformations"] is False for c in study.encoder_plan()))
        self.assertEqual(set(members["member_specifications"]), {"core", "cat"})


if __name__ == "__main__":
    unittest.main()
