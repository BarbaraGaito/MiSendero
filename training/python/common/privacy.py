"""Reject training CSVs that carry personal or exact-location columns.

Ports the same header denylist the old JS trainers enforced (see
`ai/datasets/README.md`), so swapping the training pipeline for Python does
not quietly drop that safeguard.
"""

from __future__ import annotations

import re

import pandas as pd

_RESTRICTED_HEADER_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"^name$",
        r"nombre",
        r"^email$",
        r"mail",
        r"^phone$",
        r"telefono",
        r"^dni$",
        r"document",
        r"^id$",
        r"user.?id",
        r"session.?id",
        r"subject",
        r"exact.?lat",
        r"exact.?lng",
        r"exact.?lon",
        r"location",
        r"ubicacion",
        r"^address$",
        r"direccion",
    ]
]


def assert_no_restricted_columns(df: pd.DataFrame, dataset_name: str) -> None:
    restricted = [
        column
        for column in df.columns
        if any(pattern.search(column) for pattern in _RESTRICTED_HEADER_PATTERNS)
    ]

    if restricted:
        raise ValueError(
            f"{dataset_name} contains personal or exact-location fields: {', '.join(restricted)}"
        )
