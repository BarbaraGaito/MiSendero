import * as SQLite from "expo-sqlite";
import { Trail, TrailReport } from "../types";
import {
  deleteOfflineTilesForTrail,
  downloadOfflineTilesForTrail,
  getOfflineTileCoverageForTrail,
  OfflineTileDownloadOptions,
} from "./mapTileCache";

const db = SQLite.openDatabaseSync("trekking.db");

export interface OfflineMap {
  id: number;
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
}

export interface OfflineMapsSummary {
  count: number;
  totalSizeMb: number;
}

const initOfflineMapsTable = async () => {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS offline_maps (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
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
      last_error TEXT
    );
  `);

  const columns = await db.getAllAsync<{ name: string }>(
    `PRAGMA table_info(offline_maps)`
  );
  const columnNames = columns.map((column) => column.name);

  if (!columnNames.includes("trail_id")) {
    await db.execAsync(`ALTER TABLE offline_maps ADD COLUMN trail_id INTEGER;`);
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
};

const parseJson = <T>(value: string | null, fallback: T): T => {
  if (!value) return fallback;

  try {
    return JSON.parse(value) as T;
  } catch (error) {
    return fallback;
  }
};

const offlineMapColumns = `
  id,
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
  reports_json
`;

type OfflineMapRow = {
  id: number;
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
};

const toOfflineMap = (row: OfflineMapRow): OfflineMap => ({
  id: row.id,
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
  reports: parseJson<TrailReport[]>(row.reports_json, []),
});

export const getOfflineMaps = async (): Promise<OfflineMap[]> => {
  await initOfflineMapsTable();

  const rows = await db.getAllAsync<OfflineMapRow>(
    `SELECT ${offlineMapColumns}
     FROM offline_maps
     ORDER BY updated_at DESC`
  );

  return rows.map(toOfflineMap);
};

export const getOfflineMapByTrailId = async (
  trailId: number
): Promise<OfflineMap | null> => {
  await initOfflineMapsTable();

  const row = await db.getFirstAsync<OfflineMapRow>(
    `SELECT ${offlineMapColumns}
     FROM offline_maps
     WHERE trail_id = ?
     ORDER BY updated_at DESC
     LIMIT 1`,
    [trailId]
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

  const row = await db.getFirstAsync<{
    count: number;
    total_size_mb: number | null;
  }>(
    `SELECT COUNT(*) AS count, COALESCE(SUM(size_mb), 0) AS total_size_mb
     FROM offline_maps
     WHERE status = 'disponible'`
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
  await initOfflineMapsTable();

  const now = Date.now();
  const tileCache = await downloadOfflineTilesForTrail(trail, onTileProgress, options);
  const coverage = await getOfflineTileCoverageForTrail(trail);

  if (!coverage.isComplete) {
    throw new Error(
      `offline-map-incomplete:${coverage.availableTiles}/${coverage.totalTiles}`
    );
  }

  const sizeMb = estimateTrailMapSizeMb(trail, reports) + tileCache.sizeMb;
  const existing = await db.getFirstAsync<{ id: number }>(
    `SELECT id FROM offline_maps WHERE trail_id = ? LIMIT 1`,
    [trail.id]
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
           reports_json = ?
       WHERE id = ?`,
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
        existing.id,
      ]
    );

    return getOfflineMapByTrailId(trail.id);
  }

  await db.runAsync(
    `INSERT INTO offline_maps (
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
       last_error
     )
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
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
    ]
  );

  return getOfflineMapByTrailId(trail.id);
};

export const refreshOfflineTrailReports = async (
  trailId: number,
  reports: TrailReport[]
) => {
  await initOfflineMapsTable();

  await db.runAsync(
    `UPDATE offline_maps
     SET reports_json = ?,
         updated_at = ?
     WHERE trail_id = ?`,
    [JSON.stringify(reports), Date.now(), trailId]
  );
};

export const deleteOfflineMap = async (mapId: number): Promise<boolean> => {
  await initOfflineMapsTable();

  const row = await db.getFirstAsync<OfflineMapRow>(
    `SELECT ${offlineMapColumns}
     FROM offline_maps
     WHERE id = ?
     LIMIT 1`,
    [mapId]
  );

  if (!row) return false;

  const offlineMap = toOfflineMap(row);

  if (offlineMap.trail) {
    await deleteOfflineTilesForTrail(offlineMap.trail).catch(() => undefined);
  }

  await db.runAsync(`DELETE FROM offline_maps WHERE id = ?`, [mapId]);

  return true;
};

const updateOfflineMapTileVerification = async (
  mapId: number,
  downloadedTiles: number,
  totalTiles: number,
  verifiedAt: number
) => {
  await initOfflineMapsTable();

  await db.runAsync(
    `UPDATE offline_maps
     SET downloaded_tiles = ?,
         total_tiles = ?,
         verified_at = ?,
         last_error = NULL
     WHERE id = ?`,
    [downloadedTiles, totalTiles, verifiedAt, mapId]
  );
};

const estimateTrailMapSizeMb = (trail: Trail, reports: TrailReport[]) => {
  const bytes = JSON.stringify({ trail, reports }).length;
  const metadataMb = bytes / 1024 / 1024;

  return Math.max(1, Math.ceil(metadataMb * 10) / 10);
};
