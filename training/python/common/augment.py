"""Deterministic synthetic augmentation for approved training runs.

The production training scripts call this helper only after the real
train/test split. Synthetic rows are added to the training fold, while held-out
test metrics remain calculated on real rows.

Rows are synthesized by interpolating between two real rows of the same
label (SMOTE-style) plus a small amount of Gaussian jitter, so a generated
point stays inside the region actually spanned by real observations instead
of drifting off in one feature while the correlated features stay fixed -
independent per-feature noise around a single row can invent combinations
that never occur together in real trekking data (e.g. a long distance with a
implausibly small elevation gain). When a label has only one real row,
interpolation is impossible and the row falls back to noise-only jitter
around that single point. A fixed random seed keeps approved runs
reproducible across machines.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RANDOM_SEED = 42

# Relative noise (as a fraction of each feature's overall standard deviation)
# and physically sane lower bounds. Values below reflect the units used
# throughout the app's CSVs (heart rate in bpm, speed in km/h, minutes,
# meters, and small integer scores), not a general-purpose default.
# Jitter added on top of an interpolated pair - kept small since the
# interpolation itself is where most of the realistic variation comes from.
_INTERPOLATION_JITTER_FRACTION_OF_STD = 0.06
# Jitter used for the single-real-row fallback, where interpolation isn't
# possible and noise is the only source of variation.
_FALLBACK_NOISE_FRACTION_OF_STD = 0.18
_MIN_CLIP_BY_FEATURE = {
    "hr": 40.0,
    "mean_hr": 40.0,
    "spo2": 50.0,
    "mean_spo2": 50.0,
    "sinuosity": 1.0,
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
_MAX_CLIP_BY_FEATURE = {"hr": 240.0, "mean_hr": 240.0, "spo2": 100.0, "mean_spo2": 100.0}


def _clip(column: str, value: float) -> float:
    return min(_MAX_CLIP_BY_FEATURE.get(column, float("inf")),
               max(_MIN_CLIP_BY_FEATURE.get(column, 0.0), value))


def augment_dataset(
    df: pd.DataFrame,
    label_col: str,
    feature_cols: list[str],
    target_rows_per_label: int = 80,
) -> pd.DataFrame:
    """Expand `df` so each label reaches `target_rows_per_label` rows.

    Each synthetic row interpolates between two distinct real rows of the
    same label plus small jitter, staying inside the real feature-space
    region for that label instead of drifting off in one feature while
    ignoring the others. Labels with a single real row fall back to
    noise-only jitter around that row. The original rows are always kept and
    are included unmodified in the returned frame.
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
            synthetic_row: dict = {}

            if len(real_rows) >= 2:
                first_index, second_index = rng.choice(
                    len(real_rows), size=2, replace=False
                )
                first_row, second_row = real_rows[first_index], real_rows[second_index]
                mix = rng.uniform(0.0, 1.0)

                for column in feature_cols:
                    interpolated = float(first_row[column]) + mix * (
                        float(second_row[column]) - float(first_row[column])
                    )
                    jitter_scale = feature_std[column] * _INTERPOLATION_JITTER_FRACTION_OF_STD
                    synthetic_row[column] = _clip(
                        column, interpolated + rng.normal(0.0, jitter_scale)
                    )
            else:
                base_row = real_rows[0]
                for column in feature_cols:
                    noise_scale = feature_std[column] * _FALLBACK_NOISE_FRACTION_OF_STD
                    noisy_value = float(base_row[column]) + rng.normal(0.0, noise_scale)
                    synthetic_row[column] = _clip(column, noisy_value)

            synthetic_row[label_col] = label
            synthetic_rows.append(synthetic_row)

    if not synthetic_rows:
        return df.reset_index(drop=True)

    augmented = pd.concat([df, pd.DataFrame(synthetic_rows)], ignore_index=True)
    return augmented.reset_index(drop=True)
