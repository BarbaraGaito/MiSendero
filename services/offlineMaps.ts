import { db } from "../database/connection";
import { Trail, TrailReport } from "../types";
import { getAuthSession } from "./authSession";
import { initDB } from "../database/database";
import { sanitizeReports } from "./reportPrivacy";
import {
  deleteOfflineTilesForTrail,
  downloadOfflineTilesForTrail,
  getOfflineTileCoverageForTrail,
  OfflineTileDownloadOptions,
} from "./mapTileCache";
import { Coordinate, parseRouteCoordinates } from "./geoUtils";
import {
  buildTerrainElevationCacheKey,
  TerrainGridData,
} from "./terrainElevation";

// Compatibility with DEM grids saved by older app versions. New map downloads
// contain only the basic map, route and available trail metadata.
export type OfflineTerrainGrid = TerrainGridData & {
  version: 1;
  // Mismo SHA-256 de geometria que el perfil descargado (trail.elevation).
  geometry_hash: string;
  // Clave del trazado consultado; si la ruta cambia, la grilla se descarta.
  route_key: string;
};

export interface OfflineMap {
  id: number;
  userId: number | null;
  trailId: number | null;
  name: string;
  sizeMb: number;
  status: string;
  downloadedAt: number;
  updatedAt: number;
  downloadedTiles: number;
  totalTiles: number;
  verifiedAt: number | null;
  lastError: string | null;
  trail: Trail | null;
  reports: TrailReport[];
  terrain: OfflineTerrainGrid | null;
}

export interface OfflineMapsSummary {
  count: number;
  totalSizeMb: number;
}

