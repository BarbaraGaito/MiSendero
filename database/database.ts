import * as SQLite from "expo-sqlite";

export const db = SQLite.openDatabaseSync("trekking.db");

let initPromise: Promise<void> | null = null;

const isDuplicateColumnError = (error: unknown) =>
  error instanceof Error && error.message.toLowerCase().includes("duplicate column");

const addColumnIfMissing = async (
  tableName: string,
  columnName: string,
  columnDefinition: string
) => {
  const columns = await db.getAllAsync<{ name: string }>(`PRAGMA table_info(${tableName})`);
  const columnNames = columns.map((column) => column.name);

  if (columnNames.includes(columnName)) return;

  try {
    await db.execAsync(`ALTER TABLE ${tableName} ADD COLUMN ${columnName} ${columnDefinition};`);
  } catch (error) {
    if (!isDuplicateColumnError(error)) {
      throw error;
    }
  }
};

const runInitDB = async () => {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      started_at INTEGER NOT NULL,
      ended_at INTEGER,
      duration INTEGER,
      distance REAL,
      avg_fatigue TEXT,
      trail_id INTEGER,
      rating INTEGER,
      review_text TEXT,
      reviewed_at INTEGER
    );

    CREATE TABLE IF NOT EXISTS heart_rate_logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      hr INTEGER,
      timestamp INTEGER,
      session_id INTEGER
    );

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

  await addColumnIfMissing("sessions", "started_at", "INTEGER NOT NULL DEFAULT 0");
  await addColumnIfMissing("sessions", "ended_at", "INTEGER");
  await addColumnIfMissing("sessions", "avg_fatigue", "TEXT DEFAULT 'bajo'");
  await addColumnIfMissing("sessions", "trail_id", "INTEGER");
  await addColumnIfMissing("sessions", "rating", "INTEGER");
  await addColumnIfMissing("sessions", "review_text", "TEXT");
  await addColumnIfMissing("sessions", "reviewed_at", "INTEGER");
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
