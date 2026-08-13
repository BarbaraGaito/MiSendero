import * as SQLite from "expo-sqlite";

const db = SQLite.openDatabaseSync("trekking.db");

export type DistanceUnit = "km" | "mi";

export interface AppPreferences {
  notificationsEnabled: boolean;
  distanceUnit: DistanceUnit;
  batterySaverEnabled: boolean;
  externalSensorLinked: boolean;
  updatedAt: number | null;
}

const defaultPreferences: AppPreferences = {
  notificationsEnabled: true,
  distanceUnit: "km",
  batterySaverEnabled: true,
  externalSensorLinked: false,
  updatedAt: null,
};

const initPreferencesTable = async () => {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS app_preferences (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      notifications_enabled INTEGER NOT NULL DEFAULT 1,
      distance_unit TEXT NOT NULL DEFAULT 'km',
      battery_saver_enabled INTEGER NOT NULL DEFAULT 1,
      external_sensor_linked INTEGER NOT NULL DEFAULT 0,
      updated_at INTEGER
    );
  `);
};

export const getAppPreferences = async (): Promise<AppPreferences> => {
  await initPreferencesTable();

  const row = await db.getFirstAsync<{
    notifications_enabled: number;
    distance_unit: string;
    battery_saver_enabled: number;
    external_sensor_linked: number;
    updated_at: number | null;
  }>(
    `SELECT
       notifications_enabled,
       distance_unit,
       battery_saver_enabled,
       external_sensor_linked,
       updated_at
     FROM app_preferences
     WHERE id = 1`
  );

  if (!row) return defaultPreferences;

  return {
    notificationsEnabled: row.notifications_enabled === 1,
    distanceUnit: row.distance_unit === "mi" ? "mi" : "km",
    batterySaverEnabled: row.battery_saver_enabled === 1,
    externalSensorLinked: row.external_sensor_linked === 1,
    updatedAt: row.updated_at ?? null,
  };
};

export const saveAppPreferences = async (
  preferences: Omit<AppPreferences, "updatedAt">
) => {
  await initPreferencesTable();

  await db.runAsync(
    `INSERT OR REPLACE INTO app_preferences (
       id,
       notifications_enabled,
       distance_unit,
       battery_saver_enabled,
       external_sensor_linked,
       updated_at
     )
     VALUES (1, ?, ?, ?, ?, ?)`,
    [
      preferences.notificationsEnabled ? 1 : 0,
      preferences.distanceUnit,
      preferences.batterySaverEnabled ? 1 : 0,
      preferences.externalSensorLinked ? 1 : 0,
      Date.now(),
    ]
  );
};
