#!/usr/bin/env python3
"""Verify SNMF PDFs that explicitly report no national fires.

Only exact, text-extractable statements whose internal report date matches the
archived date are counted as nationally no-fire-reported days. This remains a
label for the official report record, not proof of physical absence of fire.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'docs/environmental-models-2026-10-22'
PRIVATE = ROOT / 'training/data/environmental/private'
GEOGRAPHY = ROOT / 'training/data/environmental/geography.json'
OUT = BASE / 'fire-snmf-national-no-fire-report-audit.json'
OUT_MD = BASE / 'fire-snmf-national-no-fire-report-audit.md'
YEARS = {
    '2022-apr-dec': ('2022-daily-occurrence-events.json', 'snmf-2022-daily-occurrence-2022-apr-dec'),
    '2023-jul-dec': ('snmf-2023-daily-occurrence-events.json', 'snmf-daily-occurrence-2023-jul-dec'),
    '2024': ('snmf-2024-daily-occurrence-events.json', 'snmf-daily-occurrence-2024'),
    '2025': ('snmf-2025-daily-occurrence-events.json', 'snmf-daily-occurrence-2025'),
    '2026-jan': ('snmf-2026-jan-daily-occurrence-events.json', 'snmf-daily-occurrence-2026-jan'),
}
MONTHS = {
    name: index for index, name in enumerate((
        'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
        'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE',
    ), start=1)
}
DATE_RE = re.compile(r'\b(\d{1,2})\s+DE\s+([A-Z]+)\s+DE\s+((?:19|20)\d{2})\b')
NO_FIRE_PHRASE = 'NO SE REPORTARON INCENDIOS EN EL TERRITORIO NACIONAL'


def normalize(text: str) -> str:
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(char for char in text if not unicodedata.combining(char))
    return ' '.join(text.upper().split())


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def text_report_date(text: str) -> str | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    day, month, year = int(match.group(1)), MONTHS.get(match.group(2)), int(match.group(3))
    if month is None:
        return None
    return f'{year:04d}-{month:02d}-{day:02d}'


def inspect_report(path: Path) -> tuple[str, int, int]:
    with fitz.open(path) as document:
        text = normalize(' '.join(page.get_text() for page in document))
        page_count = document.page_count
    return text, len(text), page_count


def main() -> None:
    candidates = []
    explicit = []
    scanned_reports = 0
    for year_dir, (events_file, manifest_dir) in YEARS.items():
        manifest_path = PRIVATE / manifest_dir / 'source-manifest.json'
        events_path = BASE / events_file
        if not manifest_path.is_file() or not events_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        event_data = json.loads(events_path.read_text(encoding='utf-8'))
        parsed_rows_by_date: dict[str, int] = {}
        for row in event_data.get('snapshots', []):
            parsed_rows_by_date[row['report_date']] = parsed_rows_by_date.get(row['report_date'], 0) + 1
        for report in manifest.get('reports', []):
            if report.get('status') not in {'cached', 'downloaded'}:
                continue
            expected_date = report['date']
            path = manifest_path.parent / report['path']
            scanned_reports += 1
            source_hash = file_sha256(path)
            try:
                text, text_chars, page_count = inspect_report(path)
                extraction_error = None
            except Exception as error:  # Keep failed PDF extraction unknown.
                text, text_chars, page_count = '', 0, 0
                extraction_error = f'{type(error).__name__}: {error}'
            internal_date = text_report_date(text)
            phrase_found = NO_FIRE_PHRASE in text
            hash_matches_manifest = source_hash == report.get('sha256')
            status = 'unknown'
            if not hash_matches_manifest:
                status = 'source_hash_mismatch'
            elif extraction_error:
                status = 'pdf_text_extraction_error'
            elif not text_chars:
                status = 'pdf_has_no_extractable_text'
            elif phrase_found and internal_date != expected_date:
                status = 'explicit_no_fire_phrase_but_report_date_mismatch'
            elif phrase_found and internal_date == expected_date and parsed_rows_by_date.get(expected_date, 0):
                status = 'no_fire_phrase_conflicts_with_parsed_event_rows'
            elif phrase_found and internal_date == expected_date:
                status = 'explicit_national_no_fire_report'
            elif internal_date and internal_date != expected_date:
                status = 'report_date_mismatch_without_no_fire_phrase'
            elif text_chars < 1000:
                status = 'short_report_without_explicit_no_fire_phrase'
            else:
                status = 'zero_parsed_events_but_report_has_other_text'

            row = {
                'report_date_in_archive': expected_date,
                'report_date_inside_pdf': internal_date,
                'source_url': report.get('url'),
                'pdf_path': str(path.relative_to(ROOT)),
                'pdf_bytes': path.stat().st_size,
                'pdf_sha256': source_hash,
                'manifest_sha256': report.get('sha256'),
                'manifest_hash_matches': hash_matches_manifest,
                'pages': page_count,
                'normalized_extractable_text_characters': text_chars,
                'explicit_no_fire_phrase': phrase_found,
                'parsed_event_rows': parsed_rows_by_date.get(expected_date, 0),
                'classification': status,
            }
            if extraction_error:
                row['extraction_error'] = extraction_error
            candidates.append(row)
            if status == 'explicit_national_no_fire_report':
                explicit.append(row)

    regions = json.loads(GEOGRAPHY.read_text(encoding='utf-8'))['fire_regions']
    route_count = len(regions)
    verified_route_day_labels = [
        {
            'report_date': report['report_date_in_archive'],
            'route_sector': region['name'],
            'label': 0,
            'label_meaning': 'SNMF_explicitly_reported_no_national_fires',
            'evidence_report_date': report['report_date_in_archive'],
            'evidence_pdf_path': report['pdf_path'],
            'evidence_pdf_sha256': report['pdf_sha256'],
            'group_id': report['report_date_in_archive'],
        }
        for report in explicit
        for region in regions
    ]
    result = {
        'experiment_id': 'snmf-explicit-national-no-fire-daily-report-audit',
        'target': 'Official report states no fires were reported nationally on the report date; not a sensor-confirmed physical no-fire label.',
        'method': {
            'candidate_reports': 'Every cached/downloaded SNMF PDF in the available manifests, including reports with parsed event rows so contradictory evidence can be detected.',
            'confirmation_rule': 'Manifest PDF hash matches; extractable PDF text contains the exact normalized phrase "NO SE REPORTARON INCENDIOS EN EL TERRITORIO NACIONAL"; and an internal PDF date matches the archive date.',
            'route_day_mapping': 'Each explicitly national no-fire report covers all eight route sectors for the report date as a negative official-report proxy, at either spatial radius.',
        },
        'summary': {
            'archived_reports_scanned': scanned_reports,
            'zero_parsed_event_report_candidates': sum(row['parsed_event_rows'] == 0 for row in candidates),
            'reports_with_explicit_no_fire_phrase_and_matching_date_but_conflicting_event_rows': sum(
                row['classification'] == 'no_fire_phrase_conflicts_with_parsed_event_rows' for row in candidates
            ),
            'explicit_national_no_fire_reports_with_date_and_hash_verified': len(explicit),
            'report_days_available_for_all_eight_route_sectors': len(explicit),
            'national_negative_route_day_records_across_eight_sectors': route_count * len(explicit),
            'years': dict(sorted({row['report_date_in_archive'][:4]: sum(
                item['report_date_in_archive'].startswith(row['report_date_in_archive'][:4]) for item in explicit
            ) for row in explicit}.items())),
        },
        'verified_explicit_no_fire_reports': explicit,
        'verified_negative_route_day_labels': verified_route_day_labels,
        'other_zero_parsed_report_cases_not_admitted_as_national_negatives': [
            row for row in candidates if row['classification'] != 'explicit_national_no_fire_report'
        ],
        'limitations': [
            'The phrase certifies what the official report says, not that no unreported or undetected physical fire existed.',
            'A national no-fire report is useful for training/evaluating the target of nearby officially reported fire only.',
            'A report date has daily, not hourly, temporal resolution and cannot verify 24-hour forecast lead from ignition.',
            'This audit does not evaluate any model, precision, recall, calibration, or event-level independence.',
        ],
        'synthetic_observations': 0,
        'deployment_approved': False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    md = [
        '# Auditoria de partes SNMF sin incendios reportados',
        '',
        f'Se revisaron {scanned_reports} PDF oficiales archivados. Un dia se acepta como negativo del **registro de incendios reportados** solo si el hash del PDF coincide con el manifiesto, el texto contiene la frase exacta "No se reportaron incendios en el territorio nacional", la fecha impresa coincide con la fecha archivada y el extractor no encuentra eventos en ese parte.',
        '',
        f'El criterio verifico **{len(explicit)} dias** ({route_count * len(explicit)} registros fecha-sector para los ocho sectores) en {", ".join(f"{year}: {count}" for year, count in sorted(result["summary"]["years"].items()))}. Los archivos con fecha interna distinta, conflicto con eventos parseados o sin texto legible se conservan como desconocidos.',
        '',
        'Esto permite contar negativos mas solidos para el objetivo "incendio cercano reportado por SNMF". No demuestra ausencia fisica de fuego, no da hora de ignicion y no permite afirmar precision de un predictor por si solo. Las fechas pueden incluir ocho sectores del mismo dia, pero no son ocho observaciones independientes de incendio.',
        '',
        'La lista detallada, hashes, URL de cada PDF y regla de clasificacion estan en [el JSON reproducible](fire-snmf-national-no-fire-report-audit.json). Se reproduce con [`audit_snmf_national_no_fire_reports.py`](../../training/python/audit_snmf_national_no_fire_reports.py).',
        '',
    ]
    OUT_MD.write_text('\n'.join(md), encoding='utf-8')
    print(json.dumps({'output': str(OUT.relative_to(ROOT)), 'summary': result['summary'],
                      'verified_dates': [row['report_date_in_archive'] for row in explicit]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
