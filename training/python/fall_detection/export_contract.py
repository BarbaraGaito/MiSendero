"""Write the signal contract consumed by the TypeScript pipeline (never edit the JSON by hand)."""
from __future__ import annotations

import json

from . import config, features
from .dataset import ROOT

TARGET = ROOT / "services/fallDetection/modelContract.json"


def contract() -> dict:
    return {
        "schemaVersion": 1,
        "generatedBy": "training/python/fall_detection/export_contract.py",
        "sampleRateHz": config.SAMPLE_RATE_HZ,
        "standardGravity": config.STANDARD_GRAVITY,
        "gateG": config.GATE_G,
        "neighbourhood": config.NEIGHBOURHOOD,
        "preSamples": config.PRE_SAMPLES,
        "postSamples": config.POST_SAMPLES,
        "window": config.WINDOW,
        "peakIndex": config.PEAK_INDEX,
        "cooldownSeconds": config.COOLDOWN_SECONDS,
        "features": {
            "order": features.FEATURE_ORDER,
            "segments": {"pre_far": features.PRE_FAR, "pre_near": features.PRE_NEAR,
                         "impact": features.IMPACT, "post": features.POST},
            "freeFall": features.FREE_FALL,
            "freeFallThresholdG": features.FREE_FALL_THRESHOLD_G,
            "peakCountThresholdG": features.PEAK_COUNT_THRESHOLD_G,
            "stillToleranceG": features.STILL_TOLERANCE_G,
        },
    }


if __name__ == "__main__":
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(contract(), indent=2) + "\n", encoding="utf-8")
    print("wrote", TARGET)
