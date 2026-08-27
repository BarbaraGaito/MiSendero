import * as FileSystem from "expo-file-system/legacy";
import { Trail } from "../types";
import { Coordinate, parseRouteCoordinates } from "./geoUtils";

export type CachedMapLayer = "standard" | "terrain";

export interface TileCacheResult {
  downloadedTiles: number;
  totalTiles: number;
  sizeMb: number;
}

export interface OfflineTileDownloadOptions {
  shouldCancel?: () => boolean;
}

export interface OfflineTileCoverage {
  availableTiles: number;
  totalTiles: number;
  sizeMb: number;
  isComplete: boolean;
}

type TileDescriptor = {
  layer: CachedMapLayer;
  zoom: number;
  x: number;
  y: number;
  url: string;
  localUri: string;
};

const TILE_SIZE = 256;
const DEFAULT_ZOOM = 13;
const MIN_ZOOM = 10;
const MAX_DOWNLOAD_TILES = 220;
const MIN_VALID_TILE_BYTES = 96;
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

type TileFileInfo = Awaited<ReturnType<typeof FileSystem.getInfoAsync>> & {
  exists: true;
  size: number;
};

const isUsableTileInfo = (
  info: Awaited<ReturnType<typeof FileSystem.getInfoAsync>>
): info is TileFileInfo =>
  info.exists &&
  "size" in info &&
  typeof info.size === "number" &&
  info.size >= MIN_VALID_TILE_BYTES;

const getTileSize = (info: Awaited<ReturnType<typeof FileSystem.getInfoAsync>>) =>
  isUsableTileInfo(info) ? info.size ?? 0 : 0;

const removeFileIfPresent = async (uri: string) => {
  const info = await FileSystem.getInfoAsync(uri);

  if (info.exists) {
    await FileSystem.deleteAsync(uri, { idempotent: true });
  }
};

export class MapTileDownloadError extends Error {
  constructor(
    public readonly code:
      | "storage-unavailable"
      | "empty-tile-plan"
      | "download-cancelled"
      | "tile-download-failed",
    message: string,
    public readonly details?: {
      downloadedTiles?: number;
      totalTiles?: number;
      tile?: Pick<TileDescriptor, "layer" | "zoom" | "x" | "y" | "url">;
    }
  ) {
    super(message);
    this.name = "MapTileDownloadError";
  }
}

export const resolveCachedTileUri = async (
  layer: CachedMapLayer | "satellite",
  zoom: number,
  x: number,
  y: number
) => {
  if (layer === "satellite") return null;

  const localUri = getTileLocalUri(layer, zoom, x, y);
  const info = await FileSystem.getInfoAsync(localUri);

  return isUsableTileInfo(info) ? localUri : null;
};

