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
  const configured = layer === "standard" ? process.env.EXPO_PUBLIC_OFFLINE_STANDARD_TILE_URL
    : layer === "terrain" ? process.env.EXPO_PUBLIC_OFFLINE_TERRAIN_TILE_URL : null;
  if (configured) return configured.replace("{z}", String(zoom)).replace("{x}", String(tileX)).replace("{y}", String(y));

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
      | "provider-not-configured"
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
  if (layer === "satellite" || !FileSystem.documentDirectory) return null;

  const localUri = getTileLocalUri(layer, zoom, x, y);
  const info = await FileSystem.getInfoAsync(localUri);

  return isUsableTileInfo(info) ? localUri : null;
};

export const getOfflineTilePlanForTrail = (trail: Trail): TileDescriptor[] => {
  const route = parseRouteCoordinates(trail.route_coordinates);
  if (!route.length && (trail.center_lat == null || trail.center_lng == null)) return [];
  const fallbackCenter: Coordinate = [
    trail.center_lat ?? DEFAULT_CENTER[0],
    trail.center_lng ?? DEFAULT_CENTER[1],
  ];
  const points = route.length > 0 ? route : [fallbackCenter];
  const baseZoom = clamp(trail.map_zoom ?? DEFAULT_ZOOM, MIN_ZOOM, 15);
  // Never truncate a layer or a route halfway. Reduce resolution until the
  // complete bounds (including a one-tile margin) fit for BOTH layers.
  let zooms: number[] = [];
  for (let top = Math.min(15, baseZoom + 1); top >= MIN_ZOOM; top--) {
    const candidate = Array.from(new Set([Math.max(MIN_ZOOM, top - 2), Math.max(MIN_ZOOM, top - 1), top]));
    const count = candidate.reduce((sum, zoom) => {
      const bounds = getTileBounds(points, zoom, 1);
      return sum + (bounds.maxX - bounds.minX + 1) * (bounds.maxY - bounds.minY + 1) * 2;
    }, 0);
    if (count <= MAX_DOWNLOAD_TILES) { zooms = candidate; break; }
  }
  const tiles = new Map<string, TileDescriptor>();
  for (const layer of ["standard", "terrain"] as CachedMapLayer[]) {
    for (const zoom of zooms) addTilesForLayerAndZoom(tiles, layer, zoom, points);
  }

  return Array.from(tiles.values());
};

const addTilesForLayerAndZoom = (
  tiles: Map<string, TileDescriptor>,
  layer: CachedMapLayer,
  zoom: number,
  points: Coordinate[]
) => {
  const bounds = getTileBounds(points, zoom, 1);

  for (let x = bounds.minX; x <= bounds.maxX; x += 1) {
    addTilesForColumn(tiles, layer, zoom, x, bounds);
  }
};

