"""Download public annual GWIS GlobFire GeoPackages to the ignored research cache."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import urlopen

from fire_sources import PRIVATE


def main():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    for year in (2022, 2023, 2024):
        compressed = PRIVATE / f'globfire_{year}.gpkg.gz'
        source = f'https://gwis.jrc.ec.europa.eu/downloads/country.profile/globfire_{year}.gpkg.gz'
        if not compressed.exists():
            print(f'Downloading {year}', flush=True)
            with urlopen(source, timeout=180) as response, compressed.open('wb') as output:
                shutil.copyfileobj(response, output)
        package = PRIVATE / f'globfire_{year}.gpkg'
        if not package.exists():
            print(f'Extracting {year}', flush=True)
            temporary = package.with_suffix('.gpkg.part')
            with gzip.open(compressed, 'rb') as input_stream, temporary.open('wb') as output:
                shutil.copyfileobj(input_stream, output)
            temporary.replace(package)
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        print(json.dumps({'year': year, 'source': source,
            'compressed_bytes': compressed.stat().st_size, 'gpkg_bytes': package.stat().st_size,
            'gpkg_sha256': digest}), flush=True)


if __name__ == '__main__':
    main()
