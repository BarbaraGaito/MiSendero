"""Untrusted training paths must be refused before reading or creating data."""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import train as training
from ranking import sha256
from test_ranking import fixture, training_paths


class TrainingPathTests(unittest.TestCase):
    def test_manifest_rejects_paths_in_preparation_checksum_before_creating_artifacts(self):
        with tempfile.TemporaryDirectory() as name, training_paths(Path(name)) as (data, artifacts):
            catalog, prepared, _ = fixture(data, count=0)
            manifest_path = prepared / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for value in ("../../outside/model.joblib", "file:///outside", {"filename": "../outside"}):
                with self.subTest(value=value):
                    manifest_path.write_text(json.dumps({**manifest, "preparationCodeSha256": value}), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "Invalid preparation code checksum"):
                        training.train(catalog, prepared, artifacts / "new-version", synthetic_test=True)
                    self.assertFalse((artifacts / "new-version").exists())

    def assert_refused_before_data_io(self, catalog, prepared, output):
        with ExitStack() as stack:
            for method in ("read_bytes", "read_text", "write_bytes", "write_text", "mkdir"):
                stack.enter_context(patch.object(Path, method, side_effect=AssertionError("Data I/O before path validation")))
            stack.enter_context(patch.object(training.joblib, "dump", side_effect=AssertionError("Artifact write before path validation")))
            with self.assertRaises(ValueError):
                training.train(catalog, prepared, output, synthetic_test=True)

    def test_sha256_hashes_bytes_without_opening_paths(self):
        payload = b"catalog\r\n"
        with patch.object(Path, "read_bytes", side_effect=AssertionError("Hashing must not open files")):
            self.assertEqual(sha256(payload), hashlib.sha256(payload).hexdigest())
            with self.assertRaises(TypeError):
                sha256(Path("untrusted-catalog.json"))

    def test_absolute_and_relative_paths_inside_trusted_roots_are_supported(self):
        for relative in (False, True):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as name:
                root = Path(name).resolve()
                with training_paths(root) as (data, artifacts):
                    catalog, prepared, _ = fixture(data, count=0)
                    # Hash raw CRLF bytes, without platform newline translation.
                    payload = json.dumps({"candidates": [{"trailId": i + 1} for i in range(30)]}, indent=2).replace("\n", "\r\n").encode()
                    catalog.write_bytes(payload)
                    manifest_file = prepared / "manifest.json"
                    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                    manifest["catalogSha256"] = sha256(payload)
                    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
                    output = artifacts / "new-version"
                    previous = Path.cwd()
                    try:
                        if relative:
                            os.chdir(root)
                            args = [path.relative_to(root) for path in (catalog, prepared, output)]
                        else:
                            args = [catalog, prepared, output]
                        report = training.train(*args, synthetic_test=True)
                    finally:
                        os.chdir(previous)
                    self.assertEqual(report["status"], "insufficient_real_data")
                    self.assertFalse(report["trained"])
                    self.assertTrue((output / "training-status.json").is_file())

    def test_absolute_parent_traversal_and_sibling_prefix_escapes_are_refused(self):
        with tempfile.TemporaryDirectory() as name, training_paths(Path(name)) as (data, artifacts):
            root = Path(name)
            catalog, prepared, _ = fixture(data, count=0)
            output = artifacts / "new-version"
            cases = {
                "absolute catalog": (root / "outside/catalog.json", prepared, output),
                "absolute prepared": (catalog, root / "outside/prepared", output),
                "absolute output": (catalog, prepared, root / "outside/version"),
                "parent catalog": (data / "../outside/catalog.json", prepared, output),
                "parent prepared": (catalog, data / "../outside/prepared", output),
                "parent output": (catalog, prepared, artifacts / "../outside/version"),
                "catalog sibling prefix": (root / "data-other/catalog.json", prepared, output),
                "prepared sibling prefix": (catalog, root / "data-other/prepared", output),
                "output sibling prefix": (catalog, prepared, root / "artifacts-other/version"),
                "catalog in artifact root": (artifacts / "catalog.json", prepared, output),
                "output in data root": (catalog, prepared, data / "new-version"),
            }
            for label, args in cases.items():
                with self.subTest(path=label):
                    self.assert_refused_before_data_io(*args)
            self.assertFalse((root / "outside").exists())
            self.assertFalse((root / "artifacts-other").exists())

    def test_every_input_and_output_is_checked_after_canonical_resolution(self):
        # Deterministic coverage on Windows hosts that forbid creating symlinks.
        with tempfile.TemporaryDirectory() as name, training_paths(Path(name)) as (data, artifacts):
            catalog, prepared, _ = fixture(data, count=0)
            output = artifacts / "new-version"
            paths = [catalog, prepared, prepared / "manifest.json", prepared / "examples.jsonl",
                     output, output / "model.joblib", output / "metadata.json", output / "training-status.json"]
            original_resolve = Path.resolve
            for escaped in paths:
                def redirected(path, *args, **kwargs):
                    if path == escaped:
                        return Path(name) / "outside" / escaped.name
                    return original_resolve(path, *args, **kwargs)

                with self.subTest(path=escaped.name), patch.object(Path, "resolve", autospec=True, side_effect=redirected):
                    self.assert_refused_before_data_io(catalog, prepared, output)

    def test_redirecting_a_trusted_root_does_not_change_the_allowed_boundary(self):
        with tempfile.TemporaryDirectory() as name, training_paths(Path(name)) as (data, artifacts):
            catalog, prepared, _ = fixture(data, count=0)
            original_resolve = Path.resolve
            for redirected_root in (data, artifacts):
                def redirected(path, *args, **kwargs):
                    if path.is_relative_to(redirected_root):
                        return Path(name) / "outside" / path.relative_to(redirected_root)
                    return original_resolve(path, *args, **kwargs)

                with self.subTest(root=redirected_root.name), patch.object(Path, "resolve", autospec=True, side_effect=redirected):
                    self.assert_refused_before_data_io(catalog, prepared, artifacts / "new-version")

    def test_real_symlinks_cannot_redirect_inputs_roots_or_artifact_destinations(self):
        with tempfile.TemporaryDirectory() as name:
            target = Path(name) / "target"
            target.mkdir()
            try:
                (Path(name) / "probe").symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"OS does not permit symbolic links ({type(error).__name__}); canonical-resolution mocks cover escapes")

        scenarios = ("catalog", "prepared", "manifest", "examples", "output", "output_parent",
                     "model.joblib", "metadata.json", "training-status.json",
                     "dangling-model.joblib", "dangling-metadata.json", "dangling-training-status.json",
                     "data_root", "artifacts_root")
        for scenario in scenarios:
            with self.subTest(path=scenario), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                with training_paths(root) as (data, artifacts):
                    catalog, prepared, _ = fixture(data, count=0)
                    output = artifacts / "new-version"
                    outside = root / "outside"
                    outside.mkdir()
                    sentinel = outside / "sentinel"
                    sentinel.write_bytes(b"preserve external bytes")
                    if scenario == "catalog":
                        catalog.unlink()
                        catalog.symlink_to(sentinel)
                    elif scenario == "prepared":
                        prepared.rename(outside / "prepared")
                        prepared.symlink_to(outside / "prepared", target_is_directory=True)
                    elif scenario in ("manifest", "examples"):
                        link = prepared / ("manifest.json" if scenario == "manifest" else "examples.jsonl")
                        link.unlink()
                        link.symlink_to(sentinel)
                    elif scenario == "output":
                        output.symlink_to(outside, target_is_directory=True)
                    elif scenario == "output_parent":
                        link = artifacts / "linked-parent"
                        link.symlink_to(outside, target_is_directory=True)
                        output = link / "new-version"
                    elif scenario in ("data_root", "artifacts_root"):
                        link = data if scenario == "data_root" else artifacts
                        destination = outside / link.name
                        link.rename(destination)
                        link.symlink_to(destination, target_is_directory=True)
                    else:
                        output.mkdir()
                        dangling = scenario.startswith("dangling-")
                        filename = scenario.removeprefix("dangling-")
                        (output / filename).symlink_to(outside / "missing" if dangling else sentinel)
                    original_files = {path.relative_to(outside): path.read_bytes() for path in outside.rglob("*") if path.is_file()}
                    self.assert_refused_before_data_io(catalog, prepared, output)
                    self.assertEqual(original_files, {path.relative_to(outside): path.read_bytes() for path in outside.rglob("*") if path.is_file()})
                    self.assertFalse((outside / "missing").exists())
                    self.assertFalse((outside / "training-status.json").exists())


if __name__ == "__main__":
    unittest.main()
