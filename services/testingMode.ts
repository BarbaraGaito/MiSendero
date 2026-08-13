import * as SQLite from "expo-sqlite";

const db = SQLite.openDatabaseSync("trekking.db");

export interface TestingLocationMode {
  enabled: boolean;
  updatedAt: number | null;
}

const initTestingModeTable = async () => {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS testing_location_mode (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      enabled INTEGER NOT NULL DEFAULT 0,
      updated_at INTEGER
    );
  `);
};

export const getTestingLocationMode = async (): Promise<TestingLocationMode> => {
  await initTestingModeTable();

  const row = await db.getFirstAsync<{
    enabled: number;
    updated_at: number | null;
  }>("SELECT enabled, updated_at FROM testing_location_mode WHERE id = 1");

  return {
    enabled: row?.enabled === 1,
    updatedAt: row?.updated_at ?? null,
  };
};

export const saveTestingLocationMode = async (enabled: boolean) => {
  await initTestingModeTable();

  await db.runAsync(
    `INSERT OR REPLACE INTO testing_location_mode (id, enabled, updated_at)
     VALUES (1, ?, ?)`,
    [enabled ? 1 : 0, Date.now()]
  );
};
