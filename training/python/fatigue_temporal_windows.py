"""Feature-only causal phone windows for external unlabelled pretraining.

No Borg/f-level target is stored. Missing samples are zero tensor padding
accompanied by per-channel masks, not interpolated or measured zero samples.
All per-window normalization and gravity estimation use available bins only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from fatigue_features import RESEARCH
from fatigue_phone_context import available_sources
from fatigue_phone_spectral import BIN_COLUMNS, cached_bins
from fatigue_spectral_experiment import load_inputs
from fetch_whamap_sensors import DIRECTORY as WHAMAP_DIRECTORY
from public_sources import digest

DIRECTORY = RESEARCH / "temporal-phone-windows-80-v1"
LENGTH = 256
BIN_NS = 100_000_000
CHANNELS = ("acc_mag", "gyro_mag", "vertical")
STATISTICS = [f"temporal_{name}_{stat}" for name in CHANNELS for stat in ("mean", "std", "coverage")]


def make_window(times_ns, values, now_ns, task_start_ns):
    times_ns, values = np.asarray(times_ns, dtype=np.int64), np.asarray(values, dtype=float)
    if values.shape != (len(times_ns), 5) or (len(times_ns) > 1 and np.any(np.diff(times_ns) <= 0)):
        raise ValueError("Distinct chronological five-channel observed phone bins required")
    end = int(now_ns)//BIN_NS*BIN_NS
    start = end-LENGTH*BIN_NS
    selected = (times_ns >= max(start, int(task_start_ns))) & (times_ns+BIN_NS <= end)
    t, data = times_ns[selected], values[selected]
    if np.any(t % BIN_NS != 0):
        raise ValueError("Phone cache clock is not an explicit 100 ms grid")
    position = (t-start)//BIN_NS
    channels = np.full((3, LENGTH), np.nan)
    channels[0, position], channels[1, position] = data[:, 0], data[:, 1]
    axes = data[:, 2:5]
    good = np.isfinite(axes).all(axis=1)
    if good.any():
        gravity = axes[good].mean(axis=0)
        norm = np.linalg.norm(gravity)
        if norm > 1e-8:
            channels[2, position[good]] = axes[good] @ (gravity/norm)
    output, statistics = np.zeros((6, LENGTH), dtype=np.float32), []
    for i, floor in enumerate((.1, .01, .1)):
        valid = np.isfinite(channels[i])
        mean = float(channels[i, valid].mean()) if valid.any() else np.nan
        std = float(channels[i, valid].std()) if valid.any() else np.nan
        statistics.extend((mean, std, float(valid.mean())))
        if valid.any():
            output[i, valid] = np.clip((channels[i, valid]-mean)/max(std, floor), -10, 10)
            output[i+3, valid] = 1.
    return output, np.asarray(statistics, dtype=float)


def source_windows():
    path = WHAMAP_DIRECTORY / "phone-bins-provenance.json"
    evidence = json.loads(path.read_text())
    from whamap_phone_bins import CACHE
    if evidence["extractor_code_sha256"] != digest(Path(__file__).with_name("whamap_phone_bins.py")) or evidence["native_borg_supervision_rows"] != 0:
        raise ValueError("External unlabelled signal preparation changed")
    windows, stats, people, lineage = [], [], [], []
    skipped = 0
    for entry in evidence["files"]:
        for segment in entry["segments"]:
            cache_path = CACHE / segment["file"]
            if digest(cache_path) != segment["sha256"]:
                raise ValueError("External signal cache changed")
            with np.load(cache_path, allow_pickle=False) as data:
                if data["columns"].tolist() != BIN_COLUMNS:
                    raise ValueError("Unexpected external phone channels")
                times, values = data["relative_time_ns"], data["values"]
            if not len(times):
                continue
            for end in range(int(times[0])+LENGTH*BIN_NS, int(times[-1])+BIN_NS+1, LENGTH//2*BIN_NS):
                window, summary = make_window(times, values, end, int(times[0]))
                if min(summary[[2, 5, 8]]) < .9:
                    skipped += 1
                    continue
                windows.append(window)
                stats.append(summary)
                people.append(entry["source"]["participant"])
                lineage.append({"source_segment": segment["file"], "end_clock_ns": end})
    if not windows or set(people) & {"subject_02", "subject_09"}:
        raise ValueError("Missing source windows or a reserved WHAMAP person entered pretraining")
    return np.stack(windows), np.stack(stats), np.asarray(people), lineage, skipped, evidence


def query_windows():
    frame, _, _, manifest, _ = load_inputs()
    sources, _ = available_sources(require_complete=True)
    grouped = {}
    for i, evidence in enumerate(manifest["lineage"]):
        person = "p"+re.search(r"/p(\d+)-", evidence["sensor_members"][0])[1]
        terrain = next(t for t in ("stairs", "ramp", "flat_trail") if frame.iloc[i]["terrain_"+t] == 1)
        grouped.setdefault((person, terrain), []).append((i, evidence))
    windows = np.zeros((666, 6, LENGTH), dtype=np.float32)
    statistics = np.empty((666, len(STATISTICS)), dtype=float)
    lineage = []
    for number, ((person, terrain), queries) in enumerate(grouped.items()):
        matched = [s for s in sources if s["participant"] == person and s["terrain"] == terrain]
        parts = [cached_bins(s) for s in matched]
        bins = pd.concat(parts).sort_index() if parts else pd.DataFrame(columns=BIN_COLUMNS, index=pd.DatetimeIndex([], tz="UTC"))
        if bins.index.duplicated().any():
            raise ValueError("Original phone files overlap")
        times, values = bins.index.as_unit("ns").asi8, bins[BIN_COLUMNS].to_numpy(float)
        for i, evidence in queries:
            now, start = pd.Timestamp(evidence["response_time"]), pd.Timestamp(evidence["task_start"])
            windows[i], statistics[i] = make_window(times, values, now.value, start.value)
            available = times[(times >= start.value) & (times+BIN_NS <= now.value//BIN_NS*BIN_NS)]
            lineage.append({"row_key": evidence["row_key"], "prediction_time": now.isoformat(),
                            "latest_used_bin_end_ns": int(available[-1]+BIN_NS) if len(available) else None})
        if (number+1) % 10 == 0 or number+1 == len(grouped):
            print(f"Native query temporal windows {number+1}/{len(grouped)} groups", flush=True)
    return windows, statistics, frame["row_key"].to_numpy(str), lineage, manifest


def prepare():
    DIRECTORY.mkdir(exist_ok=True)
    if any((DIRECTORY / name).exists() for name in ("source.npz", "queries.npz", "provenance.json")):
        raise ValueError("Preserve the frozen temporal window snapshot before preparing a new version")
    source, source_stats, people, source_lineage, skipped, source_manifest = source_windows()
    windows, statistics, keys, lineage, manifest = query_windows()
    np.savez_compressed(DIRECTORY / "source.npz", windows=source, statistics=source_stats, participants=people)
    np.savez_compressed(DIRECTORY / "queries.npz", windows=windows, statistics=statistics, row_keys=keys)
    helpers = ("whamap_phone_bins.py", "fatigue_phone_spectral.py", "fatigue_spectral_experiment.py")
    evidence = {"version": 1, "feature_code_sha256": digest(Path(__file__)),
                "dependency_code_sha256": {name: digest(Path(__file__).with_name(name)) for name in helpers},
                "source_npz_sha256": digest(DIRECTORY / "source.npz"), "query_npz_sha256": digest(DIRECTORY / "queries.npz"),
                "source_bin_provenance_sha256": digest(WHAMAP_DIRECTORY / "phone-bins-provenance.json"),
                "parent_dataset_sha256": manifest["dataset_sha256"], "phone_receipt_sha256": manifest["phone_receipt_sha256"],
                "window_samples": LENGTH, "bin_duration_ms": 100, "window_seconds": LENGTH/10,
                "channels": list(CHANNELS), "statistics": STATISTICS, "padding_mask_channels": 3,
                "unlabelled_source_windows": len(source), "unlabelled_source_participants": len(set(people)),
                "source_windows_below_90_percent_coverage_skipped": skipped, "source_window_lineage": source_lineage,
                "unchanged_native_query_rows": 666, "query_lineage": lineage, "native_borg_targets_stored": 0, "f_level_used": False,
                "gap_interpolation": False, "synthetic_borg_supervision_rows": 0,
                "query_rows_with_any_signal": int((windows[:, 3:, :].sum(axis=(1, 2)) > 0).sum()),
                "policy": "Only complete observed past bins from the current native task. Gravity, centering and scaling use the selected window alone. Empty/partial native cases remain, with explicit per-channel masks. External fitting-only windows contain no Borg/f-level supervision; masked reconstruction targets must be observed signal values only."}
    (DIRECTORY / "provenance.json").write_text(json.dumps(evidence, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(f"Prepared {len(source)} external unlabelled windows and all 666 unchanged native query tensors; zero Borg targets stored", flush=True)


if __name__ == "__main__":
    prepare()
