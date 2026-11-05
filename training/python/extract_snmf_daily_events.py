"""Extract event snapshots with explicit coordinates from archived SNMF PDFs."""
from datetime import date, datetime, timezone
import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import fitz

from environmental_sources import ROOT
from fire_sources import PRIVATE

SOURCE_DIR = PRIVATE / 'snmf-daily-occurrence-2023-jul-dec'
SOURCE_MANIFEST = SOURCE_DIR / 'source-manifest.json'
OUT = ROOT / 'docs/environmental-models-2026-10-22/snmf-2023-daily-occurrence-events.json'
DATE_RE = re.compile(r'^\d{1,2}/\d{1,2}/\d{4}$')
NUMBER_RE = re.compile(r'\d+(?:[,.]\d+)?')
MONTHS = ('ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO', 'AGOSTO',
          'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE')


def norm(value):
    value = unicodedata.normalize('NFKD', value or '')
    value = ''.join(char for char in value if not unicodedata.combining(char))
    return ' '.join(value.upper().split())


def dms(text, label):
    start = text.find(label)
    if start < 0:
        return None
    start += len(label)
    end = text.find('Longitud:' if label == 'Latitud:' else 'Depto.:', start)
    if end < 0:
        end = min(len(text), start + 50)
    values = [float(item.replace(',', '.')) for item in NUMBER_RE.findall(text[start:end])]
    if len(values) < 3:
        return None
    degrees, minutes, seconds = values[:3]
    if minutes >= 60 or seconds >= 60:
        return None
    return -(degrees + minutes / 60 + seconds / 3600)


def page_rows(page, report_date):
    words = page.get_text('words')
    rotated = bool(page.rotation)
    ignored_boxes = []
    for block in page.get_text('dict')['blocks']:
        if block.get('type') != 0:
            continue
        block_text = ' '.join(span['text'] for line in block.get('lines', []) for span in line.get('spans', []))
        normalized = norm(block_text)
        if (('LA PRESENTE' in normalized and 'CORRESPONDE' in normalized)
                or ('REPORTE DE INCENDIOS' in normalized)
                or ('SISTEMA FEDERAL' in normalized and 'MANEJO DEL FUEGO' in normalized)
                or (re.search(r'\b(?:19|20)\d{2}\b', normalized)
                    and any(month in normalized for month in MONTHS))):
            box = fitz.Rect(block['bbox'])
            ignored_boxes.append(box * page.derotation_matrix if rotated else box)
    if rotated:
        matrix = page.derotation_matrix
        transformed = []
        for word in words:
            box = fitz.Rect(word[:4]) * matrix
            transformed.append((box.x0, box.y0, box.x1, box.y1, *word[4:]))
        words = transformed

    headers = {}
    for word in words:
        label = norm(word[4]).replace(' ', '')
        if label in {'NOMBRE', 'PROVINCIA', 'INICIO', 'ESTADO'} or 'OBSERVACIONES' in label:
            headers.setdefault(label, []).append((word[0] + word[2]) / 2)
    columns = {}
    for label, values in headers.items():
        key = 'observations' if 'OBSERVACIONES' in label else label.lower()
        columns[key] = sorted(values)[0]

    # The archive contains both the original table and redesigned PDFs, some
    # rotated 90 degrees. Header positions identify their columns in either form.
    dynamic_columns = all(key in columns for key in ('nombre', 'provincia', 'inicio', 'estado', 'observations'))
    date_words = sorted((word for word in words if DATE_RE.fullmatch(word[4])), key=lambda word: word[1])
    starts = []
    for word in date_words:
        if not starts or abs(word[1] - starts[-1][0]) > 2:
            starts.append((word[1], word[4]))
    rows = []
    for row_index, (top, raw_start) in enumerate(starts):
        row = []
        for word in words:
            label = norm(word[4]).replace(' ', '')
            center = fitz.Point((word[0] + word[2]) / 2, (word[1] + word[3]) / 2)
            if (any(box.contains(center) for box in ignored_boxes)
                    or label in {'NOMBRE', 'PROVINCIA', 'FECHA', 'INICIO', 'ESTADO', 'OBSERVACIONES'}
                    or re.fullmatch(r'\d{1,2}-\d{1,2}-\d{4}', word[4])):
                continue
            distances = [abs(word[1] - row_y) for row_y, _ in starts]
            if distances and distances.index(min(distances)) == row_index and min(distances) <= 85:
                row.append(word)
        def ordered(subset):
            if rotated:
                return ' '.join(word[4] for word in sorted(subset, key=lambda word: word[5:8]))
            return ' '.join(word[4] for word in sorted(subset, key=lambda word: (word[1], word[0])))
        if dynamic_columns:
            centers = [(columns[key], key) for key in ('nombre', 'provincia', 'inicio', 'estado', 'observations')]
            buckets = {key: [] for _, key in centers}
            for word in row:
                center = (word[0] + word[2]) / 2
                _, key = min(centers, key=lambda entry: abs(center - entry[0]))
                buckets[key].append(word)
            # In the redesigned layout, the observations column extends toward
            # the status column; keep its coordinates even when they are nearer
            # to the status heading than to the observations heading.
            if rotated:
                boundary = (columns['inicio'] + columns['estado']) / 2
                buckets['observations'] = [word for word in row if (word[0] + word[2]) / 2 <= boundary]
            else:
                boundary = (columns['estado'] + columns['observations']) / 2
                buckets['observations'] = [word for word in row if (word[0] + word[2]) / 2 >= boundary]
            name = ordered(buckets['nombre'])
            province = ordered(buckets['provincia'])
            status_text = ordered(buckets['estado'])
            observations = ordered(buckets['observations'])
        else:
            name = ordered(word for word in row if word[0] < 140)
            province = ordered(word for word in row if 140 <= word[0] < 235)
            status_text = ordered(word for word in row if 345 <= word[0] < 470)
            observations = ordered(word for word in row if word[0] >= 470)
        status_norm = norm(status_text)
        status = next((label for label in ('GUARDIA DE CENIZAS', 'EXTINGUIDO', 'CONTROLADO', 'CONTENIDO', 'ACTIVO')
                       if label in status_norm), 'UNKNOWN')
        coordinate_text = ordered(row)
        latitude, longitude = dms(coordinate_text, 'Latitud:'), dms(coordinate_text, 'Longitud:')
        start_date = datetime.strptime(raw_start, '%d/%m/%Y').date()
        if name and province:
            rows.append({'incident_name': name, 'province': province,
                'reported_start_date': start_date.isoformat(), 'report_date': report_date.isoformat(),
                'status': status, 'status_source_text': status_text, 'latitude': latitude, 'longitude': longitude,
                'department': observations.split('Depto.:', 1)[1].split('-', 1)[0].strip() if 'Depto.:' in observations else None,
                'source_page': page.number + 1})
    return rows


