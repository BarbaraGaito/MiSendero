"""Single source of truth for the signal contract shared by Python and the app.

`services/fallDetection/modelContract.json` is generated from these values by
`export_model.py`; the TypeScript pipeline must never hard-code them.
"""
from __future__ import annotations

SAMPLE_RATE_HZ = 50                 # UniMiB SHAR was recorded at exactly 20 ms per sample
STANDARD_GRAVITY = 9.80665          # dataset is in m/s^2; the app (expo-sensors) delivers g
# Candidate detection (deterministic rule, not a model decision).
GATE_G = 1.5                        # magnitude that makes a sample an impact candidate
NEIGHBOURHOOD = 20                  # a candidate must be the strict-first maximum within +-0.4 s
# Window around the candidate peak. Chosen from data coverage (see audit), not from model score:
# fall records are cropped tightly (median 1.4 s after impact) and the posture-change ADL records are
# 2 s repetitions separated by recording gaps, so a longer window would silently discard most of the
# hardest negatives. 0.8 s before / 0.4 s after keeps 99.3 % of fall impacts and 84.8 % of posture peaks.
PRE_SAMPLES = 40                    # 0.8 s before the peak
POST_SAMPLES = 20                   # 0.4 s after the peak (>= NEIGHBOURHOOD so streaming can decide at peak+20)
WINDOW = PRE_SAMPLES + 1 + POST_SAMPLES
PEAK_INDEX = PRE_SAMPLES
COOLDOWN_SECONDS = 30               # deterministic rule in the app, not tuned here

FALL_ACTIVITIES = ["FallingForw", "FallingBack", "FallingRight", "FallingLeft",
                   "Syncope", "FallingBackSC", "FallingWithPS", "HittingObstacle"]
ADL_ACTIVITIES = ["Walking", "Running", "GoingUpS", "GoingDownS", "Jumping",
                  "SittingDown", "StandingUpFS", "LyingDownFS", "StandingUpFL"]
