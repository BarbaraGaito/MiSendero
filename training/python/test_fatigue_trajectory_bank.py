import unittest

import numpy as np
import pandas as pd

from fatigue_trajectory_bank import fit_bank, native_probabilities, packed_query, predict_query, query_for
from public_sources import group_key


class TrajectoryBankTests(unittest.TestCase):
    def inputs(self):
        start = pd.Timestamp("2020-01-01T12:00Z")
        task = {"label": "flat_trail", "start_time": start.isoformat(), "end_time": (start + pd.Timedelta(minutes=20)).isoformat()}
        session = {"start_time": start.isoformat(), "end_time": task["end_time"], "tasks": [task]}
        reports = pd.DataFrame({"time": [start + pd.Timedelta(minutes=t) for t in (0, 5, 10, 15)],
                                "id": ["p1"] * 4, "task": [1] * 4, "task_label": ["flat_trail"] * 4, "borg_scale": [0., 2., 4., 6.]})
        return start, task, session, reports

    def test_current_and_future_ratings_never_enter_query_feedback(self):
        start, task, session, reports = self.inputs()
        now = start + pd.Timedelta(minutes=10)
        expected = query_for(reports, session, task, now, 2., 5.)
        changed = reports.copy()
        changed.loc[changed["time"] >= now, "borg_scale"] = 10.
        self.assertEqual(query_for(changed, session, task, now, 2., 5.), expected)
        self.assertEqual(len(expected["history"]), 2)

    def test_bank_fit_excludes_unseen_people_and_does_not_create_supervision(self):
        start, task, session, reports = self.inputs()
        second = reports.assign(id="p2", borg_scale=10.)
        bank = fit_bank(pd.concat([reports, second], ignore_index=True), {"p1": [session], "p2": [session]}, {group_key("GeoFatigue:p1")})
        self.assertEqual(bank["fit_groups"], [group_key("GeoFatigue:p1")])
        self.assertEqual(len(bank["actual_active_response_rows"]), 4)
        self.assertEqual(bank["interpolated_supervision_rows"], 0)
        query = query_for(reports, session, task, start + pd.Timedelta(minutes=10), 2., 5.)
        recipe = {"scope": "current_task", "memory_minutes": None, "bias_shrinkage": 4., "observation_sigma": .25, "prediction_sigma": .25}
        self.assertEqual(predict_query(bank, query, recipe), "Borg 4")

    def test_quantization_probabilities_include_native_edges_and_require_real_prior(self):
        probabilities = native_probabilities(np.array([-5., 3., 15.]), .25)
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.)
        self.assertEqual(probabilities.argmax(axis=1).tolist(), [0, 3, 10])
        start, task, session, reports = self.inputs()
        bank = fit_bank(reports, {"p1": [session]}, {group_key("GeoFatigue:p1")})
        query = query_for(reports, session, task, start + pd.Timedelta(minutes=10), 2., 5.)
        for age in (0., -1., 16.):
            with self.subTest(age=age), self.assertRaises(ValueError):
                packed_query(bank, {**query, "prior_age_minutes": age}, "current_task")


if __name__ == "__main__":
    unittest.main()
