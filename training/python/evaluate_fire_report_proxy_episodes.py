#!/usr/bin/env python3
"""Collapse consecutive route-day alerts into descriptive report-proxy episodes."""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "docs/environmental-models-2026-10-22"
SOURCE = REPORT_DIR / "goes-gfs-24h-snmf-daily-report-agreement-2026-jan.json"
OUT = REPORT_DIR / "fire-gfs-24h-snmf-2026-jan-alert-episodes.json"
ACTIVE = {"ACTIVO", "CONTENIDO", "CONTROLADO"}


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total == 0:
        return None
    p = successes / total
    den = 1 + z * z / total
    center = (p + z * z / (2 * total)) / den
    margin = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5) / den
    return [max(0.0, center - margin), min(1.0, center + margin)]


def group_episodes(rows: list[dict], alert_key: str) -> list[dict]:
    episodes: list[dict] = []
    route_names = sorted({row["route_sector"] for row in rows})
    for route_name in route_names:
        route_rows = sorted(
            (row for row in rows if row["route_sector"] == route_name),
            key=lambda row: row["date"],
        )
        current: list[dict] = []

        def save() -> None:
            if not current:
                return
            positive_rows = [row for row in current if row["snmf_active_incident_within_10km"]]
            incidents = sorted({
                (item["name"], item["status"])
                for row in positive_rows
                for item in row["nearby_snapshot_incidents"]
                if item["status"] in ACTIVE
            })
            episodes.append({
                "route_sector": route_name,
                "start_date": current[0]["date"],
                "end_date": current[-1]["date"],
                "consecutive_reported_alert_days": len(current),
                "report_proxy_positive_days": len(positive_rows),
                "contains_nearby_listed_active_incident": bool(positive_rows),
                "nearby_listed_incident_aliases": [
                    {"name": name, "status": status} for name, status in incidents
                ],
            })

        for row in route_rows:
            if not row[alert_key]:
                save()
                current = []
                continue
            if current and date.fromisoformat(row["date"]) != date.fromisoformat(current[-1]["date"]) + timedelta(days=1):
                save()
                current = []
            current.append(row)
        save()
    return episodes


def summarize(episodes: list[dict]) -> dict:
    matched = sum(episode["contains_nearby_listed_active_incident"] for episode in episodes)
    days = sum(episode["consecutive_reported_alert_days"] for episode in episodes)
    return {
        "alert_episodes": len(episodes),
        "episodes_containing_nearby_listed_active_incident": matched,
        "descriptive_episode_coincidence_fraction": matched / len(episodes) if episodes else None,
        "wilson_95pct_descriptive_interval": wilson(matched, len(episodes)),
        "reported_alert_route_days_within_episodes": days,
        "average_reported_alert_days_per_episode": days / len(episodes) if episodes else None,
    }


def main() -> int:
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    daily = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = daily["route_sector_day_rows"]
    model = group_episodes(rows, "model_alert_at_0_5")
    persistence = group_episodes(rows, "persistence_alert")
    result = {
        "experiment_id": "fire-gfs-24h-snmf-2026-jan-alert-episodes",
        "source": SOURCE.relative_to(ROOT).as_posix(),
        "source_sha256": source_hash,
        "protocol": {
            "alert_rule": "Existing uncalibrated diagnostic threshold 0.5; this audit does not tune it.",
            "episode_rule": "Consecutive calendar-day alerts for the same route sector form one streak. A missing/non-alert row splits a streak.",
            "proxy_positive": "At least one day in the streak has a listed ACTIVO, CONTENIDO, or CONTROLADO SNMF incident within the existing 10 km center rule.",
        },
        "model": {"summary": summarize(model), "episodes": model},
        "persistence": {"summary": summarize(persistence), "episodes": persistence},
        "limitations": [
            "This is an alert-streak coincidence with an incomplete daily-report proxy, not physical fire precision.",
            "Adjacent daily reports can describe the same fire; different alert streaks can also describe one physical event.",
            "No listed nearby active incident does not prove no fire; some dates/route sectors were excluded for missing reports or unknown incident status.",
            "The 10 km rule is based on sector centers, not complete trail lines.",
            "The 0.5 scores are uncalibrated and the test cohort is one month.",
        ],
        "deployment_approved": False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": OUT.relative_to(ROOT).as_posix(), "model": result["model"]["summary"], "persistence": result["persistence"]["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
