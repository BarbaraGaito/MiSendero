import { db } from "../../database/connection";
import { getAuthSession } from "../authSession";

// Local-only storage. Fall events and the monitoring preference are never queued for the backend:
// nothing here goes through pending_operations and eraseLocalAccountData() removes both tables.
export type FallUserResponse = "pending" | "ok" | "help" | "unanswered";
export type FallAction = "none" | "dismissed" | "sos_opened";

export interface FallEventInput {
  id: string;
  detectedAt: number;
  trailId: number | null;
  startedAt: number | null;
  modelId: string;
  modelVersion: string;
  score: number;
  peakG: number;
}

export interface FallEventRecord extends FallEventInput {
  userResponse: FallUserResponse;
  respondedAt: number | null;
  action: FallAction;
  classification: "possible_fall";
  latitude: number | null;
  longitude: number | null;
  locationRecordedAt: number | null;
}

interface Row {
  id: string; detected_at: number; trail_id: number | null; started_at: number | null; model_id: string;
  model_version: string; score: number; peak_g: number; user_response: FallUserResponse; responded_at: number | null;
  action: FallAction; classification: "possible_fall"; latitude: number | null; longitude: number | null;
  location_recorded_at: number | null;
}

export const FALL_EVENT_RETENTION_DAYS = 90;

export const ensureFallTables = () => db.execAsync(`
  CREATE TABLE IF NOT EXISTS fall_detection_events (
    id TEXT PRIMARY KEY,
    user_id INTEGER,
    detected_at INTEGER NOT NULL,
    trail_id INTEGER,
    started_at INTEGER,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    classification TEXT NOT NULL DEFAULT 'possible_fall',
    score REAL NOT NULL,
    peak_g REAL NOT NULL,
    user_response TEXT NOT NULL DEFAULT 'pending',
    responded_at INTEGER,
    action TEXT NOT NULL DEFAULT 'none',
    latitude REAL,
    longitude REAL,
    location_recorded_at INTEGER,
    created_at INTEGER NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_fall_detection_events_user ON fall_detection_events (user_id, detected_at);
  CREATE TABLE IF NOT EXISTS fall_detection_settings (
    user_id INTEGER PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 0,
    limitations_acknowledged_at INTEGER,
    updated_at INTEGER NOT NULL
  );
`);

const currentUser = async () => (await getAuthSession())?.user.id ?? -1;

const toRecord = (row: Row): FallEventRecord => ({
  id: row.id, detectedAt: row.detected_at, trailId: row.trail_id, startedAt: row.started_at, modelId: row.model_id,
  modelVersion: row.model_version, score: row.score, peakG: row.peak_g, userResponse: row.user_response,
  respondedAt: row.responded_at, action: row.action, classification: row.classification, latitude: row.latitude,
  longitude: row.longitude, locationRecordedAt: row.location_recorded_at,
});

export const saveFallEvent = async (event: FallEventInput) => {
  await ensureFallTables();
  await db.runAsync(
    `INSERT OR IGNORE INTO fall_detection_events
       (id, user_id, detected_at, trail_id, started_at, model_id, model_version, score, peak_g, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [event.id, await currentUser(), event.detectedAt, event.trailId, event.startedAt, event.modelId,
      event.modelVersion, event.score, event.peakG, Date.now()]);
};

export const getFallEvent = async (id: string): Promise<FallEventRecord | null> => {
  await ensureFallTables();
  const row = await db.getFirstAsync<Row>("SELECT * FROM fall_detection_events WHERE id = ? AND user_id = ?", [id, await currentUser()]);
  return row ? toRecord(row) : null;
};

export const listFallEvents = async (limit = 20): Promise<FallEventRecord[]> => {
  await ensureFallTables();
  const rows = await db.getAllAsync<Row>(
    "SELECT * FROM fall_detection_events WHERE user_id = ? ORDER BY detected_at DESC LIMIT ?", [await currentUser(), limit]);
  return rows.map(toRecord);
};

/** Only a still-pending event can be answered; the first answer wins. */
export const answerFallEvent = async (id: string, response: Exclude<FallUserResponse, "pending">, action: FallAction,
  location?: { latitude: number; longitude: number; recordedAt: number } | null) => {
  await ensureFallTables();
  const result = await db.runAsync(
    `UPDATE fall_detection_events SET user_response = ?, action = ?, responded_at = ?,
       latitude = ?, longitude = ?, location_recorded_at = ?
     WHERE id = ? AND user_id = ? AND user_response = 'pending'`,
    [response, action, Date.now(), location?.latitude ?? null, location?.longitude ?? null,
      location?.recordedAt ?? null, id, await currentUser()]);
  return result.changes > 0;
};

/** After a restart nothing can still be waiting on the screen: say so instead of leaving 'pending'. */
export const closeStalePendingFallEvents = async () => {
  await ensureFallTables();
  await db.runAsync(
    "UPDATE fall_detection_events SET user_response = 'unanswered', action = 'none' WHERE user_response = 'pending' AND user_id = ?",
    [await currentUser()]);
};

export interface FallSettings { enabled: boolean; limitationsAcknowledgedAt: number | null }

export const getFallSettings = async (): Promise<FallSettings> => {
  await ensureFallTables();
  const row = await db.getFirstAsync<{ enabled: number; limitations_acknowledged_at: number | null }>(
    "SELECT enabled, limitations_acknowledged_at FROM fall_detection_settings WHERE user_id = ?", [await currentUser()]);
  return { enabled: row?.enabled === 1, limitationsAcknowledgedAt: row?.limitations_acknowledged_at ?? null };
};

const settingsListeners = new Set<() => void>();
export const subscribeFallSettings = (listener: () => void) => {
  settingsListeners.add(listener);
  return () => { settingsListeners.delete(listener); };
};

export const saveFallSettings = async (settings: FallSettings) => {
  await ensureFallTables();
  await db.runAsync(
    `INSERT OR REPLACE INTO fall_detection_settings (user_id, enabled, limitations_acknowledged_at, updated_at) VALUES (?, ?, ?, ?)`,
    [await currentUser(), settings.enabled ? 1 : 0, settings.limitationsAcknowledgedAt, Date.now()]);
  settingsListeners.forEach((listener) => listener());
};

export const purgeOldFallEvents = async (now = Date.now()) => {
  await ensureFallTables();
  await db.runAsync("DELETE FROM fall_detection_events WHERE created_at <= ?", [now - FALL_EVENT_RETENTION_DAYS * 86400000]);
};
