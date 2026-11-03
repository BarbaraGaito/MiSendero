import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import torch

from fatigue_temporal_transfer import FrozenTemporalEncoder, LENGTH, MaskedAutoencoder, encoder_plan, masked_batch, reconstruction_loss


class TemporalTransferTests(unittest.TestCase):
    def test_only_observed_hidden_bins_are_reconstruction_targets(self):
        torch.set_num_threads(1)
        batch = torch.zeros((2, 6, LENGTH))
        batch[:, :3] = torch.sin(torch.arange(LENGTH)*.1)
        batch[:, 3:, :180] = 1.
        inputs, target, supervised = masked_batch(batch, torch.Generator().manual_seed(42), .35)
        changed = batch.clone()
        changed[:, :3, 180:] = 999.
        after, after_target, after_supervised = masked_batch(changed, torch.Generator().manual_seed(42), .35)
        torch.testing.assert_close(inputs, after)
        torch.testing.assert_close(target, after_target)
        torch.testing.assert_close(supervised, after_supervised)
        self.assertFalse(supervised[:, :, 180:].any())
        self.assertFalse(inputs[:, :3][supervised.bool()].any())
        network = MaskedAutoencoder()
        predicted = network(inputs)
        self.assertEqual(predicted.shape, target.shape)
        loss = reconstruction_loss(predicted, target, supervised)
        loss.backward()
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in network.parameters()))

    def test_encoder_freezes_and_serializes_without_source_queries_or_labels(self):
        rng = np.random.default_rng(42)
        windows = np.concatenate((rng.normal(size=(8, 3, LENGTH)), np.ones((8, 3, LENGTH))), axis=1).astype(np.float32)
        spec = {**encoder_plan()[0], "epochs": 2}
        encoder = FrozenTemporalEncoder(spec).fit(windows, ["subject_01"]*8)
        before = {k: v.clone() for k, v in encoder.encoder.state_dict().items()}
        queries = np.concatenate((windows[:2], np.zeros((1, 6, LENGTH), dtype=np.float32)))
        expected = encoder.extract(queries)
        self.assertEqual(expected.shape, (3, 16))
        self.assertFalse(expected[-1].any())
        self.assertFalse(any(p.requires_grad or p.grad is not None for p in encoder.encoder.parameters()))
        self.assertEqual(set(vars(encoder)), {"candidate", "loss_endpoints", "encoder", "source_window_count", "source_participants"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"encoder.joblib"
            joblib.dump(encoder, path)
            restored = joblib.load(path)
            np.testing.assert_array_equal(restored.extract(queries), expected)
        for name, state in before.items():
            torch.testing.assert_close(encoder.encoder.state_dict()[name], state, rtol=0, atol=0)

    def test_reserved_external_people_are_rejected_before_training(self):
        windows = np.zeros((1, 6, LENGTH), dtype=np.float32)
        with self.assertRaisesRegex(ValueError, "fitting participants"):
            FrozenTemporalEncoder(encoder_plan()[0]).fit(windows, ["subject_02"])


if __name__ == "__main__":
    unittest.main()
