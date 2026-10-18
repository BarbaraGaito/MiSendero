import { db, withWriteTransaction } from "./connection";
import { randomUUID } from "expo-crypto";
import type { SessionRow } from "../types";
import { persistActivityOutbox } from "./activityOutbox";
import { installRetentionPolicy } from "./dataRetention";
import { wearableStorageSql } from "./wearableSchema";

export { db };

let initPromise: Promise<void> | null = null;

const isDuplicateColumnError = (error: unknown) =>
  error instanceof Error && error.message.toLowerCase().includes("duplicate column");

const tableInfoQueries = {
  offline_maps: "PRAGMA table_info(offline_maps)",
  pending_operations: "PRAGMA table_info(pending_operations)",
  sessions: "PRAGMA table_info(sessions)",
  route_tracking_points: "PRAGMA table_info(route_tracking_points)",
} as const;

type KnownTableName = keyof typeof tableInfoQueries;

const addColumnIfMissing = async ({
  columnName,
  statement,
  tableName,
}: {
  columnName: string;
  statement: string;
  tableName: KnownTableName;
}) => {
  const columns = await db.getAllAsync<{ name: string }>(tableInfoQueries[tableName]);
  const columnNames = columns.map((column) => column.name);

  if (columnNames.includes(columnName)) return;

  try {
    await db.execAsync(statement);
  } catch (error) {
    if (!isDuplicateColumnError(error)) {
      throw error;
    }
  }
};

// Older versions persisted testing-simulator data as if it were measured. Remove
// every row that can be identified as simulated. Wearable samples a previous
// version stored under a real provider name cannot be told apart and remain.
export const purgeSimulatedData = async () => {
  // Only the removed tracking hook wrote heart_rate_logs, mixing simulator pulses
  // with real ones that cannot be told apart; nothing reads it anymore.
  await db.execAsync("DROP TABLE IF EXISTS heart_rate_logs");
  // No fatigue model was ever approved: stored levels came from a column default
  // or from that hook, so none of them is a real estimate.
  await db.runAsync("UPDATE sessions SET avg_fatigue = NULL WHERE avg_fatigue IS NOT NULL");
  await db.runAsync("DELETE FROM wearable_metric_samples WHERE provider = 'development_simulator'");
  await db.runAsync("DELETE FROM wearable_connections WHERE provider = 'development_simulator'");

  const routeRuntime = await db.getFirstAsync<{ name: string }>(
    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'route_runtime'"
  );
  const isSimulatedSession = `(
    EXISTS (SELECT 1 FROM route_tracking_points p WHERE p.simulated = 1
      AND p.user_id IS sessions.user_id AND p.trail_id = sessions.trail_id AND p.started_at = sessions.started_at)
    ${routeRuntime ? `OR EXISTS (SELECT 1 FROM route_runtime r WHERE r.simulated = 1
      AND r.user_id IS sessions.user_id AND r.trail_id = sessions.trail_id AND r.started_at = sessions.started_at)` : ""}
  )`;

  // Activities already synced live on the backend and cannot be removed from here.
  await db.runAsync(
    `DELETE FROM pending_operations
     WHERE entity_type = 'activity' AND status != 'synced' AND dedupe_key IN (
       SELECT COALESCE(sessions.user_id, 'guest') || ':activity:' || COALESCE(sessions.client_session_id, 'local-session-' || sessions.id)
       FROM sessions WHERE ${isSimulatedSession}
     )`
  );
  await db.runAsync(`DELETE FROM sessions WHERE ${isSimulatedSession}`);
  await db.runAsync("DELETE FROM route_tracking_points WHERE simulated = 1");
  if (routeRuntime) {
    await db.runAsync("DELETE FROM route_runtime WHERE simulated = 1");
  }
};

