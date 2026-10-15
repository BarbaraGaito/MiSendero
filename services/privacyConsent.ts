import { getAuthSession } from "./authSession";
import { db } from "../database/connection";
import { wearableTablesSql } from "../database/wearableSchema";


export interface PrivacyPreferences {
  sensitiveDataConsent: boolean;
  analyticsTrainingConsent: boolean;
  updatedAt: number | null;
}

const initPrivacyTable = async () => {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS user_privacy_preferences (
      id INTEGER PRIMARY KEY,
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
  }>("SELECT sensitive_data_consent, analytics_training_consent, updated_at FROM user_privacy_preferences WHERE id = ?", [(await getAuthSession())?.user.id ?? null]);

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
    `INSERT OR REPLACE INTO user_privacy_preferences (
       id,
       sensitive_data_consent,
       analytics_training_consent,
       updated_at
     )
     VALUES (?, ?, ?, ?)`,
    [
      (await getAuthSession())?.user.id ?? -1,
      preferences.sensitiveDataConsent ? 1 : 0,
      preferences.analyticsTrainingConsent ? 1 : 0,
      Date.now(),
    ]
  );

  if (!preferences.sensitiveDataConsent) {
    await clearSensitiveLocalData();
  }
};

export const clearSensitiveLocalData = async () => {
  const userId = (await getAuthSession())?.user.id;
  if (!userId) return;
  await db.execAsync(wearableTablesSql);
  await db.runAsync("DELETE FROM wearable_metric_samples WHERE user_id = ?", [userId]);
  await db.runAsync("DELETE FROM wearable_connections WHERE user_id = ?", [userId]);
};
