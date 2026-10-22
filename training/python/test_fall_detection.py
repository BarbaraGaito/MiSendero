"""Checks for the experimental fall-detection pipeline (UniMiB SHAR).

Tests that need the raw dataset are skipped, with a reason, when it has not been downloaded.
Synthetic arrays appear only as unit-test inputs of deterministic rules; they never reach training.
"""
import json
import unittest

import numpy as np
from sklearn.model_selection import GroupKFold

from fall_detection import config
from fall_detection.candidates import candidate_peaks
from fall_detection.dataset import ARCHIVE, FULL_DATA, ROOT, load_records, sha256
from fall_detection.evaluation import from_counts, counts
from fall_detection.export_contract import TARGET, contract
from fall_detection.features import FEATURE_ORDER, window_features

METRICS = ROOT / "training/data/public/fall_detection/metrics.json"
MODEL = ROOT / "services/fallDetection/fallModel.json"
FIXTURE = ROOT / "testing/fixtures/fall-detection/parity.json"
HAVE_DATA = FULL_DATA.exists() and ARCHIVE.exists()
_cache = {}


def records():
    if "r" not in _cache:
        _cache["r"] = load_records()
    return _cache["r"]


@unittest.skipUnless(HAVE_DATA, "UniMiB SHAR is not downloaded (training/data/raw/unimib-shar)")
class DatasetIntegrity(unittest.TestCase):
    def test_archive_matches_recorded_checksum(self):
        recorded = json.loads(MODEL.read_text(encoding="utf-8"))["provenance"]["archive_sha256"]
        self.assertEqual(sha256(ARCHIVE), recorded)

    def test_counts_units_and_exclusions_are_the_documented_ones(self):
        recs, audit = records()
        self.assertEqual(audit["participants"], 30)
        self.assertEqual(len({r.participant for r in recs}), 30)
        trials = {(r.participant, r.activity, r.trial) for r in recs}
        self.assertEqual(len(trials), 1980 - 1)                               # 30 x (9x2 + 8x6), minus the NaN trial
        self.assertEqual([(e["participant"], e["activity"], e["trial"]) for e in audit["excluded_records"]], [(9, "Jumping", 1)])
        self.assertEqual(sum(r.kind == "fall" for r in recs), 1440)
        self.assertTrue(all(np.isfinite(r.xyz_g).all() for r in recs))
        resting = np.median([np.linalg.norm(r.xyz_g, axis=1).mean() for r in recs if r.activity == "SittingDown"])
        self.assertAlmostEqual(resting, 1.0, delta=0.1)                       # gravity included, converted to g

    def test_segments_are_contiguous_and_pockets_are_labelled(self):
        recs, audit = records()
        self.assertEqual(audit["recording_gaps_split"], 960)                  # 240 posture trials x 4 gaps
        self.assertEqual({r.pocket for r in recs}, {"right", "left"})
        for activity in config.FALL_ACTIVITIES:
            self.assertTrue(all(r.segment == 0 for r in recs if r.activity == activity))


class FeatureAndRuleTests(unittest.TestCase):
    def test_features_are_orientation_invariant(self):
        # Unit-test input only: a pseudo-random smooth window and a random rotation of its axes.
        rng = np.random.default_rng(1)
        window = 1 + 0.3 * rng.standard_normal((config.WINDOW, 3))
        q, _ = np.linalg.qr(rng.standard_normal((3, 3)))
        np.testing.assert_allclose(window_features(window), window_features(window @ q), rtol=1e-9, atol=1e-9)
        self.assertEqual(len(window_features(window)), len(FEATURE_ORDER))

    def test_candidate_rule_requires_gate_and_first_local_maximum(self):
        m = np.ones(100)
        m[50] = 2.0
        m[52] = 2.0                      # later equal value inside the neighbourhood: still the same event
        m[10] = 1.4                      # below the gate
        self.assertEqual(candidate_peaks(m), [50])
        m[60] = 2.5                      # higher peak within +-20 samples replaces it
        self.assertEqual(candidate_peaks(m), [60])

    def test_streaming_margin_is_consistent(self):
        self.assertGreaterEqual(config.POST_SAMPLES, config.NEIGHBOURHOOD)
        self.assertEqual(config.WINDOW, 61)

    def test_contract_file_is_generated_from_python(self):
        self.assertEqual(json.loads(TARGET.read_text(encoding="utf-8")), json.loads(json.dumps(contract())))

    def test_metrics_helpers(self):
        c = counts(np.array([1, 1, 0, 0, 0]), np.array([1, 0, 1, 0, 0]))
        m = from_counts(c)
        self.assertEqual((c["tp"], c["fp"], c["fn"], c["tn"]), (1, 1, 1, 2))
        self.assertAlmostEqual(m["precision"], 0.5)
        self.assertAlmostEqual(m["recall"], 0.5)
        self.assertAlmostEqual(m["specificity"], 2 / 3)
        self.assertEqual(m["confusion_matrix"], [[2, 1], [1, 1]])


@unittest.skipUnless(HAVE_DATA and METRICS.exists(), "needs the dataset and training/data/public/fall_detection/metrics.json")
class EvaluationHonesty(unittest.TestCase):
    def test_participants_never_cross_train_and_test(self):
        recs, _ = records()
        groups = np.array([r.participant for r in recs])
        for fit, val in GroupKFold(n_splits=5).split(groups, groups, groups):
            self.assertFalse(set(groups[fit]) & set(groups[val]))

    def test_reported_metrics_equal_the_saved_out_of_fold_predictions(self):
        saved = ROOT / "training/data/processed/fall_detection_oof.npz"
        if not saved.exists():
            self.skipTest("out-of-fold predictions not kept (re-run fall_detection.run_loso)")
        data = np.load(saved, allow_pickle=False)
        report = json.loads(METRICS.read_text(encoding="utf-8"))["models"]
        for name in ("threshold_baseline", "random_forest", "xgboost"):
            mask = data["labelled"]
            y = (data["kind"][mask] == "fall").astype(int)
            got = from_counts(counts(y, data[f"alarm_{name}"][mask]))
            self.assertEqual(got["confusion_matrix"], report[name]["nested_threshold"]["confusion_matrix"])

    def test_every_model_is_compared_on_the_same_candidates_and_no_synthetic_data_is_declared(self):
        metrics = json.loads(METRICS.read_text(encoding="utf-8"))
        self.assertEqual(metrics["protocol"]["synthetic_data"], "none")
        totals = {tuple(sum(m["nested_threshold"]["confusion_matrix"], [])[i] for i in range(4)) for m in metrics["models"].values()}
        self.assertEqual({sum(t) for t in totals}, {metrics["candidate_counts"]["labelled"]})

    def test_the_exported_model_is_experimental_and_reproduces_the_fixture(self):
        from fall_detection.export_model import evaluate_exported
        file = json.loads(MODEL.read_text(encoding="utf-8"))
        self.assertEqual((file["status"], file["deployment_approved"]), ("experimental", False))
        self.assertEqual(file["feature_order"], FEATURE_ORDER)
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        X = np.array([w["features"] for w in fixture["windows"]])
        np.testing.assert_allclose(evaluate_exported(file["xgboost"], X), [w["probability"] for w in fixture["windows"]], atol=1e-5)


if __name__ == "__main__":
    unittest.main()
