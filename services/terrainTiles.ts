import { decode } from "fast-png";
import type { Coordinate } from "./geoUtils";
import {
  buildTerrainElevationCacheKey,
  createTerrainGridCoordinates,
  type TerrainGridData,
} from "./terrainElevation";

export const TERRAIN_TILES_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium";
export const TERRAIN_TILES_ATTRIBUTION =
  "Elevación: Mapzen Terrain Tiles · SRTM/GMTED2010: USGS · ETOPO1: NOAA.";

const TILE_SIZE = 256;
const MAX_ZOOM = 12;
const MAX_TILES_PER_GRID = 9;
const MAX_CACHED_TILES = 32;
const MAX_MERCATOR_LATITUDE = 85.0511287798;
const REQUEST_TIMEOUT_MS = 15000;

export type TerrainTileFetch = (url: string, init?: { signal?: AbortSignal }) => Promise<{
  ok: boolean;
  status: number;
  arrayBuffer: () => Promise<ArrayBuffer>;
}>;

type Tile = ReturnType<typeof decode>;
type Pixel = { key: string; x: number; y: number };
const tiles = new Map<string, Promise<Tile>>();
const grids = new Map<string, Promise<TerrainGridData | null>>();

const pixelAt = ([latitude, longitude]: Coordinate, zoom: number): Pixel => {
  if (Math.abs(latitude) > MAX_MERCATOR_LATITUDE) throw new Error("El terreno queda fuera de la cobertura DEM.");
  const size = 2 ** zoom;
  const x = ((longitude + 180) / 360 * size + size) % size;
  const y = Math.min(size - Number.EPSILON * size, Math.max(0,
    (1 - Math.asinh(Math.tan(latitude * Math.PI / 180)) / Math.PI) / 2 * size));
  return {
    key: `${zoom}/${Math.floor(x)}/${Math.floor(y)}`,
    x: Math.min(TILE_SIZE - 1, Math.floor((x - Math.floor(x)) * TILE_SIZE)),
    y: Math.min(TILE_SIZE - 1, Math.floor((y - Math.floor(y)) * TILE_SIZE)),
  };
};

const readTile = (key: string, fetchFn: TerrainTileFetch): Promise<Tile> => {
  const cached = tiles.get(key);
  if (cached) {
    tiles.delete(key);
    tiles.set(key, cached);
    return cached;
  }
  const request = (async () => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const response = await fetchFn(`${TERRAIN_TILES_URL}/${key}.png`, { signal: controller.signal });
      if (!response.ok) throw new Error(`No se pudo descargar el terreno (HTTP ${response.status}).`);
      const tile = decode(await response.arrayBuffer(), { checkCrc: true });
      if (tile.width !== TILE_SIZE || tile.height !== TILE_SIZE || tile.depth !== 8 ||
          (tile.channels !== 3 && tile.channels !== 4)) {
        throw new Error("El mosaico DEM no tiene el formato Terrarium esperado.");
      }
      return tile;
    } finally {
      clearTimeout(timeout);
    }
  })();
  tiles.set(key, request);
  void request.catch(() => { if (tiles.get(key) === request) tiles.delete(key); });
  while (tiles.size > MAX_CACHED_TILES) tiles.delete(tiles.keys().next().value!);
  return request;
};

const loadGrid = async (
  route: readonly Coordinate[],
  fetchFn: TerrainTileFetch
): Promise<TerrainGridData | null> => {
  const geometry = createTerrainGridCoordinates(route);
  if (!geometry) return null;
  let zoom = MAX_ZOOM;
  let pixels = geometry.coordinates.map(coordinate => pixelAt(coordinate, zoom));
  while (new Set(pixels.map(pixel => pixel.key)).size > MAX_TILES_PER_GRID && zoom > 0) {
    zoom -= 1;
    pixels = geometry.coordinates.map(coordinate => pixelAt(coordinate, zoom));
  }
  const keys = [...new Set(pixels.map(pixel => pixel.key))];
  const loaded = new Map<string, Tile>();
  // Share adjacent tiles and keep native network/PNG decoding concurrency bounded.
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(3, keys.length) }, async () => {
    while (next < keys.length) {
      const key = keys[next++];
      loaded.set(key, await readTile(key, fetchFn));
    }
  }));
  const elevationsMeters = pixels.map(pixel => {
    const tile = loaded.get(pixel.key)!;
    const offset = (pixel.y * TILE_SIZE + pixel.x) * tile.channels;
    const elevation = tile.data[offset] * 256 + tile.data[offset + 1] + tile.data[offset + 2] / 256 - 32768;
    if ((tile.channels === 4 && tile.data[offset + 3] === 0) || elevation < -12000 || elevation > 9000) {
      throw new Error("El mosaico DEM contiene una altura no disponible.");
    }
    return elevation;
  });
  const { coordinates: _coordinates, ...grid } = geometry;
  return {
    grid: { ...grid, elevationsMeters,
      minElevationMeters: Math.min(...elevationsMeters), maxElevationMeters: Math.max(...elevationsMeters) },
    source: {
      provider: "AWS Terrain Tiles",
      dataset: "Mapzen Terrain Tiles",
      // Conservative floor for the mixed DEM sources; lower zooms may be coarser.
      resolutionMeters: Math.max(90, Math.ceil(156543.03392 / 2 ** zoom)),
      endpoint: TERRAIN_TILES_URL,
      attribution: TERRAIN_TILES_ATTRIBUTION,
      fetchedAt: new Date().toISOString(),
    },
  };
};

export const clearTerrainTileCache = () => { tiles.clear(); grids.clear(); };

export const peekTerrainTileGrid = (trailKey: string | number, route: readonly Coordinate[]) =>
  grids.get(buildTerrainElevationCacheKey(trailKey, route)) ?? null;

export const getTerrainTileGrid = (
  trailKey: string | number,
  route: readonly Coordinate[],
  fetchFn: TerrainTileFetch = (url, init) => fetch(url, init)
): Promise<TerrainGridData | null> => {
  const key = buildTerrainElevationCacheKey(trailKey, route);
  const cached = grids.get(key);
  if (cached) return cached;
  const request = loadGrid(route, fetchFn).catch(() => null).then(data => {
    if (!data && grids.get(key) === request) grids.delete(key);
    return data;
  });
  grids.set(key, request);
  return request;
};
