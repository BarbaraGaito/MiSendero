import unittest

import numpy as np
import pandas as pd
import torch

from fatigue_joint_transfer import JointBorg, JointResidualNetwork
from fatigue_warm_sgd import core_candidate


class JointTransferTests(unittest.TestCase):
    def test_separate_fractional_auxiliary_head_updates_shared_encoder(self):
        torch.manual_seed(42)
        model = JointResidualNetwork(2, 2, ["sts", "post_test"])
        x = torch.ones((3, 2))
        target = torch.tensor([.5, 3., 4.])
        loss = torch.nn.functional.smooth_l1_loss(model.source_prediction(x, "sts"), target)
        loss.backward()
        self.assertGreater(sum(float(p.grad.abs().sum()) for p in model.encoder.parameters()), 0.)
        self.assertTrue(all(p.grad is None for p in model.source_heads["post_test"].parameters()))
        # A zero initialized correction preserves the exact base score vector.
        offsets = torch.randn((3, 21), dtype=torch.float64)
        np.testing.assert_array_equal(model.correction(x, torch.ones((3, 2)), offsets).detach(), np.zeros((3, 21)))

    def test_current_label_and_identity_do_not_enter_joint_prediction(self):
        frame = pd.DataFrame({"row_key": [f"r{i}" for i in range(18)], "group_key": [f"p{i//6}" for i in range(18)],
                              "prior_borg": [0, 1, 2, 2, 3, 3]*3, "prior_age_minutes": [5.]*18,
                              "hr_last": [90., 100., 110., 115., 120., 130.]*3,
                              "label": ["Borg 1", "Borg 2", "Borg 2", "Borg 3", "Borg 3", "Borg 4"]*3})
        external = pd.DataFrame({"hr_last": [80., 90., 100., 110.], "borg_native": [.5, 2., 3., 4.],
                                 "source_domain": ["sts"]*4, "group_key": [f"s{i}" for i in range(4)]})
        candidate = {"algorithm": "shared_sensor_residual_network", "sensor_features": ["hr_last"], "epochs": 2, "auxiliary_weight": .1}
        specification = core_candidate({"calibration_features": []})
        specification["features"] = ["prior_borg", "prior_age_minutes"]
        model = JointBorg(candidate).fit(frame, external, specification)
        before = model.predict(frame)
        changed = frame.copy()
        changed["label"], changed["group_key"] = "current_label_unavailable", "ignored_identity"
        np.testing.assert_array_equal(before, model.predict(changed))
        self.assertTrue(set(before) <= {f"Borg {i}" for i in range(11)})
        for age in (0., 16., np.nan):
            invalid = frame.copy()
            invalid["prior_age_minutes"] = age
            with self.assertRaises(ValueError):
                model.predict(invalid)


if __name__ == "__main__":
    unittest.main()
