import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from fatigue_source_transitions import FEATURES, OUTPUTS, TransitionBorg, add_features, build_pairs, fit_teachers


class SourceTransitionTests(unittest.TestCase):
    def fixture(self):
        sources, manifests, splits = {}, {}, {}
        for domain in ("worker", "sts"):
            data, lineage = [], []
            for person in range(6):
                for rep in range(1, 5):
                    key = f"{domain}-{person}-{rep}"
                    target = float(rep+person%2)+(.5 if domain == "sts" else 0.)
                    data.append({"row_key": key, "group_key": f"{domain}-{person}", "borg_native": target,
                        "hr_last": 90.+rep*4+person, "hr_history_mean": 90.+rep+person,
                        "prior_borg": float(rep-1+person%2)+.5 if domain == "sts" and rep > 1 else np.nan})
                    lineage.append({"row_key": key, "questionnaire_worksheet_row": person+2,
                        "questionnaire_column": f"What is your physical fatigue level currently [REP {rep}] ?",
                        "member": f"{domain}-{person}", "response_time_seconds": rep*120.,
                        "prior_response_time_seconds": (rep-1)*120. if rep > 1 else None})
            sources[domain] = pd.DataFrame(data)
            manifests[domain] = {"lineage": lineage}
            splits[domain] = {"train_row_keys": [r["row_key"] for r in data], "test_row_keys": [domain+"-reserved"], "test_groups": [domain+"-reserved"]}
        return sources, manifests, splits

    def test_actual_adjacent_reports_and_fractional_outcomes_are_preserved_without_timestamps(self):
        sources, manifests, splits = self.fixture()
        data, counts = build_pairs(sources, manifests, splits)
        self.assertEqual(len(data), 36)
        self.assertEqual(counts["sts"]["fractional_targets"], 18)
        self.assertTrue((data[data.source_domain.eq("sts")].borg_native % 1 == .5).all())
        self.assertEqual(set(data), {"source_domain", "row_key", "prior_row_key", "group_key", "prior_borg", "borg_native", "hr_last", "hr_history_mean"})
        self.assertFalse(any("time" in col or "age" in col for col in data))

    def test_missing_previous_survey_does_not_create_a_label_and_reserved_people_are_rejected(self):
        sources, manifests, splits = self.fixture()
        sources["worker"] = sources["worker"][~sources["worker"].row_key.eq("worker-0-2")]
        splits["worker"]["train_row_keys"] = sources["worker"].row_key.tolist()
        data, _ = build_pairs(sources, manifests, splits)
        self.assertNotIn("worker-0-3", data.row_key.tolist())
        splits["worker"]["test_groups"].append("worker-1")
        with self.assertRaisesRegex(ValueError, "reserved"):
            build_pairs(sources, manifests, splits)

    def test_later_survey_changes_cannot_change_previous_input_and_context_must_match(self):
        sources, manifests, splits = self.fixture()
        expected, _ = build_pairs(sources, manifests, splits)
        sources["worker"].loc[sources["worker"].row_key.eq("worker-0-4"), "borg_native"] = 10.
        changed, _ = build_pairs(sources, manifests, splits)
        pd.testing.assert_frame_equal(expected[expected.row_key.eq("worker-0-3")], changed[changed.row_key.eq("worker-0-3")])
        self.assertEqual(changed.loc[changed.row_key.eq("worker-0-4"), "prior_borg"].item(), 3.)
        sources["sts"].loc[sources["sts"].row_key.eq("sts-0-3"), "prior_borg"] = 0.
        with self.assertRaisesRegex(ValueError, "disagrees"):
            build_pairs(sources, manifests, splits)

    def test_source_only_teachers_and_serialized_native_model_require_no_query_labels(self):
        data, _ = build_pairs(*self.fixture())
        teachers = fit_teachers(data, "ridge")
        frame = pd.DataFrame({"prior_borg": np.tile([1., 2., 3., 4.], 6), "prior_age_minutes": 5.,
            "terrain_stairs": 0, "terrain_ramp": 1, "terrain_flat_trail": 0,
            "hr_last": np.arange(24.)+95, "hr_history_mean": np.arange(24.)+91,
            "label": [f"Borg {i%4+1+(i//4)%2}" for i in range(24)], "row_key": "unused", "group_key": "unused"})
        specifications = {"core": {"features": ["prior_borg", "prior_age_minutes"], "algorithm": "mlp", "target_mode": "change_from_prior",
            "params": {"hidden_layer_sizes": [4, 3], "alpha": 10., "solver": "lbfgs", "max_iter": 1000}}}
        candidate = {"id": "fixture", "member": "core", "algorithm": "ridge"}
        before = add_features(frame, teachers)[OUTPUTS]
        model = TransitionBorg(candidate, teachers).fit(frame, specifications)
        predicted = model.predict(frame)
        pd.testing.assert_frame_equal(add_features(frame, teachers)[OUTPUTS], before)
        np.testing.assert_array_equal(model.predict(frame[model.input_features]), predicted)
        np.testing.assert_array_equal(model.predict(frame.assign(label="unavailable", row_key="changed", group_key="changed")), predicted)
        self.assertEqual(set(vars(model)), {"candidate", "teachers", "input_features", "model"})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"transition.joblib"
            joblib.dump(model, path)
            np.testing.assert_array_equal(joblib.load(path).predict(frame[model.input_features]), predicted)


if __name__ == "__main__":
    unittest.main()
