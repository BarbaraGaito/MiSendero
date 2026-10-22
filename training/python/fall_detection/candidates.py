"""Impact-candidate extraction equivalent to the streaming rule used in the app.

A sample p is a candidate when its magnitude exceeds GATE_G and it is the first maximum inside
[p - NEIGHBOURHOOD, p + NEIGHBOURHOOD] (everything on the left is strictly lower, everything on the
right is lower or equal). The app can decide as soon as sample p + NEIGHBOURHOOD arrives and
classifies once p + POST_SAMPLES is available (POST_SAMPLES >= NEIGHBOURHOOD).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import GATE_G, NEIGHBOURHOOD, POST_SAMPLES, PRE_SAMPLES, WINDOW
from .dataset import Record
from .features import FEATURE_ORDER, magnitude, window_features


def candidate_peaks(m: np.ndarray, gate: float = GATE_G, neighbourhood: int = NEIGHBOURHOOD) -> list[int]:
    peaks = []
    for p in range(len(m)):
        if m[p] <= gate:
            continue
        lo, hi = max(0, p - neighbourhood), min(len(m), p + neighbourhood + 1)
        if np.all(m[lo:p] < m[p]) and np.all(m[p + 1:hi] <= m[p]):
            peaks.append(p)
    return peaks


@dataclass
class Candidate:
    record_index: int
    participant: int
    activity: str
    kind: str
    trial: int
    pocket: str
    peak: int
    peak_g: float
    main_impact: bool        # the global maximum of a fall segment
    has_window: bool         # enough real samples before and after the peak


def extract_candidates(records: list[Record], gate: float = GATE_G) -> tuple[list[Candidate], np.ndarray]:
    candidates: list[Candidate] = []
    rows: list[np.ndarray] = []
    for index, record in enumerate(records):
        m = magnitude(record.xyz_g)
        global_peak = int(np.argmax(m))
        for peak in candidate_peaks(m, gate):
            has_window = peak >= PRE_SAMPLES and peak + POST_SAMPLES < len(m)
            candidates.append(Candidate(index, record.participant, record.activity, record.kind, record.trial,
                                        record.pocket, peak, float(m[peak]),
                                        record.kind == "fall" and peak == global_peak, has_window))
            if has_window:
                rows.append(window_features(record.xyz_g[peak - PRE_SAMPLES:peak + POST_SAMPLES + 1]))
            else:
                rows.append(np.full(len(FEATURE_ORDER), np.nan))
    return candidates, np.vstack(rows)
