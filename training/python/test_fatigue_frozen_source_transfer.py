import unittest

import numpy as np
import pandas as pd
import torch

from fatigue_frozen_source_transfer import FrozenSourceEncoder, added_feature_names


class FrozenSourceTransferTests(unittest.TestCase):
    def source(self):
        return pd.DataFrame({"row_key": [f"s{i}" for i in range(8)], "hr_last": [80., 90., 100., 110.]*2,
                             "borg_native": [.5, 2., 3., 4.]*2, "source_domain": ["a"]*4+["b"]*4})

    def specification(self):
        return {"features": ["hr_last"], "epochs": 2, "loss_weighting": "equal_domains"}

    def test_encoder_retains_fractional_targets_and_freezes_before_query_extraction(self):
        encoder = FrozenSourceEncoder(self.specification()).fit(self.source())
        self.assertEqual(encoder.native_fractional_report_count, 2)
        self.assertEqual(encoder.report_counts, {"a": 4, "b": 4})
        self.assertTrue(all(not p.requires_grad for p in encoder.model.parameters()))
        query = pd.DataFrame({"hr_last": [95., np.nan], "prior_borg": [2., 3.], "label": ["Borg 3", "Borg 4"], "group_key": ["ignored"]*2})
        weights = {k: v.detach().clone() for k, v in encoder.model.named_parameters()}
        first = encoder.extract(query)
        query["label"], query["group_key"] = "current_target_unavailable", "changed"
        second = encoder.extract(query)
        self.assertEqual(list(first), added_feature_names(["a", "b"]))
        for key in first:
            np.testing.assert_array_equal(first[key], second[key])
        self.assertTrue(all(torch.equal(weights[k], value) for k, value in encoder.model.named_parameters()))

    def test_non_native_or_missing_auxiliary_targets_are_rejected(self):
        for value in (np.nan, 15.):
            source = self.source()
            source.loc[0, "borg_native"] = value
            with self.assertRaises(ValueError):
                FrozenSourceEncoder(self.specification()).fit(source)


if __name__ == "__main__":
    unittest.main()
