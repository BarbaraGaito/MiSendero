import * as SQLite from "expo-sqlite";
import { Trail, TrailReport } from "../types";
import { downloadOfflineTilesForTrail } from "./mapTileCache";

const db = SQLite.openDatabaseSync("trekking.db");

export interface OfflineMap {
  id: number;
  name: string;
  sizeMb: number;
  status: string;
  downloadedAt: number;
  updatedAt: number;
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
      reports_json TEXT
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
};

const parseJson = <T>(value: string | null, fallback: T): T => {
  if (!value) return fallback;

  try {
    return JSON.parse(value) as T;
  } catch (error) {
    return fallback;
  }
};

export const getOfflineMaps = async (): Promise<OfflineMap[]> => {
  await initOfflineMapsTable();

  const rows = await db.getAllAsync<{
    id: number;
    name: string;
    size_mb: number;
    status: string;
    downloaded_at: number;
    updated_at: number;
    trail_json: string | null;
    reports_json: string | null;
  }>(
    `SELECT id, name, size_mb, status, downloaded_at, updated_at, trail_json, reports_json
     FROM offline_maps
     ORDER BY updated_at DESC`
  );

  return rows.map((row) => ({
    id: row.id,
    name: row.name,
    sizeMb: row.size_mb,
    status: row.status,
    downloadedAt: row.downloaded_at,
    updatedAt: row.updated_at,
    trail: parseJson<Trail | null>(row.trail_json, null),
    reports: parseJson<TrailReport[]>(row.reports_json, []),
  }));
};

export const getOfflineMapByTrailId = async (
  trailId: number
): Promise<OfflineMap | null> => {
  await initOfflineMapsTable();

  const row = await db.getFirstAsync<{
    id: number;
    name: string;
    size_mb: number;
    status: string;
    downloaded_at: number;
    updated_at: number;
    trail_json: string | null;
    reports_json: string | null;
  }>(
    `SELECT id, name, size_mb, status, downloaded_at, updated_at, trail_json, reports_json
     FROM offline_maps
     WHERE trail_id = ?
     ORDER BY updated_at DESC
     LIMIT 1`,
    [trailId]
  );

  if (!row) return null;

  return {
    id: row.id,
    name: row.name,
    sizeMb: row.size_mb,
    status: row.status,
    downloadedAt: row.downloaded_at,
    updatedAt: row.updated_at,
    trail: parseJson<Trail | null>(row.trail_json, null),
    reports: parseJson<TrailReport[]>(row.reports_json, []),
  };
};

export const getOfflineMapsSummary = async (): Promise<OfflineMapsSummary> => {
  await initOfflineMapsTable();

  const row = await db.getFirstAsync<{
    count: number;
    total_size_mb: number | null;
  }>(
    `SELECT COUNT(*) AS count, COALESCE(SUM(size_mb), 0) AS total_size_mb
     FROM offline_maps`
  );

  return {
    count: row?.count ?? 0,
    totalSizeMb: row?.total_size_mb ?? 0,
  };
};

export const saveOfflineTrailMap = async (
  trail: Trail,
  reports: TrailReport[] = [],
  onTileProgress?: (downloaded: number, total: number) => void
) => {
  await initOfflineMapsTable();

  const now = Date.now();
  const tileCache = await downloadOfflineTilesForTrail(trail, onTileProgress);
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
           trail_json = ?,
           reports_json = ?
       WHERE id = ?`,
      [
        trail.name,
        sizeMb,
        "disponible",
        now,
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
       reports_json
     )
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      trail.name,
      sizeMb,
      "disponible",
      now,
      now,
      trail.id,
      JSON.stringify(trail),
      JSON.stringify(reports),
    ]
  );

  return getOfflineMapByTrailId(trail.id);
};

const estimateTrailMapSizeMb = (trail: Trail, reports: TrailReport[]) => {
  const bytes = JSON.stringify({ trail, reports }).length;
  const metadataMb = bytes / 1024 / 1024;

  return Math.max(1, Math.ceil(metadataMb * 10) / 10);
};
