"""Separate product creation delay from later public-bucket modification time."""
from datetime import datetime
import sys
import json
from pathlib import Path
import csv

import netCDF4
import numpy as np

from environmental_sources import ROOT, sha256, utc
from fire_sources import PRIVATE

EXPERIMENT = sys.argv[1] if len(sys.argv) > 1 else 'fire-goes16-2025-q1'
manifest_path = PRIVATE / f'{EXPERIMENT}-source-manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
product_lag, archive_lag = [], []
availability_rows = []
for source in manifest:
    if source.get('status') != 'acquired':
        continue
    with netCDF4.Dataset(ROOT / source['relative_path']) as ds:
        end = utc(ds.time_coverage_end)
        created = utc(ds.date_created)
        scan_start = utc(ds.time_coverage_start)
    product_lag.append((created - end).total_seconds() / 60)
    archive_lag.append((utc(source['s3_last_modified']) - end).total_seconds() / 60)
    availability_rows.append({'source_id': Path(source['relative_path']).name,
        'scan_start': scan_start.isoformat(), 'scan_end': end.isoformat(),
        'product_created_at': created.isoformat()})

availability_path = PRIVATE / f'{EXPERIMENT}-availability-by-scan.csv'
with availability_path.open('w', encoding='utf-8', newline='') as stream:
    writer = csv.DictWriter(stream, fieldnames=availability_rows[0].keys())
    writer.writeheader()
    writer.writerows(availability_rows)

def summarize(values):
    return {
        'count': len(values), 'median_minutes': float(np.median(values)),
        'p95_minutes': float(np.percentile(values, 95)), 'maximum_minutes': float(max(values)),
        'negative_count': sum(value < 0 for value in values),
    }

result = {
    'experiment_id': EXPERIMENT,
    'manifest_sha256': sha256(manifest_path),
    'availability_table_sha256': sha256(availability_path),
    'product_created_minus_scan_end': summarize(product_lag),
    's3_last_modified_minus_scan_end': summarize(archive_lag),
    'interpretation': 'date_created measures product generation, not proven first public availability; S3 LastModified can reflect later archival updates and is not a reliable first-publication timestamp.',
}
output = Path(__file__).resolve().parents[2] / 'docs' / 'environmental-models-2026-10-22' / f'{EXPERIMENT}-availability-audit.json'
output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