const initOfflineMapsTable = async () => {
  await initDB();
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS offline_maps (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      name TEXT NOT NULL,
      size_mb REAL NOT NULL,
      status TEXT NOT NULL,
      downloaded_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL,
      trail_id INTEGER,
      trail_json TEXT,
      reports_json TEXT,
      downloaded_tiles INTEGER NOT NULL DEFAULT 0,
      total_tiles INTEGER NOT NULL DEFAULT 0,
      verified_at INTEGER,
      last_error TEXT,
      terrain_json TEXT
    );
  `);

  const columns = await db.getAllAsync<{ name: string }>(
    `PRAGMA table_info(offline_maps)`
  );
  const columnNames = columns.map((column) => column.name);

  if (!columnNames.includes("trail_id")) {
    await db.execAsync(`ALTER TABLE offline_maps ADD COLUMN trail_id INTEGER;`);
  }

  if (!columnNames.includes("user_id")) {
    await db.execAsync(`ALTER TABLE offline_maps ADD COLUMN user_id INTEGER;`);
  }

  if (!columnNames.includes("trail_json")) {
    await db.execAsync(`ALTER TABLE offline_maps ADD COLUMN trail_json TEXT;`);
  }

  if (!columnNames.includes("reports_json")) {
    await db.execAsync(`ALTER TABLE offline_maps ADD COLUMN reports_json TEXT;`);
  }

  if (!columnNames.includes("downloaded_tiles")) {
    await db.execAsync(`ALTER TABLE offline_maps ADD COLUMN downloaded_tiles INTEGER NOT NULL DEFAULT 0;`);
  }

  if (!columnNames.includes("total_tiles")) {
    await db.execAsync(`ALTER TABLE offline_maps ADD COLUMN total_tiles INTEGER NOT NULL DEFAULT 0;`);
  }

  if (!columnNames.includes("verified_at")) {
    await db.execAsync(`ALTER TABLE offline_maps ADD COLUMN verified_at INTEGER;`);
  }

  if (!columnNames.includes("last_error")) {
    await db.execAsync(`ALTER TABLE offline_maps ADD COLUMN last_error TEXT;`);
  }

  if (!columnNames.includes("terrain_json")) {
    await db.execAsync(`ALTER TABLE offline_maps ADD COLUMN terrain_json TEXT;`);
  }
  const cached = await db.getAllAsync<{ id: number; reports_json: string | null }>("SELECT id, reports_json FROM offline_maps WHERE reports_json IS NOT NULL");
  for (const row of cached) {
    const clean = JSON.stringify(sanitizeReports(parseJson<TrailReport[]>(row.reports_json, [])));
    if (clean !== row.reports_json) await db.runAsync("UPDATE offline_maps SET reports_json = ? WHERE id = ?", [clean, row.id]);
  }
};

const parseJson = <T>(value: string | null, fallback: T): T => {
  if (!value) return fallback;

  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
};

const offlineMapColumns = `
  id,
  user_id,
  trail_id,
  name,
  size_mb,
  status,
  downloaded_at,
  updated_at,
  downloaded_tiles,
  total_tiles,
  verified_at,
  last_error,
  trail_json,
  reports_json,
  terrain_json
`;

type OfflineMapRow = {
  id: number;
  user_id: number | null;
  trail_id: number | null;
  name: string;
  size_mb: number;
  status: string;
  downloaded_at: number;
  updated_at: number;
  downloaded_tiles: number | null;
  total_tiles: number | null;
  verified_at: number | null;
  last_error: string | null;
  trail_json: string | null;
  reports_json: string | null;
  terrain_json: string | null;
};

const toOfflineMap = (row: OfflineMapRow): OfflineMap => ({
  id: row.id,
  userId: row.user_id,
  trailId: row.trail_id,
  name: row.name,
  sizeMb: row.size_mb,
  status: row.status,
  downloadedAt: row.downloaded_at,
  updatedAt: row.updated_at,
  downloadedTiles: row.downloaded_tiles ?? 0,
  totalTiles: row.total_tiles ?? 0,
  verifiedAt: row.verified_at,
  lastError: row.last_error,
  trail: parseJson<Trail | null>(row.trail_json, null),
  reports: sanitizeReports(parseJson<TrailReport[]>(row.reports_json, [])),
  terrain: parseJson<OfflineTerrainGrid | null>(row.terrain_json, null),
});

const getCurrentUserId = async () => {
  const session = await getAuthSession().catch(() => null);
  return session?.user.id ?? null;
};

export const getOfflineMaps = async (): Promise<OfflineMap[]> => {
  await initOfflineMapsTable();
  const userId = await getCurrentUserId();

  const rows = await db.getAllAsync<OfflineMapRow>(
    `SELECT ${offlineMapColumns}
     FROM offline_maps
     WHERE user_id IS ?
     ORDER BY updated_at DESC`,
    [userId]
  );

  return rows.map(toOfflineMap);
};

export const getOfflineMapByTrailId = async (
  trailId: number
): Promise<OfflineMap | null> => {
  await initOfflineMapsTable();
  const userId = await getCurrentUserId();

  const row = await db.getFirstAsync<OfflineMapRow>(
    `SELECT ${offlineMapColumns}
     FROM offline_maps
     WHERE user_id IS ? AND trail_id = ?
     ORDER BY updated_at DESC
     LIMIT 1`,
    [userId, trailId]
  );

  if (!row) return null;

  return toOfflineMap(row);
};

export const getVerifiedOfflineMapByTrailId = async (
  trailId: number
): Promise<OfflineMap | null> => {
  const offlineMap = await getOfflineMapByTrailId(trailId);

  if (!offlineMap?.trail || offlineMap.status !== "disponible") {
    return null;
  }

  const coverage = await getOfflineTileCoverageForTrail(offlineMap.trail);

  if (!coverage.isComplete) {
    return null;
  }

  const verifiedAt = Date.now();

  await updateOfflineMapTileVerification(
    offlineMap.id,
    coverage.availableTiles,
    coverage.totalTiles,
    verifiedAt
  );

  return {
    ...offlineMap,
    downloadedTiles: coverage.availableTiles,
    totalTiles: coverage.totalTiles,
    verifiedAt,
    lastError: null,
  };
};

export const getOfflineMapsSummary = async (): Promise<OfflineMapsSummary> => {
  await initOfflineMapsTable();
  const userId = await getCurrentUserId();

  const row = await db.getFirstAsync<{
    count: number;
    total_size_mb: number | null;
  }>(
    `SELECT COUNT(*) AS count, COALESCE(SUM(size_mb), 0) AS total_size_mb
     FROM offline_maps
     WHERE user_id IS ? AND status = 'disponible'`,
    [userId]
  );

  return {
    count: row?.count ?? 0,
    totalSizeMb: row?.total_size_mb ?? 0,
  };
};

export const saveOfflineTrailMap = async (
  trail: Trail,
  reports: TrailReport[] = [],
  onTileProgress?: (downloaded: number, total: number) => void,
  options: OfflineTileDownloadOptions = {}
) => {
  reports = sanitizeReports(reports);
  await initOfflineMapsTable();
  const userId = await getCurrentUserId();

  const now = Date.now();
  const geometry = await getOfflineMapByTrailId(trail.id);
  if (!geometry) {
    await db.runAsync(`INSERT INTO offline_maps (user_id, name, size_mb, status, downloaded_at, updated_at, trail_id, trail_json, reports_json)
      VALUES (?, ?, ?, 'incompleto', ?, ?, ?, ?, ?)`,
      [userId, trail.name, estimateTrailMapSizeMb(trail, reports), now, now, trail.id, JSON.stringify(trail), JSON.stringify(reports)]);
  } else {
    await db.runAsync(
      `UPDATE offline_maps SET trail_json = ?, reports_json = ?, status = 'incompleto',
       verified_at = NULL, updated_at = ? WHERE id = ? AND user_id IS ?`,
      [JSON.stringify(trail), JSON.stringify(reports), now, geometry.id, userId]
    );
  }
  const tileCache = await downloadOfflineTilesForTrail(trail, onTileProgress, options);
  const coverage = await getOfflineTileCoverageForTrail(trail);

  if (!coverage.isComplete) {
    throw new Error(
      `offline-map-incomplete:${coverage.availableTiles}/${coverage.totalTiles}`
    );
  }

  // New downloads never request 3D data. Preserve compatible legacy data only.
  const route = parseRouteCoordinates(trail.route_coordinates);
  const keptTerrain = geometry?.terrain && isTerrainGridFor(geometry.terrain, trail, route)
    ? geometry.terrain
    : null;
  const terrain = keptTerrain;
  const terrainJson = terrain ? JSON.stringify(terrain) : null;
  const sizeMb = estimateTrailMapSizeMb(trail, reports) + tileCache.sizeMb;
  const existing = await db.getFirstAsync<{ id: number }>(
    `SELECT id FROM offline_maps WHERE user_id IS ? AND trail_id = ? LIMIT 1`,
    [userId, trail.id]
  );

  if (existing) {
    await db.runAsync(
      `UPDATE offline_maps
       SET name = ?,
           size_mb = ?,
           status = ?,
           updated_at = ?,
           downloaded_tiles = ?,
           total_tiles = ?,
           verified_at = ?,
           last_error = ?,
           trail_json = ?,
           reports_json = ?,
           terrain_json = ?
       WHERE id = ? AND user_id IS ?`,
      [
        trail.name,
        sizeMb,
        "disponible",
        now,
        coverage.availableTiles,
        coverage.totalTiles,
        now,
        null,
        JSON.stringify(trail),
        JSON.stringify(reports),
        terrainJson,
        existing.id,
        userId,
      ]
    );

    return getOfflineMapByTrailId(trail.id);
  }

  await db.runAsync(
    `INSERT INTO offline_maps (
       user_id,
       name,
       size_mb,
       status,
       downloaded_at,
       updated_at,
       trail_id,
       trail_json,
       reports_json,
       downloaded_tiles,
       total_tiles,
       verified_at,
       last_error,
       terrain_json
     )
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      userId,
      trail.name,
      sizeMb,
      "disponible",
      now,
      now,
      trail.id,
      JSON.stringify(trail),
      JSON.stringify(reports),
      coverage.availableTiles,
      coverage.totalTiles,
      now,
      null,
      terrainJson,
    ]
  );

  return getOfflineMapByTrailId(trail.id);
};

