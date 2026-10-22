"""Check whether the published PLOS mountain-hiking supplement can test MiSendero.

Requires pyreadstat==1.3.7. Prints aggregate schema evidence only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pyreadstat


SOURCE_URL = "https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0177719.s003&type=supplementary"
EXPECTED_SHA256 = "2fd3b50d7f21b8509d02aa59b807df80ac34e8a6ab666664ab164502d8a1b843"
ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/fatigue-trekking-evaluation-2026-10-22/plos-hiking-audit.json"


def audit(path: Path) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError("Supplement differs from the reviewed source; audit its version first")
    frame, _ = pyreadstat.read_sav(path, apply_value_formats=False)
    rpe_fields = ["M_pre_RPE", "M_between_RPE", "M_post_RPE"]
    if not all(field in frame for field in rpe_fields):
        raise ValueError("Expected hiking RPE columns missing")
    heart_fields = [column for column in frame if any(token in column.lower() for token in ("heart", "pulse", "_hr", "heartrate"))]
    return {
        "source": SOURCE_URL,
        "sha256": digest,
        "bytes": path.stat().st_size,
        "format": "SPSS SAV",
        "rows": len(frame),
        "columns": len(frame.columns),
        "hiking_rpe_observations": {field: int(frame[field].notna().sum()) for field in rpe_fields},
        "hiking_rpe_scale": "Borg 6-20 as documented in the study",
        "heart_rate_columns": heart_fields,
        "subject_id_columns": [column for column in frame if column.lower() in ("id", "subject", "participant", "participant_id")],
        "decision": "Not suitable for external evaluation of the GeoFatigue model: no individual HR or wearable signal in the public supplement, and RPE scales differ.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sav", type=Path, help="Unmodified PLOS S1 supplementary SAV file")
    args = parser.parse_args()
    result = audit(args.sav)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