const runInitDB = async () => {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      started_at INTEGER NOT NULL,
      ended_at INTEGER,
      duration INTEGER,
      distance REAL,
      avg_fatigue TEXT,
      trail_id INTEGER,
      completion_status TEXT NOT NULL DEFAULT 'completed',
      route_progress_meters REAL,
      route_total_meters REAL,
      ended_latitude REAL,
      ended_longitude REAL,
      rating INTEGER,
      review_text TEXT,
      reviewed_at INTEGER
    );

    CREATE TABLE IF NOT EXISTS route_tracking_points (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      trail_id INTEGER NOT NULL,
      started_at INTEGER NOT NULL,
      latitude REAL NOT NULL,
      longitude REAL NOT NULL,
      accuracy_meters REAL,
      speed_kmh REAL,
      distance_delta_meters REAL NOT NULL DEFAULT 0,
      recorded_at INTEGER NOT NULL,
      simulated INTEGER NOT NULL DEFAULT 0,
      created_at INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_route_tracking_points_route
    ON route_tracking_points (trail_id, started_at, recorded_at);

    CREATE TABLE IF NOT EXISTS app_preferences (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      notifications_enabled INTEGER NOT NULL DEFAULT 1,
      distance_unit TEXT NOT NULL DEFAULT 'km',
      battery_saver_enabled INTEGER NOT NULL DEFAULT 1,
      external_sensor_linked INTEGER NOT NULL DEFAULT 0,
      updated_at INTEGER
    );

    CREATE TABLE IF NOT EXISTS experience_profile (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      completed INTEGER NOT NULL DEFAULT 0,
      skipped INTEGER NOT NULL DEFAULT 0,
      experience_level TEXT,
      answers_json TEXT,
      completed_at INTEGER,
      skipped_at INTEGER,
      updated_at INTEGER
    );

    CREATE TABLE IF NOT EXISTS emergency_contact (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      name TEXT NOT NULL,
      phone TEXT NOT NULL,
      relationship TEXT NOT NULL,
      updated_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS emergency_contacts (
      user_id INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      phone TEXT NOT NULL,
      relationship TEXT NOT NULL,
      updated_at INTEGER NOT NULL
    );

    ${wearableStorageSql}

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
      last_error TEXT
    );

    CREATE TABLE IF NOT EXISTS favorite_trails (
      trail_id INTEGER PRIMARY KEY,
      created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS pending_operations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      entity_type TEXT NOT NULL,
      payload_json TEXT NOT NULL,
      dedupe_key TEXT,
      status TEXT NOT NULL DEFAULT 'pending',
      retry_count INTEGER NOT NULL DEFAULT 0,
      last_error TEXT,
      server_id INTEGER,
      created_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_pending_operations_status
    ON pending_operations (status, created_at);

  `);

  const columnMigrations: Array<readonly [KnownTableName, string, string]> = [
    ["route_tracking_points", "user_id", "ALTER TABLE route_tracking_points ADD COLUMN user_id INTEGER;"],
    ["sessions", "started_at", "ALTER TABLE sessions ADD COLUMN started_at INTEGER NOT NULL DEFAULT 0;"],
    ["sessions", "user_id", "ALTER TABLE sessions ADD COLUMN user_id INTEGER;"],
    ["sessions", "client_session_id", "ALTER TABLE sessions ADD COLUMN client_session_id TEXT;"],
    ["sessions", "ended_at", "ALTER TABLE sessions ADD COLUMN ended_at INTEGER;"],
    ["sessions", "avg_fatigue", "ALTER TABLE sessions ADD COLUMN avg_fatigue TEXT;"],
    ["sessions", "trail_id", "ALTER TABLE sessions ADD COLUMN trail_id INTEGER;"],
    [
      "sessions",
      "completion_status",
      "ALTER TABLE sessions ADD COLUMN completion_status TEXT NOT NULL DEFAULT 'completed';",
    ],
    ["sessions", "route_progress_meters", "ALTER TABLE sessions ADD COLUMN route_progress_meters REAL;"],
    ["sessions", "route_total_meters", "ALTER TABLE sessions ADD COLUMN route_total_meters REAL;"],
    ["sessions", "ended_latitude", "ALTER TABLE sessions ADD COLUMN ended_latitude REAL;"],
    ["sessions", "ended_longitude", "ALTER TABLE sessions ADD COLUMN ended_longitude REAL;"],
    ["sessions", "rating", "ALTER TABLE sessions ADD COLUMN rating INTEGER;"],
    ["sessions", "review_text", "ALTER TABLE sessions ADD COLUMN review_text TEXT;"],
    ["sessions", "reviewed_at", "ALTER TABLE sessions ADD COLUMN reviewed_at INTEGER;"],
    [
      "offline_maps",
      "downloaded_tiles",
      "ALTER TABLE offline_maps ADD COLUMN downloaded_tiles INTEGER NOT NULL DEFAULT 0;",
    ],
    ["offline_maps", "user_id", "ALTER TABLE offline_maps ADD COLUMN user_id INTEGER;"],
    [
      "offline_maps",
      "total_tiles",
      "ALTER TABLE offline_maps ADD COLUMN total_tiles INTEGER NOT NULL DEFAULT 0;",
    ],
    ["offline_maps", "verified_at", "ALTER TABLE offline_maps ADD COLUMN verified_at INTEGER;"],
    ["offline_maps", "last_error", "ALTER TABLE offline_maps ADD COLUMN last_error TEXT;"],
    ["pending_operations", "dedupe_key", "ALTER TABLE pending_operations ADD COLUMN dedupe_key TEXT;"],
    ["pending_operations", "user_id", "ALTER TABLE pending_operations ADD COLUMN user_id INTEGER;"],
    ["pending_operations", "next_attempt_at", "ALTER TABLE pending_operations ADD COLUMN next_attempt_at INTEGER NOT NULL DEFAULT 0;"],
  ];

  for (const [tableName, columnName, statement] of columnMigrations) {
    await addColumnIfMissing({ columnName, statement, tableName });
  }
  await db.execAsync(`
    CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_operations_dedupe_key
    ON pending_operations (dedupe_key)
    WHERE dedupe_key IS NOT NULL;
  `);
  await installRetentionPolicy();
  await purgeSimulatedData();
  await recoverActivityOutbox();
};

export const recoverActivityOutbox = async () => {
  await withWriteTransaction(async (tx) => {
    const rows = await tx.getAllAsync<SessionRow>("SELECT * FROM sessions WHERE client_session_id IS NULL");
    for (const row of rows) {
      const oldKey = `${row.user_id ?? "guest"}:activity:local-session-${row.id}`;
      const operation = await tx.getFirstAsync<{ id: number; status: string; retry_count: number; payload_json: string }>(
        "SELECT id, status, retry_count, payload_json FROM pending_operations WHERE dedupe_key = ?", [oldKey]);
      // An attempted operation may already exist remotely: preserve its old identity.
      const attempted = operation && (operation.retry_count > 0 || ["synced", "syncing", "failed"].includes(operation.status));
      const identity = attempted ? `local-session-${row.id}` : randomUUID();
      await tx.runAsync("UPDATE sessions SET client_session_id = ? WHERE id = ?", [identity, row.id]);
      if (operation && !attempted) {
        const payload = { ...JSON.parse(operation.payload_json), client_session_id: identity };
        await tx.runAsync("UPDATE pending_operations SET payload_json = ?, dedupe_key = ? WHERE id = ?",
          [JSON.stringify(payload), `${row.user_id}:activity:${identity}`, operation.id]);
      }
      await persistActivityOutbox(tx, { ...row, client_session_id: identity });
    }
    await tx.execAsync("CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_client_identity ON sessions (client_session_id) WHERE client_session_id IS NOT NULL");
  });
};

export const initDB = async () => {
  if (!initPromise) {
    initPromise = runInitDB().catch((error) => {
      initPromise = null;
      throw error;
    });
  }

  return initPromise;
};