export const getOfflineTilePlanForTrail = (trail: Trail): TileDescriptor[] => {
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
  const layers: CachedMapLayer[] = ["standard", "terrain"];
  const tiles = new Map<string, TileDescriptor>();

  for (const layer of layers) {
    for (const zoom of zooms) {
      if (tiles.size >= MAX_DOWNLOAD_TILES) break;

      const projectedPoints = points.map((point) => project(point, zoom));
      const minTileX = Math.floor(Math.min(...projectedPoints.map((point) => point.x)) / TILE_SIZE);
      const maxTileX = Math.floor(Math.max(...projectedPoints.map((point) => point.x)) / TILE_SIZE);
      const minTileY = Math.floor(Math.min(...projectedPoints.map((point) => point.y)) / TILE_SIZE);
      const maxTileY = Math.floor(Math.max(...projectedPoints.map((point) => point.y)) / TILE_SIZE);
      const buffer = 1;

      for (let x = minTileX - buffer; x <= maxTileX + buffer; x += 1) {
        for (let y = minTileY - buffer; y <= maxTileY + buffer; y += 1) {
          if (y < 0 || y >= 2 ** zoom) continue;

          const tileX = wrapTileX(x, zoom);
          const key = `${layer}-${zoom}-${tileX}-${y}`;

          if (tiles.size >= MAX_DOWNLOAD_TILES) break;

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
    }
  }

  return Array.from(tiles.values());
};

export const getOfflineTileCoverageForTrail = async (
  trail: Trail
): Promise<OfflineTileCoverage> => {
  if (!FileSystem.documentDirectory) {
    return { availableTiles: 0, totalTiles: 0, sizeMb: 0, isComplete: false };
  }

  const tileList = getOfflineTilePlanForTrail(trail);
  let availableTiles = 0;
  let totalBytes = 0;

  for (const tile of tileList) {
    const info = await FileSystem.getInfoAsync(tile.localUri);

    if (isUsableTileInfo(info)) {
      availableTiles += 1;
      totalBytes += getTileSize(info);
    }
  }

  return {
    availableTiles,
    totalTiles: tileList.length,
    sizeMb: Math.max(0, Math.ceil((totalBytes / 1024 / 1024) * 10) / 10),
    isComplete: tileList.length > 0 && availableTiles === tileList.length,
  };
};

export const downloadOfflineTilesForTrail = async (
  trail: Trail,
  onProgress?: (downloaded: number, total: number) => void,
  options: OfflineTileDownloadOptions = {}
): Promise<TileCacheResult> => {
  if (!FileSystem.documentDirectory) {
    throw new MapTileDownloadError(
      "storage-unavailable",
      "No hay almacenamiento local disponible para guardar tiles offline."
    );
  }

  await ensureDirectory(TILE_CACHE_DIR);

  const tileList = getOfflineTilePlanForTrail(trail);

  if (tileList.length === 0) {
    throw new MapTileDownloadError(
      "empty-tile-plan",
      "No se pudo calcular una zona de descarga para esta ruta."
    );
  }

  let downloadedTiles = 0;
  let totalBytes = 0;

  for (const tile of tileList) {
    if (options.shouldCancel?.()) {
      throw new MapTileDownloadError(
        "download-cancelled",
        "La descarga de tiles fue cancelada antes de completar el mapa.",
        { downloadedTiles, totalTiles: tileList.length }
      );
    }

    const directory = tile.localUri.slice(0, tile.localUri.lastIndexOf("/") + 1);
    await ensureDirectory(directory);

    const existing = await FileSystem.getInfoAsync(tile.localUri);

    if (isUsableTileInfo(existing)) {
      totalBytes += getTileSize(existing);
      downloadedTiles += 1;
      onProgress?.(downloadedTiles, tileList.length);
      continue;
    }

    if (existing.exists) {
      await removeFileIfPresent(tile.localUri);
    }

    const tempUri = `${tile.localUri}.download`;

    try {
      await removeFileIfPresent(tempUri);
      const result = await FileSystem.downloadAsync(tile.url, tempUri);

      if (options.shouldCancel?.()) {
        await removeFileIfPresent(tempUri).catch(() => undefined);
        throw new MapTileDownloadError(
          "download-cancelled",
          "La descarga de tiles fue cancelada antes de completar el mapa.",
          { downloadedTiles, totalTiles: tileList.length }
        );
      }

      if (result.status < 200 || result.status >= 300) {
        throw new Error(`HTTP ${result.status}`);
      }

      const tempInfo = await FileSystem.getInfoAsync(tempUri);

      if (!isUsableTileInfo(tempInfo)) {
        throw new Error("invalid-tile-file");
      }

      await FileSystem.moveAsync({ from: tempUri, to: tile.localUri });

      totalBytes += getTileSize(tempInfo);
      downloadedTiles += 1;
      onProgress?.(downloadedTiles, tileList.length);
    } catch (error) {
      await removeFileIfPresent(tempUri).catch(() => undefined);

      if (
        error instanceof MapTileDownloadError &&
        error.code === "download-cancelled"
      ) {
        throw error;
      }

      throw new MapTileDownloadError(
        "tile-download-failed",
        "La descarga de tiles se interrumpio antes de completar el mapa.",
        {
          downloadedTiles,
          totalTiles: tileList.length,
          tile: {
            layer: tile.layer,
            zoom: tile.zoom,
            x: tile.x,
            y: tile.y,
            url: tile.url,
          },
        }
      );
    }
  }

  return {
    downloadedTiles,
    totalTiles: tileList.length,
    sizeMb: Math.max(1, Math.ceil((totalBytes / 1024 / 1024) * 10) / 10),
  };
};

export const deleteOfflineTilesForTrail = async (trail: Trail): Promise<number> => {
  if (!FileSystem.documentDirectory) return 0;

  const tileList = getOfflineTilePlanForTrail(trail);
  let deletedTiles = 0;

  for (const tile of tileList) {
    const info = await FileSystem.getInfoAsync(tile.localUri);

    if (info.exists) {
      await FileSystem.deleteAsync(tile.localUri, { idempotent: true });
      deletedTiles += 1;
    }

    await removeFileIfPresent(`${tile.localUri}.download`).catch(() => undefined);
  }

  return deletedTiles;
};
