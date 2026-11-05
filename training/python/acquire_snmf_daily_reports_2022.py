#!/usr/bin/env python3
"""Acquire official SNMF daily PDFs overlapping the archived 2022 SMN WRF cohort.

The monthly archive page is the source of truth for URLs. Missing links and
failed downloads remain unknown; they are never encoded as no-fire days.
Only research data under training/data/environmental/private are written.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fire_sources import PRIVATE

MONTHS = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
          'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')
START = date(2022, 4, 2)  # First day in the archived SMN route forecast cohort.
END_EXCLUSIVE = date(2023, 1, 1)
DEST = PRIVATE / 'snmf-daily-occurrence-2022-apr-dec'
MANIFEST = DEST / 'source-manifest.json'
BASE_PAGE = 'https://www.argentina.gob.ar/reporte-diario-de-incendios'
DATE_RE = re.compile(r'(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})')


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class PdfLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'a':
            href = dict(attrs).get('href', '')
            if href.lower().split('?', 1)[0].endswith('.pdf'):
                self.current = {'href': href, 'text': ''}

    def handle_data(self, data):
        if self.current is not None:
            self.current['text'] += data

    def handle_endtag(self, tag):
        if tag.lower() == 'a' and self.current is not None:
            self.links.append(self.current)
            self.current = None


def load_previous() -> dict:
    if not MANIFEST.is_file():
        return {}
    payload = json.loads(MANIFEST.read_text(encoding='utf-8'))
    return {item['date']: item for item in payload.get('reports', [])}


def fetch_page(month: int) -> tuple[dict, dict[str, str]]:
    url = f'{BASE_PAGE}/{MONTHS[month - 1]}-de-2022'
    request = Request(url, headers={'User-Agent': 'MiSendero research dataset audit/1.0',
                                    'Accept': 'text/html'})
    error = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=45) as response:
                body = response.read()
                record = {'url': url, 'status': 'downloaded', 'retrieved_at_utc':
                          datetime.now(timezone.utc).isoformat(), 'http_status': response.status,
                          'bytes': len(body), 'sha256': sha256(body),
                          'content_type': response.headers.get('Content-Type')}
            parser = PdfLinks()
            parser.feed(body.decode('utf-8', errors='replace'))
            links = {}
            for link in parser.links:
                match = DATE_RE.search(link['text'])
                if not match:
                    continue
                day, linked_month, year = map(int, match.groups())
                if year != 2022 or linked_month != month:
                    continue
                report_day = date(year, linked_month, day)
                href = link['href']
                if href.startswith('/'):
                    href = 'https://www.argentina.gob.ar' + href
                if not href.startswith('https://www.argentina.gob.ar/'):
                    continue
                links[report_day.isoformat()] = href
            record['pdf_links_found'] = len(links)
            return record, links
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            error = f'{type(exc).__name__}: {exc}'
            if attempt < 2:
                time.sleep(1 + attempt)
    return {'url': url, 'status': 'page_error', 'error': error}, {}


def acquire_one(day: date, url: str | None, previous: dict) -> dict:
    key = day.isoformat()
    path = DEST / f'snmf-{key}.pdf'
    if path.is_file() and path.read_bytes().startswith(b'%PDF-'):
        prior = previous.get(key, {})
        content_hash = sha256(path.read_bytes())
        return prior | {'date': key, 'status': 'cached', 'url': prior.get('url', url),
                        'bytes': path.stat().st_size, 'sha256': content_hash,
                        'path': path.name}
    if url is None:
        return {'date': key, 'status': 'not_linked_in_archive', 'path': None}
    request = Request(url, headers={'User-Agent': 'MiSendero research dataset audit/1.0',
                                    'Accept': 'application/pdf'})
    error = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=60) as response:
                body = response.read()
                headers = {'http_status': response.status,
                           'content_type': response.headers.get('Content-Type'),
                           'last_modified': response.headers.get('Last-Modified')}
            if not body.startswith(b'%PDF-'):
                return {'date': key, 'url': url, 'status': 'response_not_pdf',
                        'first_bytes_hex': body[:16].hex(), **headers}
            temporary = path.with_suffix('.pdf.part')
            temporary.write_bytes(body)
            temporary.replace(path)
            return {'date': key, 'url': url, 'status': 'downloaded',
                    'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                    'bytes': len(body), 'sha256': sha256(body), 'path': path.name, **headers}
        except HTTPError as exc:
            if exc.code == 404:
                return {'date': key, 'url': url, 'status': 'linked_pdf_404'}
            error = f'HTTP {exc.code}: {exc.reason}'
        except (URLError, TimeoutError, OSError) as exc:
            error = f'{type(exc).__name__}: {exc}'
        if attempt < 2:
            time.sleep(1 + attempt)
    return {'date': key, 'url': url, 'status': 'download_error', 'error': error}


def main():
    global DEST, MANIFEST
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=date.fromisoformat, default=START)
    parser.add_argument('--end-exclusive', type=date.fromisoformat, default=END_EXCLUSIVE)
    parser.add_argument('--output-dir', type=Path, default=DEST)
    parser.add_argument('--workers', type=int, default=6)
    args = parser.parse_args()
    if args.start >= args.end_exclusive or args.workers < 1 or args.workers > 12:
        raise ValueError('Invalid date range or worker count')
    DEST = args.output_dir
    MANIFEST = DEST / 'source-manifest.json'
    DEST.mkdir(parents=True, exist_ok=True)
    previous = load_previous()
    months = sorted({(args.start.year, args.start.month),
                     *((day.year, day.month) for day in iter_days(args.start, args.end_exclusive))})
    if any(year != 2022 for year, _ in months):
        raise ValueError('This acquisition script is scoped to the 2022 SNMF archive')
    pages, links = {}, {}
    for _, month in months:
        page, month_links = fetch_page(month)
        pages[f'2022-{month:02d}'] = page
        links.update(month_links)
        if page['status'] != 'downloaded':
            raise RuntimeError(f"Monthly archive page failed for {month}: {page.get('error')}")
    days = list(iter_days(args.start, args.end_exclusive))
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(acquire_one, day, links.get(day.isoformat()), previous)
                   for day in days]
        for index, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if index % 50 == 0:
                print(f'checked {index}/{len(days)} SNMF daily PDFs', flush=True)
    results.sort(key=lambda item: item['date'])
    counts = {status: sum(item['status'] == status for item in results)
              for status in sorted({item['status'] for item in results})}
    manifest = {'source': 'Official SNMF daily reports linked from Argentina.gob.ar monthly archives',
        'period': [args.start.isoformat(), args.end_exclusive.isoformat()],
        'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
        'archive_pages': pages, 'status_counts': counts, 'reports': results,
        'interpretation': 'Archive omissions, PDF gaps, and reports without nearby listed events are not verified fire-free observations.'}
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'manifest': str(MANIFEST), 'status_counts': counts,
        'downloaded_bytes': sum(item.get('bytes', 0) for item in results)}, indent=2))


def iter_days(start: date, end_exclusive: date):
    day = start
    while day < end_exclusive:
        yield day
        day += timedelta(days=1)


if __name__ == '__main__':
    main()
