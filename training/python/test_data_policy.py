"""Execute policy preflight even without ML dependencies."""
import subprocess
import sys
import unittest
from pathlib import Path
from common.data_policy import REJECTED_RECIPES, require_public_ground_truth
ROOT = Path(__file__).resolve().parent

class RealDataPolicyTests(unittest.TestCase):
    def test_legacy_and_unknown_recipes_reject(self):
        for recipe in [*REJECTED_RECIPES, "new_source"]:
            with self.subTest(recipe=recipe):
                with self.assertRaisesRegex(ValueError, "Real evaluation unavailable"):
                    require_public_ground_truth(recipe)

    def test_cli_preflight(self):
        commands = [[ROOT / name / "train.py"] for name in REJECTED_RECIPES]
        commands.append([ROOT / "build_datasets.py", "--write"])
        for command in commands:
            with self.subTest(command=command):
                result = subprocess.run([sys.executable, *map(str, command)], capture_output=True, text=True, timeout=15)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Real evaluation unavailable", result.stderr)
                self.assertNotIn("ModuleNotFoundError", result.stderr)

if __name__ == "__main__":
    unittest.main()
