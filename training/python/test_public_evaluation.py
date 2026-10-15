"""Regression checks against group leakage and tampered real-data evidence."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import public_sources
from train_public import group_split, grouped_cv
from validate_public import validate


class PublicEvaluationTests(unittest.TestCase):
    def test_group_holdout_keeps_all_windows_together(self):
        # Artificial unit-test fixture only; never included in training artifacts.
        frame = pd.DataFrame({"group_key": [str(i // 3) for i in range(36)]})
        a, b = group_split(frame)
        self.assertFalse(set(frame.iloc[a]["group_key"]) & set(frame.iloc[b]["group_key"]))
        self.assertEqual(set(a) | set(b), set(range(len(frame))))
        self.assertEqual(group_split(frame)[1].tolist(), b.tolist())

    def test_small_group_count_never_falls_back_to_row_split(self):
        with self.assertRaisesRegex(ValueError, "four independent groups"):
            group_split(pd.DataFrame({"group_key": ["one"] * 100}))

    def test_augmentation_is_rebuilt_inside_cv_training_only(self):
        x = pd.DataFrame({"hr": list(range(70, 94))})
        y = pd.Series(["observed-A", "observed-B"] * 12)
        groups = pd.Series([str(i // 2) for i in range(24)])
        original = x.copy(deep=True)
        calls = []
        from common.augment import augment_dataset as actual
        def spy(rows, *args, **kwargs):
            calls.append(set(rows["hr"]))
            return actual(rows, *args, **kwargs)
        with patch("train_public.augment_dataset", side_effect=spy):
            result = grouped_cv(x, y, groups, {"n_estimators": 5, "max_depth": 2, "min_samples_leaf": 2}, True)
        self.assertEqual(len(calls), result["folds"])
        for fold, used in zip(result["partitions"], calls):
            validation = set(fold["validation_groups"])
            validation_values = set(x.loc[groups.isin(validation), "hr"])
            self.assertFalse(used & validation_values)
            self.assertGreater(fold["synthetic_training_rows"], 0)
        pd.testing.assert_frame_equal(x, original)

    def test_changed_public_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            raw = base / "raw"
            out = base / "out"
            (raw / "osm").mkdir(parents=True)
            out.mkdir()
            (out / "source_catalog.json").write_text("{}")
            (raw / "osm/map_one.xml").write_text("modified")
            lock = {"catalog_sha256": public_sources.digest(out / "source_catalog.json"),
                    "files": [{"path": "osm/map_one.xml", "sha256": "wrong"}]}
            (out / "sources.lock.json").write_text(json.dumps(lock))
            with patch.object(public_sources, "RAW", raw), patch.object(public_sources, "OUTPUT", out):
                with self.assertRaisesRegex(ValueError, "changed public source"):
                    public_sources.verify_source_snapshot("route_difficulty")

    def test_committed_metrics_match_original_labels_and_sealed_groups(self):
        for model in public_sources.ADAPTERS:
            with self.subTest(model=model):
                if not all((public_sources.RAW / entry["path"]).exists() for entry in json.loads((public_sources.OUTPUT / "sources.lock.json").read_text())["files"]):
                    self.skipTest("Raw public downloads absent; run fetch:ai-data before source validation")
                validate(model)


if __name__ == "__main__":
    unittest.main()
