"""Acquire missing public MOD14A1.061 COGs for in-app Argentine trail tiles.

Only tiles absent from the local cache are requested. COG bytes and unsigned
source provenance are kept in the ignored research cache; signed URLs are
transient and never printed or persisted.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from environmental_sources import ROOT

ROUTE_FILES = (ROOT / "backend/src/data/additionalTrailRoutes.json",
               ROOT / "backend/src/data/catalogExpansionRoutes20261017.json")
RASTER_DIR = ROOT / "training/data/raw/environmental/fire-mod14a1"
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "modis-14A1-061"
START = "2022-01-01T00:00:00Z"
END = "2026-11-01T00:00:00Z"
_SAS_LOCK = threading.Lock()
_SAS_TOKEN: dict | None = None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def route_samples(points: list[list[float]]) -> list[tuple[float, float]]:
    samples = []
    for first, second in zip(points, points[1:]):
        lat1, lon1 = first
        lat2, lon2 = second
        mean_lat = math.radians((lat1 + lat2) / 2)
        length = math.hypot((lon2 - lon1) * 111_320 * math.cos(mean_lat),
                            (lat2 - lat1) * 110_574)
        steps = max(1, math.ceil(length / 1000))
        samples.extend((lat1 + (lat2 - lat1) * i / steps,
                        lon1 + (lon2 - lon1) * i / steps) for i in range(steps))
    samples.append(tuple(points[-1]))
    return samples


def modis_tile(latitude: float, longitude: float) -> str:
    radius, width = 6_371_007.181, 1_111_950.5196666667
    x = radius * math.radians(longitude) * math.cos(math.radians(latitude))
    y = radius * math.radians(latitude)
    h = math.floor((x + 20_015_109.354) / width)
    v = math.floor((10_007_554.677 - y) / width)
    return f"h{h:02d}v{v:02d}"


def request_json(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/geo+json", "User-Agent": "MiSendero-thesis-research/1.0"})
    for attempt in range(5):
        try:
            with urlopen(request, timeout=90) as response:
                data = json.loads(response.read())
            break
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 4:
                raise
            time.sleep(min(60, int(error.headers.get("Retry-After", 2 ** (attempt + 1)))))
        except URLError:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
    if not isinstance(data, dict):
        raise ValueError("STAC response is not a JSON object")
    return data


def items_for_tile(tile: str) -> list[dict]:
    h, v = int(tile[1:3]), int(tile[4:6])
    params = {"collections": COLLECTION,
        "query": json.dumps({"platform": {"eq": "terra"},
                             "modis:horizontal-tile": {"eq": h},
                             "modis:vertical-tile": {"eq": v}}, separators=(",", ":")),
        "datetime": f"{START}/{END}", "limit": 1000}
    url = f"{STAC}/search?{urlencode(params)}"
    first = request_json(url)
    features = list(first.get("features", []))
    next_links = [link for link in first.get("links", []) if link.get("rel") == "next"]
    while next_links:
        link = next_links.pop(0)
        page = request_json(link["href"])
        features.extend(page.get("features", []))
        next_links.extend(item for item in page.get("links", []) if item.get("rel") == "next")
    by_start = {}
    for item in features:
        props = item.get("properties", {})
        item_id = item.get("id", "")
        if (props.get("platform") != "terra"
                or props.get("modis:horizontal-tile") != h
                or props.get("modis:vertical-tile") != v
                or not item_id.startswith("MOD14A1.A20")):
            raise ValueError(f"Unexpected STAC result for {tile}")
        start = props.get("start_datetime")
        if not start:
            raise ValueError(f"Missing start date for {item_id}")
        if start not in by_start or item_id > by_start[start]["id"]:
            by_start[start] = item
    return sorted(by_start.values(), key=lambda item: item["id"])


def signed_href(href: str) -> tuple[str, str]:
    global _SAS_TOKEN
    parsed = urlparse(href)
    if parsed.scheme != "https" or parsed.hostname != "modiseuwest.blob.core.windows.net" or parsed.query:
        raise ValueError("Unexpected original asset origin")
    with _SAS_LOCK:
        token = _SAS_TOKEN
        if token is None or token["expires"] <= datetime.now(timezone.utc).timestamp() + 300:
            sign_url = "https://planetarycomputer.microsoft.com/api/sas/v1/sign?" + urlencode({"href": href})
            signed = request_json(sign_url)
            signed_href_value = signed.get("href", "")
            signed_parsed = urlparse(signed_href_value)
            params = parse_qs(signed_parsed.query)
            if (signed_parsed.hostname != parsed.hostname or params.get("sr") != ["c"]
                    or not params.get("se") or not params.get("sig")):
                raise ValueError("Planetary Computer did not return a reusable container token")
            expires = datetime.fromisoformat(params["se"][0].replace("Z", "+00:00")).timestamp()
            _SAS_TOKEN = token = {"query": signed_parsed.query, "expires": expires}
    return href + "?" + token["query"], str(token["expires"])


def download_asset(item: dict, band: str) -> dict:
    item_id = item["id"]
    asset = item.get("assets", {}).get(band)
    if not asset or not asset.get("href"):
        raise ValueError(f"Missing {band} asset for {item_id}")
    output = RASTER_DIR / f"{item_id}_{band}.tif"
    sidecar = output.with_suffix(".source.json")
    original_href = asset["href"]
    if output.is_file() and sidecar.is_file():
        source = json.loads(sidecar.read_text(encoding="utf-8"))
        if source.get("url") == original_href and source.get("sha256") == sha256_file(output):
            return {"item_id": item_id, "band": band, "bytes": output.stat().st_size,
                    "sha256": source["sha256"], "status": "cached_verified"}
        raise ValueError(f"Existing {item_id} {band} asset failed provenance verification")
    signed_url, _ = signed_href(original_href)
    request = Request(signed_url, headers={"Accept": "image/tiff"})
    for attempt in range(5):
        try:
            with urlopen(request, timeout=120) as response:
                content = response.read()
                last_modified = response.headers.get("Last-Modified")
            break
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 4:
                raise RuntimeError(f"Public asset download failed for {item_id} {band}; HTTP {error.code}") from None
            time.sleep(min(60, int(error.headers.get("Retry-After", 2 ** (attempt + 1)))))
        except URLError as error:
            if attempt == 4:
                raise RuntimeError(f"Public asset download failed for {item_id} {band}; {type(error).__name__}") from None
            time.sleep(2 ** attempt)
    if content[:4] not in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+") or not last_modified:
        raise ValueError(f"Expected original TIFF and source Last-Modified for {item_id} {band}")
    RASTER_DIR.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".part")
    temporary.write_bytes(content)
    temporary.replace(output)
    source = {"url": original_href, "sha256": sha256_bytes(content), "bytes": len(content),
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "last_modified": last_modified,
        "relative_path": output.relative_to(ROOT).as_posix(), "collection": COLLECTION}
    sidecar.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    return {"item_id": item_id, "band": band, "bytes": len(content),
            "sha256": source["sha256"], "status": "downloaded"}


def main() -> None:
    routes = {}
    for path in ROUTE_FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        for name, route in data.items():
            if len(route.get("points") or []) < 2 or not route.get("source_url"):
                raise ValueError(f"Route lacks sourced geometry: {name}")
            routes[name] = route
    required_tiles = {modis_tile(lat, lon) for route in routes.values()
                      for lat, lon in route_samples(route["points"])}
    items = []
    missing_tiles = []
    for tile in sorted(required_tiles):
        tile_items = items_for_tile(tile)
        tile_has_missing = False
        for item in tile_items:
            for band in ("FireMask", "QA"):
                path = RASTER_DIR / f"{item['id']}_{band}.tif"
                sidecar = path.with_suffix(".source.json")
                if path.is_file() and sidecar.is_file():
                    source = json.loads(sidecar.read_text(encoding="utf-8"))
                    if source.get("url") != item["assets"][band]["href"] or source.get("sha256") != sha256_file(path):
                        raise ValueError(f"Cached source mismatch for {item['id']} {band}")
                else:
                    tile_has_missing = True
        if tile_has_missing:
            missing_tiles.append(tile)
        items.extend(tile_items)
        print(f"{tile}: {len(tile_items)} granules; {'downloads required' if tile_has_missing else 'cache verified'}", flush=True)
    if not items:
        raise ValueError("STAC returned no MOD14A1 items for required trail tiles")
    if not missing_tiles:
        print(json.dumps({"status": "all_route_assets_already_cached_and_verified",
                          "required_tiles": sorted(required_tiles)}))
        return
    results = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(download_asset, item, band)
                   for item in items for band in ("FireMask", "QA")]
        for future in as_completed(futures):
            results.append(future.result())
    summary = {"experiment_id": "missing-in-app-trail-tiles-mod14a1-2022-2026-10",
        "period": {"start_inclusive": START, "end_exclusive": END},
        "required_tiles": sorted(required_tiles), "tiles_with_downloads": missing_tiles,
        "downloaded_tiles": missing_tiles, "granules": len(items),
        "assets": len(results), "bytes": sum(row["bytes"] for row in results),
        "sha256_by_asset": {f"{row['item_id']}_{row['band']}": row["sha256"] for row in results},
        "route_file_sha256": {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in ROUTE_FILES},
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "synthetic_observations": 0, "deployment_approved": False}
    manifest = ROOT / "training/data/environmental/private/missing-in-app-trail-tiles-mod14a1-manifest.json"
    manifest.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("required_tiles", "downloaded_tiles", "granules", "assets", "bytes")}, indent=2))


if __name__ == "__main__":
    main()
