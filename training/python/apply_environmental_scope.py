"""Apply an explicit project-scope exclusion without deleting research evidence."""
import json
from environmental_sources import EXCLUDED_STATIONS, ROOT, STATIONS, satellite_status, sha256


def main():
    path = ROOT / 'docs/environmental-models-2026-10-22/river-results.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    rejected = [m for m in report['models'] if m['series_id'] not in STATIONS]
    if rejected:
        archive = path.parent / 'archive' / f'river-results-{sha256(path)}.json'
        archive.parent.mkdir(parents=True, exist_ok=True)
        if not archive.exists():
            archive.write_bytes(path.read_bytes())
    report['models'] = [m for m in report['models'] if m['series_id'] in STATIONS]
    report['scope_exclusions'] = EXCLUDED_STATIONS
    report['satellite_models'] = satellite_status()
    report['limitations'] = [item for item in report['limitations'] if not item.startswith('NASA satellite models')]
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print('Active river experiments:', len(report['models']), '; excluded series:', list(EXCLUDED_STATIONS))


if __name__ == '__main__':
    main()
