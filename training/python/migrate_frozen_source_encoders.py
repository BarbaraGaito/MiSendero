"""Repair only module references in this task's own SHA-pinned encoder files.

The original __main__ joblib and descriptor are archived. Every network tensor,
normalization statistic, source prediction and fitting result must survive the
importable-module reserialization exactly. No external pickle is accepted.
"""
from __future__ import annotations

import __main__
import json
from pathlib import Path

import joblib
import numpy as np
import torch

import fatigue_frozen_source_transfer as frozen
from public_sources import digest


def migrate():
    _, _, _, manifest, _ = frozen.spectral_inputs()
    source, evidence = frozen.source_inputs()
    selection = json.loads((frozen.DIRECTORY / "selection.json").read_text())
    signature = frozen.fingerprint(manifest, evidence)
    if selection["status"] != "complete" or any(selection.get(k) != v for k, v in signature.items()):
        raise ValueError("Only the unchanged completed local frozen-source experiment may be migrated")
    aliases = {"FrozenSourceEncoder": frozen.FrozenSourceEncoder, "SourceNetwork": frozen.SourceNetwork}
    if any(hasattr(__main__, name) for name in aliases):
        raise ValueError("Migration requires a clean main module")
    for name, cls in aliases.items():
        setattr(__main__, name, cls)
    try:
        for spec in frozen.source_plan():
            directory = frozen.DIRECTORY / "encoders" / spec["id"]
            model_path, meta_path = directory / "model.joblib", directory / "descriptor.json"
            descriptor = json.loads(meta_path.read_text())
            if descriptor["signature"] != signature or descriptor["candidate"] != spec or digest(model_path) != descriptor["model_sha256"]:
                raise ValueError("Local encoder does not match its pre-existing descriptor")
            if "module_reference_migration" in descriptor:
                print(f"Already migrated {spec['id']}", flush=True)
                continue
            encoder = joblib.load(model_path)
            if type(encoder) is not frozen.FrozenSourceEncoder or type(encoder.model) is not frozen.SourceNetwork:
                raise ValueError("Unexpected local model class")
            # Refit with only the original external fitting rows to establish
            # that resolving the two legacy names does not change semantics.
            refit = frozen.FrozenSourceEncoder(spec).fit(source)
            for key, value in encoder.model.state_dict().items():
                if not torch.equal(value, refit.model.state_dict()[key]):
                    raise ValueError("Legacy encoder differs from independent pretraining")
            np.testing.assert_array_equal(encoder.imputer.statistics_, refit.imputer.statistics_)
            np.testing.assert_array_equal(encoder.scaler.mean_, refit.scaler.mean_)
            archive = directory / "legacy-main-module"
            archive.mkdir(exist_ok=True)
            for name in ("model.joblib", "descriptor.json"):
                original, copy = directory / name, archive / name
                if copy.exists() and copy.read_bytes() != original.read_bytes():
                    raise ValueError("Refuse to replace an earlier module-reference archive")
                if not copy.exists():
                    copy.write_bytes(original.read_bytes())
            replacement = directory / "model.importable.joblib"
            joblib.dump(encoder, replacement)
            restored = joblib.load(replacement)
            for key, value in encoder.model.state_dict().items():
                if not torch.equal(value, restored.model.state_dict()[key]):
                    raise ValueError("Reserialization changed a network tensor")
            np.testing.assert_array_equal(restored.transform(source), encoder.transform(source))
            for name in encoder.domains:
                with torch.no_grad():
                    np.testing.assert_array_equal(restored.model.prediction(restored.transform(source), name),
                                                  encoder.model.prediction(encoder.transform(source), name))
            model_path.write_bytes(replacement.read_bytes())
            replacement.unlink()
            descriptor["module_reference_migration"] = {
                "legacy_model_sha256": digest(archive / "model.joblib"),
                "legacy_descriptor_sha256": digest(archive / "descriptor.json"),
                "migration_code_sha256": digest(Path(__file__)),
                "new_module": "fatigue_frozen_source_transfer", "all_network_tensors_unchanged": True,
                "external_source_outputs_unchanged": True, "independent_external_refit_matches": True}
            descriptor["model_sha256"] = digest(model_path)
            meta_path.write_text(json.dumps(descriptor, indent=2, allow_nan=False)+"\n", encoding="utf-8")
            print(f"Migrated {spec['id']}; all weights and source predictions unchanged", flush=True)
    finally:
        for name in aliases:
            delattr(__main__, name)


if __name__ == "__main__":
    migrate()
