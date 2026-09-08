import * as SQLite from "expo-sqlite";
import {
  heartRateLogsTableSql,
  wearableTablesSql,
} from "../database/wearableSchema";

const db = SQLite.openDatabaseSync("trekking.db");

export interface PrivacyPreferences {
  sensitiveDataConsent: boolean;
  analyticsTrainingConsent: boolean;
  updatedAt: number | null;
}

const initPrivacyTable = async () => {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS privacy_preferences (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      sensitive_data_consent INTEGER NOT NULL DEFAULT 0,
      analytics_training_consent INTEGER NOT NULL DEFAULT 0,
      updated_at INTEGER
    );
  `);
};

export const getPrivacyPreferences = async (): Promise<PrivacyPreferences> => {
  await initPrivacyTable();

  const row = await db.getFirstAsync<{
    sensitive_data_consent: number;
    analytics_training_consent: number;
    updated_at: number | null;
  }>("SELECT sensitive_data_consent, analytics_training_consent, updated_at FROM privacy_preferences WHERE id = 1");

  return {
    sensitiveDataConsent: row?.sensitive_data_consent === 1,
    analyticsTrainingConsent: row?.analytics_training_consent === 1,
    updatedAt: row?.updated_at ?? null,
  };
};

export const savePrivacyPreferences = async (
  preferences: Omit<PrivacyPreferences, "updatedAt">
) => {
  await initPrivacyTable();

  await db.runAsync(
    `INSERT OR REPLACE INTO privacy_preferences (
       id,
       sensitive_data_consent,
       analytics_training_consent,
       updated_at
     )
     VALUES (1, ?, ?, ?)`,
    [
      preferences.sensitiveDataConsent ? 1 : 0,
      preferences.analyticsTrainingConsent ? 1 : 0,
      Date.now(),
    ]
  );

  if (!preferences.sensitiveDataConsent) {
    await clearSensitiveLocalData();
  }
};

export const hasSensitiveDataConsent = async () => {
  const preferences = await getPrivacyPreferences();
  return preferences.sensitiveDataConsent;
};

export const clearSensitiveLocalData = async () => {
  await db.execAsync(`
    ${heartRateLogsTableSql}
    ${wearableTablesSql}

    DELETE FROM wearable_metric_samples;
    DELETE FROM wearable_connections;
    DELETE FROM heart_rate_logs;
  `);
};
