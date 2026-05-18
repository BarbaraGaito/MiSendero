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
