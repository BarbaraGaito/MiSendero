"""Acquire public SNMF daily occurrence reports available for 2024.

The archive currently exposes daily reports through 2024-11-19. Missing PDFs
remain unknown; they are never interpreted as fire-free observations.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta, datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fire_sources import PRIVATE

START = date(2024, 1, 1)
END_EXCLUSIVE = date(2024, 11, 20)
DEST = PRIVATE / 'snmf-daily-occurrence-2024'
MANIFEST = DEST / 'source-manifest.json'
PREVIOUS_BY_DATE = {}


def candidate_urls(day):
    hyphen = f'{day.day:02d}-{day.month:02d}-{day.year}'
    names = (f'reporte_diario_{hyphen}.pdf', f'reporte_diario_{hyphen}_0.pdf',
             f'reporte_diario_{hyphen}_l.pdf')
    # The archive moved uploads from the January directory to monthly
    # directories during 2024. Check the date's directory first, then the
    # known shared directories used by the official archive.
    directories = [f'2024/{day.month:02d}', '2024/01', '2024/09']
    return [f'https://www.argentina.gob.ar/sites/default/files/{directory}/{name}'
            for directory in dict.fromkeys(directories) for name in names]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def acquire(day, dest=DEST):
    filename = f'snmf-{day.isoformat()}.pdf'
    path = dest / filename
    urls = candidate_urls(day)
    if path.exists() and path.read_bytes().startswith(b'%PDF-'):
        data = path.read_bytes()
        previous = PREVIOUS_BY_DATE.get(day.isoformat(), {})
        return previous | {'date': day.isoformat(), 'status': 'cached', 'bytes': len(data),
            'sha256': sha256(data), 'path': filename}
    checked = []
    for url in urls:
        request = Request(url, headers={'User-Agent': 'MiSendero thesis research',
            'Accept': 'application/pdf'})
        try:
            with urlopen(request, timeout=25) as response:
                data = response.read()
                headers = {'last_modified': response.headers.get('Last-Modified'),
                    'content_type': response.headers.get('Content-Type')}
        except HTTPError as exc:
            if exc.code == 404:
                checked.append(url)
                continue
            return {'date': day.isoformat(), 'url': url, 'status': f'http_{exc.code}'}
        except (URLError, TimeoutError) as exc:
            return {'date': day.isoformat(), 'url': url, 'status': f'network_{type(exc).__name__}'}
        if not data.startswith(b'%PDF-'):
            return {'date': day.isoformat(), 'url': url, 'status': 'response_not_pdf',
                'content_type': headers['content_type'], 'first_bytes_hex': data[:16].hex()}
        temporary = path.with_suffix('.pdf.part')
        temporary.write_bytes(data)
        temporary.replace(path)
        return {'date': day.isoformat(), 'url': url, 'status': 'downloaded',
            'bytes': len(data), 'sha256': sha256(data), 'path': filename, **headers}
    return {'date': day.isoformat(), 'urls_checked': checked, 'status': 'not_found_at_checked_paths'}


def main(start=START, end_exclusive=END_EXCLUSIVE, dest=DEST):
    global PREVIOUS_BY_DATE
    manifest_path = dest / 'source-manifest.json'
    dest.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding='utf-8'))
        PREVIOUS_BY_DATE = {item['date']: item for item in previous.get('reports', [])}
    days = [start + timedelta(days=i) for i in range((end_exclusive - start).days)]
    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(acquire, day, dest) for day in days]
        for future in as_completed(futures):
            results.append(future.result())
            if len(results) % 50 == 0:
                print(f'checked {len(results)}/{len(days)} dates', flush=True)
    results.sort(key=lambda item: item['date'])
    counts = {status: sum(item['status'] == status for item in results)
        for status in sorted({item['status'] for item in results})}
    manifest = {'source': 'Servicio Nacional de Manejo del Fuego, archived daily occurrence reports',
        'archive_pages': ['https://www.argentina.gob.ar/reporte-de-incendios-09',
            'https://www.argentina.gob.ar/node/414390'],
        'period': [start.isoformat(), end_exclusive.isoformat()],
        'retrieved_at': datetime.now(timezone.utc).isoformat(), 'status_counts': counts,
        'reports': results,
        'interpretation': 'Jurisdiction-reported incidents, not exhaustive ground truth. Missing PDFs are unknown, not negative observations.'}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'manifest': str(manifest_path), 'status_counts': counts,
        'downloaded_bytes': sum(item.get('bytes', 0) for item in results)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=date.fromisoformat, default=START)
    parser.add_argument('--end-exclusive', type=date.fromisoformat, default=END_EXCLUSIVE)
    parser.add_argument('--dest', type=Path, default=DEST)
    args = parser.parse_args()
    main(args.start, args.end_exclusive, args.dest)
