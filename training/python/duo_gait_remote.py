"""Read selected public DUO-GAIT ZIP members using validated HTTP byte ranges.

ZIP member CRC is checked by zipfile. A partial archive cannot verify the
deposited MD5 of the complete multi-gigabyte ZIP; report that limitation.
No archive extraction to paths supplied by ZIP members is performed.
"""
from __future__ import annotations

import io
import time
import urllib.request
import zipfile

_DIRECTORY_RANGES: dict[tuple[str, int, int], bytes] = {}


class RemoteZipBytes(io.RawIOBase):
    def __init__(self, url: str, size: int):
        self.url, self.size, self.position = url, size, 0
        self.cache_start, self.cache = 0, b''
        self.bytes_fetched = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        new = offset if whence == io.SEEK_SET else self.position + offset if whence == io.SEEK_CUR else self.size + offset
        if new < 0:
            raise ValueError('Negative seek')
        self.position = new
        return new

    def read(self, size=-1):
        if size < 0:
            raise ValueError('Unbounded archive download is disabled')
        size = min(size, max(0, self.size - self.position))
        if not size:
            return b''
        for (url, total, start), data in tuple(_DIRECTORY_RANGES.items()):
            if url == self.url and total == self.size and start <= self.position and self.position + size <= start + len(data):
                self.cache_start, self.cache = start, data
                break
        if not (self.cache_start <= self.position and self.position + size <= self.cache_start + len(self.cache)):
            amount = min(max(size, 65536), self.size - self.position)
            if amount > 32 * 1024 * 1024:
                raise ValueError('Unexpectedly large single range request')
            start, end = self.position, self.position + amount - 1
            request = urllib.request.Request(self.url, headers={'Range': f'bytes={start}-{end}', 'Accept-Encoding': 'identity'})
            for attempt in range(4):
                try:
                    with urllib.request.urlopen(request, timeout=90) as response:
                        header = response.headers.get('Content-Range', '')
                        expected = f'bytes {start}-{end}/{self.size}'
                        if response.status != 206 or header != expected:
                            raise ValueError(f'Range not honored: {response.status} {header}, expected {expected}')
                        chunks, received = [], 0
                        while received <= amount:
                            chunk = response.read(min(65536, amount + 1 - received))
                            if not chunk:
                                break
                            chunks.append(chunk)
                            received += len(chunk)
                        data = b''.join(chunks)
                    if len(data) != amount:
                        raise ValueError(f'Incomplete or oversized byte range: {len(data)} vs {amount}')
                    break
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(attempt + 1)
            self.cache_start, self.cache = start, data
            self.bytes_fetched += amount
            if start >= self.size - 1024 * 1024:
                _DIRECTORY_RANGES[(self.url, self.size, start)] = data
        offset = self.position - self.cache_start
        data = self.cache[offset:offset + size]
        self.position += len(data)
        return data


def archive_url(name: str) -> str:
    if name not in {'raw.zip', 'interim.zip'}:
        raise ValueError('Unexpected source archive')
    return f'https://zenodo.org/records/8244887/files/{name}?download=1'


def read_member(archive: str, size: int, member: str) -> tuple[bytes, dict]:
    remote = RemoteZipBytes(archive_url(archive), size)
    with zipfile.ZipFile(remote) as source:
        info = source.getinfo(member)
        if info.file_size > 32 * 1024 * 1024:
            raise ValueError('Unexpectedly large selected ZIP member')
        content = source.read(info)
    return content, {'archive': archive, 'archive_size': size, 'member': member,
                     'uncompressed_bytes': len(content), 'zip_crc32': f'{info.CRC:08x}',
                     'bytes_fetched': remote.bytes_fetched,
                     'integrity': 'ZIP CRC32 verified; complete archive MD5 not verified for partial downloads'}
