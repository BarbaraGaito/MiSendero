import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from fatigue_prior_view_training import PriorViewBorg, fitting_views
from fatigue_prior_views import alternative_histories, history_row


class PriorViewTests(unittest.TestCase):
    def fixture(self):
        start = pd.Timestamp("2026-01-01", tz="UTC")
        task = {"label": "ramp", "start_time": start.isoformat(), "end_time": (start+pd.Timedelta(minutes=30)).isoformat()}
        session = {"start_time": (start-pd.Timedelta(minutes=20)).isoformat(), "tasks": [task]}
        reports = pd.DataFrame({"time": [start+pd.Timedelta(minutes=m) for m in (-20, -2, 0, 5, 10, 11)],
                                "borg_scale": [8, 0, 1, 3, 5, 6]})
        return start, task, session, reports

    def test_future_and_out_of_window_reports_never_change_history_inputs(self):
        start, task, session, reports = self.fixture()
        now = start+pd.Timedelta(minutes=10)
        before, past = history_row(reports, session, task, now)
        changed = reports.copy()
        changed.loc[~changed.index.isin(past.index), "borg_scale"] = np.nan
        after, _ = history_row(changed, session, task, now)
        np.testing.assert_allclose(list(before.values()), list(after.values()), rtol=0, atol=0, equal_nan=True)
        self.assertEqual(before["prior_borg"], 3.)
        self.assertEqual(before["prior_age_minutes"], 5.)

    def test_history_subsets_remove_hidden_values_and_never_invent_an_onset(self):
        start, task, session, reports = self.fixture()
        now = start+pd.Timedelta(minutes=10)
        _, past = history_row(reports, session, task, now)
        views = list(alternative_histories(past))
        self.assertEqual(len(views), 6)
        self.assertEqual(sum(prefix for _, prefix in views), 2)
        retained = past.iloc[[0, 2]]
        row, _ = history_row(retained, session, task, now)
        self.assertEqual(row["prior2_borg"], 0.)
        self.assertEqual(row["prior_count_current_task"], 1)
        self.assertAlmostEqual(row["prior_borg_slope"], 3/7)
        single, _ = history_row(past.iloc[:1], session, task, now)
        self.assertTrue(np.isnan(single["prior2_borg"]))
        self.assertEqual(single["prior_in_current_task"], 0)
        with self.assertRaisesRegex(ValueError, "earlier"):
            history_row(reports[reports["time"].ge(now)], session, task, now)

    def weight_fixture(self):
        frame = pd.DataFrame({"row_key": ["a", "b", "c"], "group_key": ["p1", "p1", "p2"], "label": ["Borg 1", "Borg 2", "Borg 3"]})
        views = pd.DataFrame({"target_row_key": ["a", "a", "b", "held"], "group_key": ["p1", "p1", "p1", "held_person"],
                              "label": ["Borg 1", "Borg 1", "Borg 2", "invalid_unavailable_target"],
                              "view_key": ["a1", "a2", "b1", "held1"], "prefix_only": [True, False, True, True]})
        return frame, views

    def test_each_original_report_retains_weight_one_despite_unequal_view_counts(self):
        frame, views = self.weight_fixture()
        data, weights, keys = fitting_views(frame, views, "subsets", .3)
        self.assertEqual(keys, ["a1", "a2", "b1"])
        np.testing.assert_allclose(weights, [.7, .7, 1., .15, .15, .3], rtol=0, atol=1e-12)
        self.assertAlmostEqual(weights.sum(), 3.)
        self.assertNotIn("invalid_unavailable_target", data["label"].tolist())
        self.assertEqual(fitting_views(frame, views, "prefix", .3)[2], ["a1", "b1"])

    def test_selected_view_cannot_change_its_person_or_observed_target(self):
        frame, views = self.weight_fixture()
        for column, value in (("label", "Borg 10"), ("group_key", "another_person")):
            changed = views.copy()
            changed.loc[0, column] = value
            with self.assertRaisesRegex(ValueError, "person/target"):
                fitting_views(frame, changed, "subsets", .3)

    def test_inference_and_serialization_do_not_need_current_labels_or_the_view_pool(self):
        start, task, session, reports = self.fixture()
        feature, _ = history_row(reports, session, task, start+pd.Timedelta(minutes=10))
        frame = pd.DataFrame([{**feature, "prior_borg": float(i % 3), "elapsed_minutes": float(i+1),
                               "row_key": f"q{i}", "group_key": f"p{i//4}", "label": f"Borg {i%3+1}"} for i in range(24)])
        pool = frame.copy().rename(columns={"row_key": "target_row_key"})
        pool["view_key"] = [f"v{i}" for i in range(24)]
        pool["prefix_only"], pool["prior_age_minutes"] = True, 10.
        candidate = {"algorithm": "mlp", "features": list(feature), "view_policy": "subsets", "view_mass": .3,
                     "target_mode": "change_from_prior", "params": {"hidden_layer_sizes": [8], "alpha": 10., "solver": "lbfgs", "max_iter": 1000}}
        model = PriorViewBorg(candidate).fit(frame, pool, {})
        predicted = model.predict(frame)
        changed = frame.copy()
        changed["label"], changed["row_key"], changed["group_key"] = "unavailable", "unused", "unused"
        np.testing.assert_array_equal(predicted, model.predict(changed))
        self.assertEqual(set(vars(model)), {"candidate", "imputer", "scaler", "model", "fit_summary"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"model.joblib"
            joblib.dump(model, path)
            restored = joblib.load(path)
            np.testing.assert_array_equal(restored.predict(frame), predicted)


if __name__ == "__main__":
    unittest.main()
