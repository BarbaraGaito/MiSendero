"""Inventory published image context and already audited raw sensor coverage."""
import json
from datetime import datetime,timezone
from pathlib import Path

import numpy as np
import pandas as pd

from fetch_geofatigue_context import METADATA_PATH
from public_sources import ROOT,OUTPUT,digest


def validate():
    record = json.loads(METADATA_PATH.read_text())
    files = record["data"]["latestVersion"]["files"]
    photos = [entry for entry in files if entry["dataFile"]["contentType"].startswith("image/")]
    if len(photos) != 5 or not all(entry.get("directoryLabel","").endswith("HQ Panorama Images") for entry in photos):
        raise ValueError("Reinspect changed published image modality inventory")
    if any(entry["dataFile"]["contentType"].startswith("video/") for entry in files):
        raise ValueError("A new video source requires temporal/label inspection")
    raw_dir = ROOT/"training/data/fatigue-research/raw-v1"
    manifest = json.loads((raw_dir/"provenance.json").read_text())
    if manifest["dataset_sha256"] != digest(raw_dir/"dataset.csv") or manifest["feature_code_sha256"] != digest(Path(__file__).with_name("fatigue_raw_features.py")):
        raise ValueError("Previously audited raw physiological feature snapshot changed")
    columns = ["raw_bvp_60s_mean","raw_eda_60s_mean","raw_temperature_60s_mean","raw_acc_magnitude_60s_mean"]
    data = pd.read_csv(raw_dir/"dataset.csv",usecols=columns)
    if len(data) != 666 or len(manifest["lineage"]) != 666:
        raise ValueError("Original raw-feature cohort changed")
    protocol = json.loads((OUTPUT/"fatigue/metrics.json").read_text())["evaluation_protocol"]
    fit = np.array([r["row_key"] in set(protocol["train_row_keys"]) for r in manifest["lineage"]])
    if int(fit.sum()) != 487:
        raise ValueError("Original training cohort changed")
    coverage = {name:{"original_666_with_valid_60s_mean":int(data[name].notna().sum()),
        "original_fitting_487_with_valid_60s_mean":int(data.loc[fit,name].notna().sum())} for name in columns}
    return {"version":1,"verified_at":datetime.now(timezone.utc).isoformat(),"verification_code_sha256":digest(Path(__file__)),
        "public_dataset_metadata_sha256":digest(METADATA_PATH),"published_inventory_files":len(files),
        "published_image_files":[{"id":e["dataFile"]["id"],"filename":e["dataFile"]["filename"],
            "bytes":e["dataFile"]["filesize"],"directory":e["directoryLabel"],"restricted":e["restricted"]} for e in photos],
        "image_interpretation":"Five static experimental-site panorama images, not a per-participant or per-report image stream. The published inventory does not supply temporally paired individual frames for current Borg prediction.",
        "individual_temporal_image_or_video_files_in_inventory":0,"images_downloaded_or_fitted_in_this_audit":0,
        "raw_sensor_feature_snapshot_sha256":manifest["dataset_sha256"],"raw_60_second_coverage":coverage,
        "proposed_next_representation":"Current/prior paired raw physiological waveform windows, using only actually observed samples and natural missingness masks. Requires independent timestamp and window reconstruction before model fitting.",
        "proposed_sequence_windows_already_verified":False,"new_native_borg_targets":0,"synthetic_observations_added":0,
        "current_native_test_response_values_inspected":False,
        "scope":"Metadata and observed input coverage only. No image-to-Borg label assignment, fabricated images, waveform interpolation, row exclusion, model fitting or new accuracy claim. Valid 60-second feature means do not establish coverage of every future 16-second current/prior sequence."}


if __name__ == "__main__":
    result = validate()
    path = ROOT/"docs/fatigue-80-2026-10-25/modality-inventory.json"
    path.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"static_site_images":5,"timed_individual_frames":0,"raw_60_second_sensor_coverage":result["raw_60_second_coverage"],"new_native_targets":0}))
