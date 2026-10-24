"""Acquire archived daily SNMF occurrence PDFs for the MODIS 2023 test window."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta, datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fire_sources import PRIVATE

START = date(2023, 7, 1)
END_EXCLUSIVE = date(2024, 1, 1)
DEST = PRIVATE / 'snmf-daily-occurrence-2023-jul-dec'
MANIFEST = DEST / 'source-manifest.json'
SOURCE_BY_DATE = {}


def candidate_urls(day):
    stem = f'{day.day:02d}-{day.month:02d}-{day.year}'
    old = f'reportediario_{stem}.pdf'
    current = f'reporte_diario_{stem}.pdf'
    occurrence = f'reporte_tecnico_de_ocurrencia_{stem}.pdf'
    return [f'https://www.argentina.gob.ar/sites/default/files/2023/06/{old}',
        f'https://www.argentina.gob.ar/sites/default/files/2023/06/{current}',
        f'https://www.argentina.gob.ar/sites/default/files/2024/01/{current}',
        f'https://www.argentina.gob.ar/sites/default/files/2024/01/{occurrence}']


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def acquire(day):
    name = f'snmf-{day.isoformat()}.pdf'
    path = DEST / name
    urls = candidate_urls(day)
    if path.exists():
        if path.read_bytes()[:5] != b'%PDF-':
            raise ValueError(f'Cached daily report is not a PDF: {name}')
        previous = SOURCE_BY_DATE.get(day.isoformat(), {})
        return previous | {'date': day.isoformat(), 'status': 'cached',
                'bytes': path.stat().st_size, 'sha256': digest(path), 'path': name}
    failures = []
    for url in urls:
        request = Request(url, headers={'User-Agent': 'MiSendero thesis research contact', 'Accept': 'application/pdf'})
        try:
            with urlopen(request, timeout=25) as response:
                data = response.read()
                headers = {'last_modified': response.headers.get('Last-Modified'),
                           'content_type': response.headers.get('Content-Type')}
        except HTTPError as exc:
            if exc.code == 404:
                failures.append(url)
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
                'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                'path': name, **headers}
    return {'date': day.isoformat(), 'urls_checked': urls, 'status': 'not_published_at_expected_paths'}


def main():
    global SOURCE_BY_DATE
    DEST.mkdir(parents=True, exist_ok=True)
    if MANIFEST.exists():
        previous = json.loads(MANIFEST.read_text(encoding='utf-8'))
        SOURCE_BY_DATE = {item['date']: item for item in previous.get('reports', [])}
    days = [START + timedelta(days=i) for i in range((END_EXCLUSIVE - START).days)]
    results = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(acquire, day) for day in days]
        for future in as_completed(futures):
            results.append(future.result())
            if len(results) % 25 == 0:
                print(f'checked {len(results)}/{len(days)} reports', flush=True)
    results.sort(key=lambda item: item['date'])
    manifest = {'source': 'Servicio Nacional de Manejo del Fuego, archived daily occurrence reports',
        'period': [START.isoformat(), END_EXCLUSIVE.isoformat()],
        'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'status_counts': {status: sum(item['status'] == status for item in results)
                          for status in sorted({item['status'] for item in results})},
        'reports': results,
        'interpretation': 'A missing archived PDF is not a fire-free observation. Reports contain jurisdiction-reported incidents, not exhaustive ground truth.'}
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'manifest': str(MANIFEST.relative_to(PRIVATE.parents[1])),
        'status_counts': manifest['status_counts'],
        'downloaded_bytes': sum(item.get('bytes', 0) for item in results)}, indent=2))


if __name__ == '__main__':
    main()