def incident_key(row):
    if row['latitude'] is None or row['longitude'] is None:
        return (norm(row['province']), norm(row['incident_name']), row['reported_start_date'])
    return (norm(row['province']), norm(row['incident_name']), row['reported_start_date'],
            round(row['latitude'], 3), round(row['longitude'], 3))


def main(source_dir=SOURCE_DIR, out=OUT):
    source_manifest_path = source_dir / 'source-manifest.json'
    source_manifest = json.loads(source_manifest_path.read_text(encoding='utf-8'))
    snapshots, unique = [], {}
    missing_coordinates = 0
    zero_event_reports = 0
    for source in source_manifest['reports']:
        if source['status'] not in ('downloaded', 'cached'):
            continue
        report_day = date.fromisoformat(source['date'])
        path = source_dir / source['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError(f'Source PDF hash mismatch: {path.name}')
        document = fitz.open(path)
        page_count = len(document)
        rows = []
        for page in document:
            rows.extend(page_rows(page, report_day))
        rows = [row for row in rows if row['incident_name'] and row['province']]
        snapshots.extend(rows)
        if not rows:
            zero_event_reports += 1
        for row in rows:
            if row['latitude'] is None or row['longitude'] is None:
                missing_coordinates += 1
            unique.setdefault(incident_key(row), row)
    events = sorted(unique.values(), key=lambda row: (row['reported_start_date'], row['province'], row['incident_name']))
    period = source_manifest.get('period')
    expected_days = ((date.fromisoformat(period[1]) - date.fromisoformat(period[0])).days
        if period else len(source_manifest['reports']))
    missing_reports = sum(item['status'] not in ('downloaded', 'cached') for item in source_manifest['reports'])
    report = {'schema_version': 1, 'source_manifest_sha256': hashlib.sha256(source_manifest_path.read_bytes()).hexdigest(),
        'source': 'Archived official daily SNMF occurrence reports, as supplied by provincial/jurisdictional reports.',
        'extraction': {'method': 'PDF table row positions; incident start date, event name, province, status and latitude/longitude parsed from page text.',
            'missing_coordinate_snapshot_rows': missing_coordinates,
            'snapshot_rows': len(snapshots), 'deduplicated_incidents': len(events),
            'reports_used': source_manifest['status_counts'].get('downloaded', 0) + source_manifest['status_counts'].get('cached', 0),
            'reports_with_zero_parsed_events': zero_event_reports},
        'limitations': [f"{missing_reports} of {expected_days} dates had no PDF at the checked public archive paths; these dates are unobserved, not negative.",
            'A missing report is not a fire-free observation and is not encoded as a negative label.',
            'A repeated event is deduplicated by province/name/start date and rounded coordinates; records without coordinates use province/name/start date only.',
            'Automated extraction requires spot-checking against the original PDF; no row without parsed coordinates is used in spatial matching.'],
        'snapshots': snapshots, 'deduplicated_events': events}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': out.resolve().relative_to(ROOT.resolve()).as_posix(), **report['extraction']}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-dir', type=Path, default=SOURCE_DIR)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    main(args.source_dir, args.output)