const addTilesForColumn = (
  tiles: Map<string, TileDescriptor>,
  layer: CachedMapLayer,
  zoom: number,
  x: number,
  bounds: ReturnType<typeof getTileBounds>
) => {
  for (let y = bounds.minY; y <= bounds.maxY; y += 1) {
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
};

const getTileBounds = (points: Coordinate[], zoom: number, buffer: number) => {
  const projectedPoints = points.map((point) => project(point, zoom));
  const xValues = projectedPoints.map((point) => point.x);
  const yValues = projectedPoints.map((point) => point.y);

  return {
    minX: Math.floor(Math.min(...xValues) / TILE_SIZE) - buffer,
    maxX: Math.floor(Math.max(...xValues) / TILE_SIZE) + buffer,
    minY: Math.floor(Math.min(...yValues) / TILE_SIZE) - buffer,
    maxY: Math.floor(Math.max(...yValues) / TILE_SIZE) + buffer,
  };
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

  const providers = [process.env.EXPO_PUBLIC_OFFLINE_STANDARD_TILE_URL, process.env.EXPO_PUBLIC_OFFLINE_TERRAIN_TILE_URL];
  if (providers.some((url) => !url || !url.startsWith("https://") || !["{z}", "{x}", "{y}"].every((part) => url.includes(part)) || /(^|\.)tile\.openstreetmap\.org$/i.test(new URL(url).hostname))) {
    throw new MapTileDownloadError("provider-not-configured", "La descarga del mapa base requiere configurar un proveedor que permita uso offline. El trazado y los reportes quedan guardados en este teléfono.");
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
    const downloadedTile = await downloadTileIfNeeded(tile, {
      downloadedTiles,
      totalTiles: tileList.length,
      shouldCancel: options.shouldCancel,
    });

    totalBytes += downloadedTile.sizeBytes;
    downloadedTiles += 1;
    onProgress?.(downloadedTiles, tileList.length);
  }

  return {
    downloadedTiles,
    totalTiles: tileList.length,
    sizeMb: Math.max(1, Math.ceil((totalBytes / 1024 / 1024) * 10) / 10),
  };
};

const throwDownloadCancelled = (downloadedTiles: number, totalTiles: number) => {
  throw new MapTileDownloadError(
    "download-cancelled",
    "La descarga de tiles fue cancelada antes de completar el mapa.",
    { downloadedTiles, totalTiles }
  );
};

const downloadTileIfNeeded = async (
  tile: TileDescriptor,
  context: {
    downloadedTiles: number;
    totalTiles: number;
    shouldCancel?: () => boolean;
  }
) => {
  if (context.shouldCancel?.()) {
    throwDownloadCancelled(context.downloadedTiles, context.totalTiles);
  }

  await ensureDirectory(tile.localUri.slice(0, tile.localUri.lastIndexOf("/") + 1));

  const existing = await FileSystem.getInfoAsync(tile.localUri);
  if (isUsableTileInfo(existing)) {
    return { sizeBytes: getTileSize(existing) };
  }

  if (existing.exists) {
    await removeFileIfPresent(tile.localUri);
  }

  return downloadTileToLocalFile(tile, context);
};

const downloadTileToLocalFile = async (
  tile: TileDescriptor,
  context: {
    downloadedTiles: number;
    totalTiles: number;
    shouldCancel?: () => boolean;
  }
) => {
  const tempUri = `${tile.localUri}.download`;

  try {
    await removeFileIfPresent(tempUri);
    const result = await FileSystem.downloadAsync(tile.url, tempUri);

    if (context.shouldCancel?.()) {
      await removeFileIfPresent(tempUri).catch(() => undefined);
      throwDownloadCancelled(context.downloadedTiles, context.totalTiles);
    }

    if (result.status < 200 || result.status >= 300) {
      throw new Error(`HTTP ${result.status}`);
    }

    const tempInfo = await FileSystem.getInfoAsync(tempUri);
    if (!isUsableTileInfo(tempInfo)) {
      throw new Error("invalid-tile-file");
    }

    await FileSystem.moveAsync({ from: tempUri, to: tile.localUri });
    return { sizeBytes: getTileSize(tempInfo) };
  } catch (error) {
    await removeFileIfPresent(tempUri).catch(() => undefined);
    throwTileDownloadError(error, tile, context);
  }

  throw new Error("unreachable-tile-download-state");
};

const throwTileDownloadError = (
  error: unknown,
  tile: TileDescriptor,
  context: { downloadedTiles: number; totalTiles: number }
) => {
  if (error instanceof MapTileDownloadError && error.code === "download-cancelled") {
    throw error;
  }

  throw new MapTileDownloadError(
    "tile-download-failed",
    "La descarga de tiles se interrumpio antes de completar el mapa.",
    {
      downloadedTiles: context.downloadedTiles,
      totalTiles: context.totalTiles,
      tile: {
        layer: tile.layer,
        zoom: tile.zoom,
        x: tile.x,
        y: tile.y,
        url: tile.url,
      },
    }
  );
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
