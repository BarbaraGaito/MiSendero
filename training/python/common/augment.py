"""Deterministic synthetic augmentation for the tiny MiSendero training CSVs.

The thesis (section 2.1.6.3) documents that, absent bundled access to real
public wearable/trekking datasets (PAMAP2, WESAD, BIDMC), the offline models
in this academic prototype are trained on a mix of a handful of real sample
rows plus synthetic data generated from physiologically-validated
distributions around those samples. This module implements exactly that,
disclosed limitation: it is not a substitute for real data collection, it is
the documented stand-in used because real datasets are not shipped with the
repository.

Rows are synthesized by adding Gaussian noise to each real row's feature
values, conditioned on that row's label, so every generated point stays close
to a real, labeled observation rather than drifting into an unrelated region
of feature space. A fixed random seed keeps `npm run train:ai` reproducible
across machines.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RANDOM_SEED = 42

# Relative noise (as a fraction of each feature's overall standard deviation)
# and physically sane lower bounds. Values below reflect the units used
# throughout the app's CSVs (heart rate in bpm, speed in km/h, minutes,
# meters, and small integer scores), not a general-purpose default.
_NOISE_FRACTION_OF_STD = 0.18
_MIN_CLIP_BY_FEATURE = {
    "hr": 40.0,
    "speed_kmh": 0.0,
    "elapsed_minutes": 0.0,
    "hr_reserve_percent": 0.0,
    "elevation_gain_m": 0.0,
    "fatigue_score": 1.0,
    "distance_km": 0.0,
    "avg_slope_percent": 0.0,
    "max_slope_percent": 0.0,
    "technical_score": 1.0,
}


def augment_dataset(
    df: pd.DataFrame,
    label_col: str,
    feature_cols: list[str],
    target_rows_per_label: int = 80,
) -> pd.DataFrame:
    """Expand `df` so each label reaches `target_rows_per_label` rows.

    Every synthetic row is a real row's feature vector plus per-feature
    Gaussian noise scaled to that feature's overall spread, clipped to a
    physically reasonable minimum. The original rows are always kept and are
    included unmodified in the returned frame.
    """
    rng = np.random.default_rng(RANDOM_SEED)

    feature_std = {
        column: max(float(df[column].std(ddof=0)), 1e-6) for column in feature_cols
    }

    synthetic_rows: list[dict] = []

    for label, group in df.groupby(label_col):
        real_rows = group.to_dict("records")
        rows_needed = max(0, target_rows_per_label - len(real_rows))

        for _ in range(rows_needed):
            base_row = real_rows[rng.integers(0, len(real_rows))]
            synthetic_row = dict(base_row)

            for column in feature_cols:
                noise_scale = feature_std[column] * _NOISE_FRACTION_OF_STD
                noisy_value = float(base_row[column]) + rng.normal(0.0, noise_scale)
                lower_bound = _MIN_CLIP_BY_FEATURE.get(column, 0.0)
                synthetic_row[column] = max(lower_bound, noisy_value)

            synthetic_row[label_col] = label
            synthetic_rows.append(synthetic_row)

    if not synthetic_rows:
        return df.reset_index(drop=True)

    augmented = pd.concat([df, pd.DataFrame(synthetic_rows)], ignore_index=True)
    return augmented.reset_index(drop=True)
