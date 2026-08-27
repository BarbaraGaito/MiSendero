import * as FileSystem from "expo-file-system/legacy";
import { Trail } from "../types";
import { Coordinate, parseRouteCoordinates } from "./geoUtils";

export type CachedMapLayer = "standard" | "terrain";

export interface TileCacheResult {
  downloadedTiles: number;
  totalTiles: number;
  sizeMb: number;
}

const TILE_SIZE = 256;
const DEFAULT_ZOOM = 13;
const MIN_ZOOM = 10;
const MAX_DOWNLOAD_TILES = 220;
const TILE_CACHE_DIR = `${FileSystem.documentDirectory || ""}misendero-tiles/`;
const DEFAULT_CENTER: Coordinate = [-41.1734, -71.4752];

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));

const project = ([latitude, longitude]: Coordinate, zoom: number) => {
  const latRad = (latitude * Math.PI) / 180;
  const scale = TILE_SIZE * 2 ** zoom;

  return {
    x: ((longitude + 180) / 360) * scale,
    y:
      ((1 -
        Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) /
        2) *
      scale,
  };
};

const wrapTileX = (x: number, zoom: number) => {
  const max = 2 ** zoom;
  return ((x % max) + max) % max;
};

export const getTileRemoteUrl = (
  layer: CachedMapLayer | "satellite",
  zoom: number,
  x: number,
  y: number
) => {
  const tileX = wrapTileX(x, zoom);

  if (layer === "terrain") {
    return `https://services.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/${zoom}/${y}/${tileX}`;
  }

  if (layer === "satellite") {
    return `https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${zoom}/${y}/${tileX}`;
  }

  return `https://tile.openstreetmap.org/${zoom}/${tileX}/${y}.png`;
};

const getTileLocalUri = (
  layer: CachedMapLayer,
  zoom: number,
  x: number,
  y: number
) => `${TILE_CACHE_DIR}${layer}/${zoom}/${wrapTileX(x, zoom)}/${y}.png`;

const ensureDirectory = async (uri: string) => {
  const info = await FileSystem.getInfoAsync(uri);

  if (!info.exists) {
    await FileSystem.makeDirectoryAsync(uri, { intermediates: true });
  }
};

export const resolveCachedTileUri = async (
  layer: CachedMapLayer | "satellite",
  zoom: number,
  x: number,
  y: number
) => {
  if (layer === "satellite") return null;

  const localUri = getTileLocalUri(layer, zoom, x, y);
  const info = await FileSystem.getInfoAsync(localUri);

  return info.exists ? localUri : null;
};

type TileDownloadItem = {
  layer: CachedMapLayer;
  zoom: number;
  x: number;
  y: number;
  url: string;
  localUri: string;
};

const getTileBounds = (points: Coordinate[], zoom: number) => {
  const projectedPoints = points.map((point) => project(point, zoom));
  const xs = projectedPoints.map((point) => point.x);
  const ys = projectedPoints.map((point) => point.y);

  return {
    minTileX: Math.floor(Math.min(...xs) / TILE_SIZE),
    maxTileX: Math.floor(Math.max(...xs) / TILE_SIZE),
    minTileY: Math.floor(Math.min(...ys) / TILE_SIZE),
    maxTileY: Math.floor(Math.max(...ys) / TILE_SIZE),
  };
};

const addTilesForLayerZoom = (
  tiles: Map<string, TileDownloadItem>,
  layer: CachedMapLayer,
  zoom: number,
  points: Coordinate[]
) => {
  const { minTileX, maxTileX, minTileY, maxTileY } = getTileBounds(points, zoom);
  const buffer = 1;

  for (let x = minTileX - buffer; x <= maxTileX + buffer; x += 1) {
    for (let y = minTileY - buffer; y <= maxTileY + buffer; y += 1) {
      if (tiles.size >= MAX_DOWNLOAD_TILES) return;
      if (y < 0 || y >= 2 ** zoom) continue;

      const tileX = wrapTileX(x, zoom);
      const key = `${layer}-${zoom}-${tileX}-${y}`;

      tiles.set(key, {
        layer,
        zoom,
        x: tileX,
        y,
        url: getTileRemoteUrl(layer, zoom, tileX, y),
        localUri: getTileLocalUri(layer, zoom, tileX, y),
      });
    }
  }
};

const getTilesForTrail = (trail: Trail): TileDownloadItem[] => {
  const route = parseRouteCoordinates(trail.route_coordinates);
  const fallbackCenter: Coordinate = [
    trail.center_lat ?? DEFAULT_CENTER[0],
    trail.center_lng ?? DEFAULT_CENTER[1],
  ];
  const points = route.length > 0 ? route : [fallbackCenter];
  const baseZoom = clamp(trail.map_zoom ?? DEFAULT_ZOOM, MIN_ZOOM, 15);
  const zooms = Array.from(
    new Set([baseZoom - 1, baseZoom, baseZoom + 1].map((zoom) => clamp(zoom, MIN_ZOOM, 15)))
  );
  const tiles = new Map<string, TileDownloadItem>();

  for (const layer of ["standard", "terrain"] as CachedMapLayer[]) {
    for (const zoom of zooms) {
      addTilesForLayerZoom(tiles, layer, zoom, points);
    }
  }

  return Array.from(tiles.values());
};

const downloadTile = async (tile: TileDownloadItem) => {
  const directory = tile.localUri.slice(0, tile.localUri.lastIndexOf("/") + 1);
  await ensureDirectory(directory);

  const existing = await FileSystem.getInfoAsync(tile.localUri);

  if (!existing.exists) {
    await FileSystem.downloadAsync(tile.url, tile.localUri);
  }

  const info = await FileSystem.getInfoAsync(tile.localUri);
  return info.exists && "size" in info ? info.size ?? 0 : 0;
};

export const downloadOfflineTilesForTrail = async (
  trail: Trail,
  onProgress?: (downloaded: number, total: number) => void
): Promise<TileCacheResult> => {
  if (!FileSystem.documentDirectory) {
    return { downloadedTiles: 0, totalTiles: 0, sizeMb: 0 };
  }

  await ensureDirectory(TILE_CACHE_DIR);

  const tileList = getTilesForTrail(trail);
  let downloadedTiles = 0;
  let totalBytes = 0;

  for (const tile of tileList) {
    totalBytes += await downloadTile(tile);
    downloadedTiles += 1;
    onProgress?.(downloadedTiles, tileList.length);
  }

  return {
    downloadedTiles,
    totalTiles: tileList.length,
    sizeMb: Math.max(1, Math.ceil((totalBytes / 1024 / 1024) * 10) / 10),
  };
};
