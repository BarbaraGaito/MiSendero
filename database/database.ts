import * as SQLite from "expo-sqlite";

export const db = SQLite.openDatabaseSync("trekking.db");

export const initDB = async () => {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      started_at INTEGER NOT NULL,
      ended_at INTEGER,
      duration INTEGER,
      distance REAL,
      avg_fatigue TEXT
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

    CREATE TABLE IF NOT EXISTS wearable_connections (
      user_id INTEGER PRIMARY KEY,
      provider TEXT NOT NULL,
      linked INTEGER NOT NULL DEFAULT 0,
      permissions_granted INTEGER NOT NULL DEFAULT 0,
      updated_at INTEGER NOT NULL,
      last_sync_at INTEGER
    );

    CREATE TABLE IF NOT EXISTS wearable_metric_samples (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      provider TEXT NOT NULL,
      heart_rate_bpm INTEGER,
      steps INTEGER,
      active_energy_kcal REAL,
      speed_kmh REAL,
      oxygen_saturation REAL,
      recorded_at INTEGER NOT NULL,
      created_at INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_wearable_samples_user_recorded
    ON wearable_metric_samples (user_id, recorded_at DESC);
  `);

  const columns = await db.getAllAsync<{ name: string }>(`PRAGMA table_info(sessions)`);
  const columnNames = columns.map((column) => column.name);

  if (!columnNames.includes("started_at")) {
    await db.execAsync(`ALTER TABLE sessions ADD COLUMN started_at INTEGER NOT NULL DEFAULT 0;`);
  }

  if (!columnNames.includes("ended_at")) {
    await db.execAsync(`ALTER TABLE sessions ADD COLUMN ended_at INTEGER;`);
  }

  if (!columnNames.includes("avg_fatigue")) {
    await db.execAsync(`ALTER TABLE sessions ADD COLUMN avg_fatigue TEXT DEFAULT 'bajo';`);
  }
};