const toOfflineTerrainGrid = (
  trail: Trail,
  route: readonly Coordinate[],
  { grid, source }: TerrainGridData
): OfflineTerrainGrid | null =>
  trail.elevation
    ? {
        version: 1,
        geometry_hash: trail.elevation.geometry_hash,
        route_key: buildTerrainElevationCacheKey(trail.id, route),
        grid,
        source,
      }
    : null;

const isTerrainGridFor = (
  terrain: OfflineTerrainGrid,
  trail: Trail,
  route: readonly Coordinate[]
) =>
  terrain.version === 1 &&
  terrain.geometry_hash === trail.elevation?.geometry_hash &&
  terrain.route_key === buildTerrainElevationCacheKey(trail.id, route);

// Lectura local para la vista 3D: nunca consulta al proveedor. Devuelve la
// grilla solo si corresponde al perfil descargado y al trazado indicado.
export const getOfflineTerrainGrid = async (
  trailId: number,
  route: readonly Coordinate[]
): Promise<OfflineTerrainGrid | null> => {
  const local = await getOfflineMapByTrailId(trailId);
  return local?.trail && local.terrain && isTerrainGridFor(local.terrain, local.trail, route)
    ? local.terrain
    : null;
};

// Mapas descargados sin grilla: con conexion se guarda la grilla real ya
// consultada por la vista 3D, solo si coincide con el trazado descargado.
export const backfillOfflineTerrainGrid = async (
  trailId: number,
  route: readonly Coordinate[],
  data: TerrainGridData
) => {
  const local = await getOfflineMapByTrailId(trailId);
  if (!local?.trail) return;
  const terrain = toOfflineTerrainGrid(local.trail, route, data);
  const downloadedRoute = parseRouteCoordinates(local.trail.route_coordinates);
  if (!terrain || !isTerrainGridFor(terrain, local.trail, downloadedRoute)) return;
  const userId = await getCurrentUserId();
  await db.runAsync(
    `UPDATE offline_maps SET terrain_json = ?, updated_at = ?
     WHERE id = ? AND user_id IS ? AND trail_json = ?`,
    [JSON.stringify(terrain), Date.now(), local.id, userId, JSON.stringify(local.trail)]
  );
};

