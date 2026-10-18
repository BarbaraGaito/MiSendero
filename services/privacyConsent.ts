import { AccountContext, captureAccountContext, assertAccountContext } from "./accountContext";
import { getAuthSession } from "./authSession";
import { db } from "../database/connection";
import { wearableTablesSql } from "../database/wearableSchema";
import { initDB } from "../database/database";
import * as Crypto from "expo-crypto";
export { default as privacyNotices } from "../backend/src/privacyNotices.json";
import notices from "../backend/src/privacyNotices.json";
import { isAccountDeletionPending } from "./accountLifecycle";


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
    CREATE TABLE IF NOT EXISTS privacy_decision_events (
      client_event_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
      purpose TEXT NOT NULL, notice_version TEXT NOT NULL, notice_text TEXT NOT NULL,
      granted INTEGER NOT NULL, decided_at TEXT NOT NULL
    );
  `);
};

export const getPrivacyPreferences = async (captured?: AccountContext): Promise<PrivacyPreferences> => {
  const context = captured ?? await captureAccountContext();
  assertAccountContext(context);
  await initPrivacyTable();
  const userId = context.userId;

  const row = await db.getFirstAsync<{
    sensitive_data_consent: number;
    analytics_training_consent: number;
    updated_at: number | null;
  }>("SELECT sensitive_data_consent, analytics_training_consent, updated_at FROM user_privacy_preferences WHERE id = ?", [userId]);
  const decisions = await db.getAllAsync<{ purpose: string }>("SELECT DISTINCT purpose FROM privacy_decision_events WHERE user_id = ? AND notice_version = ?", [userId, notices.version]);
  assertAccountContext(context);
  const known = new Set(decisions.map((decision) => decision.purpose));
  if (userId && row?.sensitive_data_consent === 1 && !known.has("sensitiveDataConsent")) {
    await clearSensitiveLocalData(userId);
    await db.runAsync("UPDATE user_privacy_preferences SET sensitive_data_consent = 0, analytics_training_consent = 0, updated_at = NULL WHERE id = ?", [userId]);
  }

  return {
    sensitiveDataConsent: known.has("sensitiveDataConsent") && row?.sensitive_data_consent === 1,
    analyticsTrainingConsent: known.has("analyticsTrainingConsent") && row?.analytics_training_consent === 1,
    updatedAt: known.size === 2 ? row?.updated_at ?? null : null,
  };
};

export const savePrivacyPreferences = async (
  preferences: Omit<PrivacyPreferences, "updatedAt">
) => {
  const context = await captureAccountContext();
  await initPrivacyTable();
  await initDB();
  const userId = context.userId;
  if (!userId || await isAccountDeletionPending(userId)) throw new Error("Iniciá sesión con una cuenta activa para decidir tus preferencias.");
  const previous = await getPrivacyPreferences(context);
  const now = Date.now();
  await db.withTransactionAsync(async () => {
    assertAccountContext(context);
    for (const purpose of ["sensitiveDataConsent", "analyticsTrainingConsent"] as const) {
      if (previous.updatedAt !== null && previous[purpose] === preferences[purpose]) continue;
      const event = { client_event_id: Crypto.randomUUID(), purpose, notice_version: notices.version,
        notice_text: notices[purpose], granted: preferences[purpose], decided_at: new Date(now).toISOString() };
      await db.runAsync(`INSERT INTO privacy_decision_events (client_event_id, user_id, purpose, notice_version, notice_text, granted, decided_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)`, [event.client_event_id, userId, purpose, event.notice_version, event.notice_text, event.granted ? 1 : 0, event.decided_at]);
      await db.runAsync(`INSERT INTO pending_operations (user_id, entity_type, payload_json, dedupe_key, status, created_at, updated_at)
        VALUES (?, 'privacy_decision', ?, ?, 'pending', ?, ?)`, [userId, JSON.stringify(event), `${userId}:privacy:${event.client_event_id}`, now, now]);
    }

  assertAccountContext(context);
  await db.runAsync(
    `INSERT OR REPLACE INTO user_privacy_preferences (
       id,
       sensitive_data_consent,
       analytics_training_consent,
       updated_at
     )
     VALUES (?, ?, ?, ?)`,
    [
      userId,
      preferences.sensitiveDataConsent ? 1 : 0,
      preferences.analyticsTrainingConsent ? 1 : 0,
      Date.now(),
    ]
  );

  if (!preferences.sensitiveDataConsent) {
    await clearSensitiveLocalData(userId);
  }
  });
};

export const clearSensitiveLocalData = async (ownerId?: number) => {
  const userId = ownerId ?? (await getAuthSession())?.user.id;
  if (!userId) return;
  await db.execAsync(wearableTablesSql);
  await db.runAsync("DELETE FROM wearable_metric_samples WHERE user_id = ?", [userId]);
  await db.runAsync("DELETE FROM wearable_connections WHERE user_id = ?", [userId]);
};
