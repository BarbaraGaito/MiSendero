"""Orientation-invariant window features.

The same arithmetic is re-implemented in `services/fallDetection/features.ts`; keep both in sync and
verify them with `export_model.py` golden vectors. Inputs are in g with gravity included. Only
quantities derived from the acceleration magnitude, or from angles between mean gravity vectors, are
used because the phone orientation inside a pocket (or backpack) is not known and iOS/Android axis
conventions differ.
"""
from __future__ import annotations

import numpy as np

from .config import PEAK_INDEX, SAMPLE_RATE_HZ, WINDOW

# Segment boundaries inside a window of 61 samples whose peak is sample 40.
PRE_FAR = (0, 25)        # -0.80 .. -0.32 s
PRE_NEAR = (25, 36)      # -0.30 .. -0.08 s
IMPACT = (36, 45)        # peak +- 4 samples
POST = (45, 61)          # +0.10 .. +0.40 s
FREE_FALL = (10, 40)     # -0.60 .. -0.02 s
FREE_FALL_THRESHOLD_G = 0.6
PEAK_COUNT_THRESHOLD_G = 1.3
STILL_TOLERANCE_G = 0.15

_SEGMENTS = {"pre_far": PRE_FAR, "pre_near": PRE_NEAR, "impact": IMPACT, "post": POST}

FEATURE_ORDER: list[str] = (
    ["m_mean", "m_std", "m_min", "m_max", "m_range"]
    + [f"{name}_{stat}" for name in _SEGMENTS for stat in ("mean", "std", "min", "max")]
    + ["energy_all", "energy_pre", "energy_post", "peak_over_pre_rms",
       "freefall_min", "freefall_samples", "jerk_max", "jerk_mean", "jerk_impact",
       "peaks_all", "peaks_pre", "angle_deg", "gravity_pre", "gravity_post",
       "post_dev_mean", "post_still_fraction"]
)


def magnitude(xyz: np.ndarray) -> np.ndarray:
    return np.sqrt(np.sum(xyz * xyz, axis=-1))


def _local_max_count(m: np.ndarray, start: int, stop: int, threshold: float) -> int:
    count = 0
    for i in range(max(start, 1), min(stop, len(m) - 1)):
        if m[i] > threshold and m[i] > m[i - 1] and m[i] >= m[i + 1]:
            count += 1
    return count


def window_features(window: np.ndarray) -> np.ndarray:
    """`window` is (61, 3) in g; returns features in FEATURE_ORDER (float64)."""
    if window.shape != (WINDOW, 3):
        raise ValueError(f"window must be ({WINDOW}, 3)")
    m = magnitude(window)
    out: list[float] = [m.mean(), m.std(), m.min(), m.max(), m.max() - m.min()]
    for a, b in _SEGMENTS.values():
        seg = m[a:b]
        out += [seg.mean(), seg.std(), seg.min(), seg.max()]
    dev = m - 1.0
    pre_end = IMPACT[0]
    energy_pre = float(np.mean(dev[:pre_end] ** 2))
    out += [float(np.mean(dev ** 2)), energy_pre, float(np.mean(dev[POST[0]:] ** 2)),
            float(m[PEAK_INDEX]) / (np.sqrt(energy_pre) + 0.05)]
    free = m[FREE_FALL[0]:FREE_FALL[1]]
    out += [free.min(), float(np.sum(free < FREE_FALL_THRESHOLD_G))]
    diff = np.abs(np.diff(m)) * SAMPLE_RATE_HZ
    out += [diff.max(), diff.mean(), diff[IMPACT[0] - 4:IMPACT[1] - 1].max()]
    out += [float(_local_max_count(m, 0, WINDOW, PEAK_COUNT_THRESHOLD_G)),
            float(_local_max_count(m, 0, pre_end, PEAK_COUNT_THRESHOLD_G))]
    before = window[PRE_FAR[0]:PRE_FAR[1]].mean(axis=0)
    after = window[POST[0]:POST[1]].mean(axis=0)
    nb, na = float(np.sqrt(np.sum(before * before))), float(np.sqrt(np.sum(after * after)))
    cosine = float(np.dot(before, after)) / (nb * na) if nb > 0 and na > 0 else 1.0
    out += [float(np.degrees(np.arccos(min(1.0, max(-1.0, cosine))))), nb, na]
    post_dev = np.abs(m[POST[0]:POST[1]] - 1.0)
    out += [post_dev.mean(), float(np.mean(post_dev < STILL_TOLERANCE_G))]
    values = np.asarray(out, dtype=np.float64)
    if values.shape[0] != len(FEATURE_ORDER):
        raise AssertionError("feature order out of sync")
    return values
