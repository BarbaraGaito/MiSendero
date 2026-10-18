"""Synthetic fixtures ONLY test plumbing/math. They are never real accuracy evidence."""
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ranking import SPEC, baseline, components, evaluate, load_artifact, matrix, read_examples, sha256, split_examples
from train import train

ML = Path(__file__).resolve().parents[1]


def fixture(root, *, count=100):
    """No real users, names, geography or consent claims. Keep artifacts in temp dirs."""
    rows = []
    for q in range(count):
        for i in range(3):
            vector = [1, i / 2, 0.5, 60 + q, 2 + i, i, 2, None, None, None, None, None, None, None]
            rows.append({"queryId": f"synthetic_query_{q:04}", "splitGroupId": f"synthetic_group_{q % 20:04}",
                         "preferenceKey": hashlib.sha256(f"synthetic preference {q}".encode()).hexdigest(),
                         "trailId": (q % 10) * 3 + i + 1, "features": vector, "relevance": i,
                         "source": "expert_judgment", "consentVerified": False, "synthetic": True, "eligible": True})
    catalog = root / "catalog.json"
    catalog.write_text(json.dumps({"candidates": [{"trailId": i + 1} for i in range(30)]}), encoding="utf-8")
    prepared = root / "prepared"
    prepared.mkdir()
    examples = prepared / "examples.jsonl"
    examples.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    manifest = {"schemaVersion": 1, "featureSchemaVersion": SPEC["version"], "featureNames": SPEC["names"],
                "synthetic": True, "completeCandidateJudgments": True, "catalogSha256": sha256(catalog),
                "examplesSha256": sha256(examples), "rowCount": len(rows), "catalogSize": 30}
    (prepared / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return catalog, prepared, rows


class RankingTests(unittest.TestCase):
    def test_unknown_values_stay_missing_and_invalid_numbers_are_rejected(self):
        vector = [1, 1, None, 90, 4, 0, 0] + [None] * 7
        self.assertTrue(math.isnan(matrix([vector])[0][7]))
        self.assertEqual(baseline(vector), 5)
        vector[13] = 0
        self.assertEqual(baseline(vector), 6)
        vector[13] = 2
        self.assertEqual(baseline(vector), 5)
        for invalid in [[], [[1]], [[float("nan")] * 14], [[True] * 14], [[1e12] * 14]]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                matrix(invalid)

    def test_metrics_have_known_values_and_stable_ties(self):
        rows = [{"queryId": "synthetic", "trailId": i + 1, "relevance": r, "eligible": True} for i, r in enumerate([3, 0, 2])]
        metrics = evaluate(rows, [3, 2, 1], 6)
        self.assertEqual(metrics["precision@1"], 1)
        self.assertEqual(metrics["precision@3"], 2 / 3)
        self.assertEqual(metrics["recall@1"], 0.5)
        self.assertEqual(metrics["recall@3"], 1)
        self.assertEqual(metrics["ndcg@1"], 1)
        self.assertLess(metrics["ndcg@3"], 1)
        self.assertEqual(metrics["catalog_coverage_at_1"], 1 / 6)
        self.assertEqual(evaluate(rows, [1, 1, 1], 6)["precision@1"], 1)
        zeros = [{**r, "relevance": 0} for r in rows]
        self.assertIsNone(evaluate(zeros, [0, 0, 0], 6)["recall@1"])
        self.assertIsNone(evaluate(zeros, [0, 0, 0], 6)["ndcg@1"])

    def test_synthetic_rows_cannot_enter_the_real_training_path(self):
        with tempfile.TemporaryDirectory() as name:
            catalog, prepared, _ = fixture(Path(name))
            with self.assertRaises(ValueError):
                read_examples(prepared / "examples.jsonl")
            with self.assertRaises(ValueError):
                train(catalog, prepared, Path(name) / "production")

    def test_grouped_holdout_is_reproducible_without_participant_or_preference_overlap(self):
        with tempfile.TemporaryDirectory() as name:
            _, _, rows = fixture(Path(name))
            parts = split_examples(rows)
            self.assertEqual(parts, split_examples(rows))
            self.assertEqual(sum(map(len, parts)), len(rows))
            for a, b in ((0, 1), (0, 2), (1, 2)):
                for key in ("queryId", "splitGroupId", "preferenceKey"):
                    self.assertFalse({r[key] for r in parts[a]} & {r[key] for r in parts[b]})
            copied = {**rows[0], "queryId": "synthetic_duplicate", "splitGroupId": "different_person"}
            membership = components(rows + [copied])
            self.assertEqual(membership[rows[0]["queryId"]], membership[copied["queryId"]])

    def test_no_real_labels_produces_no_model_or_metrics(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            catalog, prepared, _ = fixture(root, count=0)
            manifest_path = prepared / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["synthetic"] = False
            manifest_path.write_text(json.dumps(manifest))
            result = train(catalog, prepared, root / "out")
            self.assertFalse(result["trained"])
            self.assertIsNone(result["metrics"])
            self.assertEqual(result["status"], "insufficient_real_data")
            self.assertFalse((root / "out/model.joblib").exists())

    def test_actual_sklearn_fit_load_and_private_worker_protocol_only_in_explicit_technical_mode(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            catalog, prepared, rows = fixture(root)
            out = root / "technical"
            result = train(catalog, prepared, out, synthetic_test=True)
            self.assertTrue(result["trained"])
            self.assertTrue(result["synthetic"])
            self.assertFalse(result["deployable"])
            with self.assertRaises(ValueError):
                load_artifact(out)
            model, _ = load_artifact(out, synthetic_test=True)
            scores = model.predict(matrix([r["features"] for r in rows[:3]]))
            self.assertGreater(scores[2], scores[0])
            message = json.dumps({"id": 1, "features": [r["features"] for r in rows[:3]]}) + "\n"
            env = {**os.environ, "NODE_ENV": "test", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
            worker = subprocess.run([sys.executable, str(ML / "serve.py"), "--model-dir", str(out), "--synthetic-technical-test"], input=message, text=True, capture_output=True, env=env, timeout=20)
            self.assertEqual(worker.returncode, 0, worker.stderr)
            ready, response = map(json.loads, worker.stdout.splitlines())
            self.assertEqual(ready["featureSchemaVersion"], SPEC["version"])
            self.assertEqual(response["id"], 1)
            self.assertEqual(len(response["scores"]), 3)
            rejected = subprocess.run([sys.executable, str(ML / "serve.py"), "--model-dir", str(out)], input=message, text=True, capture_output=True, env=env, timeout=20)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(rejected.stdout, "")
            env["NODE_ENV"] = "production"
            rejected = subprocess.run([sys.executable, str(ML / "serve.py"), "--model-dir", str(out), "--synthetic-technical-test"], input=message, text=True, capture_output=True, env=env, timeout=20)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(rejected.stdout, "")
            with self.assertRaises(ValueError):
                train(catalog, prepared, out, synthetic_test=True)
            metadata_path = out / "metadata.json"
            original = json.loads(metadata_path.read_text())
            metadata_path.write_text(json.dumps({**original, "sklearnVersion": "incompatible"}))
            with self.assertRaises(ValueError):
                load_artifact(out, synthetic_test=True)
            metadata_path.write_text(json.dumps(original))
            # Check corruption BEFORE unpickling.
            (out / "model.joblib").write_bytes(b"corrupt")
            with self.assertRaises(ValueError):
                load_artifact(out, synthetic_test=True)

    def test_missing_artifact_exits_without_a_protocol_ready_message(self):
        worker = subprocess.run([sys.executable, str(ML / "serve.py"), "--model-dir", "nonexistent-technical-fixture"], capture_output=True, text=True, timeout=20)
        self.assertNotEqual(worker.returncode, 0)
        self.assertEqual(worker.stdout, "")
        self.assertNotIn("nonexistent", worker.stderr)


if __name__ == "__main__":
    unittest.main()
