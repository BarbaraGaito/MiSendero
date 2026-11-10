"""Compute the final frozen recipe ahead of the sequential trainer.

Only per-fold cache files are written. The live trainer still owns selection,
metric calculation and winner selection. No algorithm or parameter changes.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import torch
from sklearn.model_selection import GroupKFold

import fatigue_runner_transfer as runner
from public_sources import digest


def precompute():
    _, train, _, _, _, members, _, _, _, _, windows, evidence = runner.load_inputs()
    signature = runner.fingerprint(members, evidence)
    path = runner.DIRECTORY / "selection.json"
    selection = json.loads(path.read_text())
    if any(selection.get(k) != v for k, v in signature.items()) or selection["plan"] != runner.plan():
        raise ValueError("The frozen recipe or source changed")
    candidate = selection["plan"][-1]
    if candidate["id"] != "runner-transfer-016":
        raise ValueError("This helper is restricted to the inspected final recipe")
    encoder_path = runner.DIRECTORY / "encoders" / (candidate["encoder"]["id"]+".joblib")
    descriptor = json.loads(encoder_path.with_suffix(".json").read_text())
    if descriptor["signature"] != signature or descriptor["model_sha256"] != digest(encoder_path):
        raise ValueError("Fitting-only source encoder changed")
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    encoder = joblib.load(encoder_path)
    for number, (fit, val) in enumerate(GroupKFold(n_splits=5).split(train, groups=train["group_key"])):
        current = json.loads(path.read_text())
        if current["status"] == "complete" or len(current["results"]) >= len(current["plan"])-1:
            print("The sequential trainer reached the final recipe; yield cache ownership", flush=True)
            return
        fitting, validation = train.iloc[fit], train.iloc[val]
        identity = {"signature": signature, "candidate": candidate,
                    "fit_row_keys": fitting["row_key"].tolist(), "validation_row_keys": validation["row_key"].tolist()}
        output = runner.DIRECTORY / "folds" / f"{candidate['id']}-fold-{number}.json"
        if output.exists():
            previous = json.loads(output.read_text())
            if any(previous.get(k) != v for k, v in identity.items()):
                raise ValueError("Existing final-recipe cache changed")
            continue
        model = runner.RunnerTransferBorg(candidate, encoder).fit(fitting, windows[fitting.index], members["member_specifications"])
        predicted = model.predict(validation, windows[validation.index]).tolist()
        if output.exists():
            previous = json.loads(output.read_text())
            if any(previous.get(k) != v for k, v in identity.items()):
                raise ValueError("Another producer used different fitting data")
            np.testing.assert_array_equal(previous["predicted"], predicted)
        else:
            saved = {**identity, "predicted": predicted, "parallel_cache_producer_code_sha256": digest(Path(__file__))}
            temporary = output.with_suffix(".parallel.tmp")
            temporary.write_text(json.dumps(saved, indent=2)+"\n", encoding="utf-8")
            temporary.replace(output)
        print(f"Final frozen recipe independently computed fold {number+1}/5", flush=True)


if __name__ == "__main__":
    precompute()