export const refreshOfflineTrailElevation = async (trail: Trail) => {
  const local = await getOfflineMapByTrailId(trail.id);
  if (!local?.trail || (!trail.elevation && trail.national_park === undefined)) return;
  // Preserve the downloaded geometry: a changed trace requires a map update.
  if (JSON.stringify(JSON.parse(local.trail.route_coordinates || "null")) !==
      JSON.stringify(JSON.parse(trail.route_coordinates || "null"))) return;
  const updated = {
    ...local.trail,
    ...(trail.elevation ? { elevation: trail.elevation } : {}),
    ...(trail.national_park !== undefined ? { national_park: trail.national_park, national_park_slug: trail.national_park_slug } : {}),
  };
  const userId = await getCurrentUserId();
  await db.runAsync(
    `UPDATE offline_maps SET trail_json = ?, updated_at = ?
     WHERE id = ? AND user_id IS ? AND trail_json = ?`,
    [JSON.stringify(updated), Date.now(), local.id, userId, JSON.stringify(local.trail)]
  );
  return updated;
};

export const refreshOfflineTrailReports = async (
  trailId: number,
  reports: TrailReport[]
) => {
  await initOfflineMapsTable();
  const userId = await getCurrentUserId();

  await db.runAsync(
    `UPDATE offline_maps
     SET reports_json = ?,
         updated_at = ?
     WHERE user_id IS ? AND trail_id = ?`,
    [JSON.stringify(sanitizeReports(reports)), Date.now(), userId, trailId]
  );
};

export const deleteOfflineMap = async (mapId: number): Promise<boolean> => {
  await initOfflineMapsTable();
  const userId = await getCurrentUserId();

  const row = await db.getFirstAsync<OfflineMapRow>(
    `SELECT ${offlineMapColumns}
     FROM offline_maps
     WHERE id = ? AND user_id IS ?
     LIMIT 1`,
    [mapId, userId]
  );

  if (!row) return false;

  const offlineMap = toOfflineMap(row);

  if (offlineMap.trail) {
    await deleteOfflineTilesForTrail(offlineMap.trail).catch(() => undefined);
  }

  await db.runAsync(`DELETE FROM offline_maps WHERE id = ? AND user_id IS ?`, [
    mapId,
    userId,
  ]);

  return true;
};

const updateOfflineMapTileVerification = async (
  mapId: number,
  downloadedTiles: number,
  totalTiles: number,
  verifiedAt: number
) => {
  await initOfflineMapsTable();
  const userId = await getCurrentUserId();

  await db.runAsync(
    `UPDATE offline_maps
     SET downloaded_tiles = ?,
         total_tiles = ?,
         verified_at = ?,
         last_error = NULL
     WHERE id = ? AND user_id IS ?`,
    [downloadedTiles, totalTiles, verifiedAt, mapId, userId]
  );
};

const estimateTrailMapSizeMb = (trail: Trail, reports: TrailReport[]) => {
  const bytes = JSON.stringify({ trail, reports }).length;
  const metadataMb = bytes / 1024 / 1024;

  return Math.max(1, Math.ceil(metadataMb * 10) / 10);
};
