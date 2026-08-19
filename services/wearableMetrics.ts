import * as SQLite from "expo-sqlite";
import { predictFatigueLevel, predictPhysioRisk } from "../ai/inferenceEngine";
import {
  HealthPredictionLevel,
  WearableConnection,
  WearableMetricSample,
  WearableProvider,
  WearableRuntimeStatus,
} from "../types";
import { getAuthSession } from "./authSession";
import { getNativeWearableBridge } from "./nativeWearableBridge";
import { getPrivacyPreferences } from "./privacyConsent";

const db = SQLite.openDatabaseSync("trekking.db");

const defaultConnection: WearableConnection = {
  provider: "development_simulator",
  linked: false,
  permissionsGranted: false,
  updatedAt: null,
  lastSyncAt: null,
};

const providerNames: Record<WearableProvider, string> = {
  apple_healthkit: "Apple Watch / Salud",
  android_health_connect: "Android / Health Connect",
  wear_os_health_services: "Wear OS / Health Services",
  development_simulator: "Simulador de desarrollo",
};

const androidNativeProviders: WearableProvider[] = [
  "android_health_connect",
  "wear_os_health_services",
];

const initWearableTables = async () => {
  await db.execAsync(`
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
};

const getCurrentUserId = async () => {
  const session = await getAuthSession();
  return session?.user.id ?? null;
};

const toConnection = (row: {
  provider: string;
  linked: number;
  permissions_granted: number;
  updated_at: number | null;
  last_sync_at: number | null;
}): WearableConnection => ({
  provider: parseProvider(row.provider),
  linked: row.linked === 1,
  permissionsGranted: row.permissions_granted === 1,
  updatedAt: row.updated_at ?? null,
  lastSyncAt: row.last_sync_at ?? null,
});

const toMetricSample = (row: {
  id: number;
  user_id: number;
  provider: string;
  heart_rate_bpm: number | null;
  steps: number | null;
  active_energy_kcal: number | null;
  speed_kmh: number | null;
  oxygen_saturation: number | null;
  recorded_at: number;
  created_at: number;
}): WearableMetricSample => ({
  id: row.id,
  user_id: row.user_id,
  provider: parseProvider(row.provider),
  heartRateBpm: row.heart_rate_bpm,
  steps: row.steps,
  activeEnergyKcal: row.active_energy_kcal,
  speedKmh: row.speed_kmh,
  oxygenSaturation: row.oxygen_saturation,
  recordedAt: row.recorded_at,
  createdAt: row.created_at,
});

const parseProvider = (value: string): WearableProvider => {
  if (
    value === "apple_healthkit" ||
    value === "android_health_connect" ||
    value === "wear_os_health_services" ||
    value === "development_simulator"
  ) {
    return value;
  }

  return "development_simulator";
};

export const getWearableProviderName = (provider: WearableProvider) =>
  providerNames[provider];

export const getWearableConnection = async (): Promise<WearableConnection> => {
  await initWearableTables();

  const userId = await getCurrentUserId();
  if (!userId) return defaultConnection;

  const row = await db.getFirstAsync<{
    provider: string;
    linked: number;
    permissions_granted: number;
    updated_at: number | null;
    last_sync_at: number | null;
  }>(
    `SELECT provider, linked, permissions_granted, updated_at, last_sync_at
     FROM wearable_connections
     WHERE user_id = ?`,
    [userId]
  );

  return row ? toConnection(row) : defaultConnection;
};

export const saveWearableConnection = async (
  provider: WearableProvider,
  linked: boolean,
  permissionsGranted: boolean
) => {
  await initWearableTables();

  const userId = await getCurrentUserId();
  if (!userId) {
    throw new Error("Sesion requerida para vincular metricas de salud.");
  }

  await db.runAsync(
    `INSERT OR REPLACE INTO wearable_connections (
       user_id,
       provider,
       linked,
       permissions_granted,
       updated_at,
       last_sync_at
     )
     VALUES (?, ?, ?, ?, ?, COALESCE((SELECT last_sync_at FROM wearable_connections WHERE user_id = ?), NULL))`,
    [userId, provider, linked ? 1 : 0, permissionsGranted ? 1 : 0, Date.now(), userId]
  );
};

export const unlinkWearableConnection = async () => {
  await initWearableTables();

  const userId = await getCurrentUserId();
  if (!userId) return;

  await db.runAsync(
    `UPDATE wearable_connections
     SET linked = 0,
         permissions_granted = 0,
         updated_at = ?
     WHERE user_id = ?`,
    [Date.now(), userId]
  );
};

export const saveWearableMetricSample = async (
  sample: Omit<WearableMetricSample, "id" | "user_id" | "createdAt">
) => {
  await initWearableTables();

  const userId = await getCurrentUserId();
  if (!userId) {
    throw new Error("Sesion requerida para guardar metricas del reloj.");
  }

  const createdAt = Date.now();

  await db.runAsync(
    `INSERT INTO wearable_metric_samples (
       user_id,
       provider,
       heart_rate_bpm,
       steps,
       active_energy_kcal,
       speed_kmh,
       oxygen_saturation,
       recorded_at,
       created_at
     )
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      userId,
      sample.provider,
      sample.heartRateBpm,
      sample.steps,
      sample.activeEnergyKcal,
      sample.speedKmh,
      sample.oxygenSaturation,
      sample.recordedAt,
      createdAt,
    ]
  );

  await db.runAsync(
    `UPDATE wearable_connections
     SET last_sync_at = ?,
         updated_at = ?
     WHERE user_id = ?`,
    [sample.recordedAt, createdAt, userId]
  );
};

export const getLatestWearableMetricSample = async () => {
  await initWearableTables();

  const userId = await getCurrentUserId();
  if (!userId) return null;

  const row = await db.getFirstAsync<{
    id: number;
    user_id: number;
    provider: string;
    heart_rate_bpm: number | null;
    steps: number | null;
    active_energy_kcal: number | null;
    speed_kmh: number | null;
    oxygen_saturation: number | null;
    recorded_at: number;
    created_at: number;
  }>(
    `SELECT *
     FROM wearable_metric_samples
     WHERE user_id = ?
     ORDER BY recorded_at DESC
     LIMIT 1`,
    [userId]
  );

  return row ? toMetricSample(row) : null;
};

export const getRecentWearableMetricSamples = async (limit = 20) => {
  await initWearableTables();

  const userId = await getCurrentUserId();
  if (!userId) return [];

  const rows = await db.getAllAsync<{
    id: number;
    user_id: number;
    provider: string;
    heart_rate_bpm: number | null;
    steps: number | null;
    active_energy_kcal: number | null;
    speed_kmh: number | null;
    oxygen_saturation: number | null;
    recorded_at: number;
    created_at: number;
  }>(
    `SELECT *
     FROM wearable_metric_samples
     WHERE user_id = ?
     ORDER BY recorded_at DESC
     LIMIT ?`,
    [userId, limit]
  );

  return rows.map(toMetricSample);
};

export const createDevelopmentMetricSample = async () => {
  const connection = await getWearableConnection();
  const provider = connection.provider || "development_simulator";
  const now = Date.now();
  const heartRateBase =
    provider === "development_simulator" ? 94 : 88 + Math.round(Math.random() * 28);
  const heartRateBpm = heartRateBase + Math.round(Math.sin(now / 25_000) * 18);
  const speedKmh = Number((2.8 + Math.random() * 2.6).toFixed(1));
  const oxygenSaturation = Number((96 + Math.random() * 3).toFixed(1));

  await saveWearableMetricSample({
    provider,
    heartRateBpm,
    steps: 800 + Math.round(Math.random() * 4200),
    activeEnergyKcal: Number((120 + Math.random() * 360).toFixed(1)),
    speedKmh,
    oxygenSaturation,
    recordedAt: now,
  });
};

export const linkNativeWearable = async () => {
  return linkNativeWearableProvider();
};

export const linkNativeWearableProvider = async (
  preferredProvider?: WearableProvider
) => {
  const bridge = getNativeWearableBridge();
  const isAvailable = await bridge.isAvailable();

  if (!isAvailable) return false;

  const permissionsGranted = await bridge.requestPermissions();
  if (!permissionsGranted) return false;

  const provider =
    preferredProvider && androidNativeProviders.includes(preferredProvider)
      ? preferredProvider
      : bridge.provider;
  await saveWearableConnection(provider, true, true);
  return true;
};

export const syncNativeWearableSample = async () => {
  const bridge = getNativeWearableBridge();
  const isAvailable = await bridge.isAvailable();

  if (!isAvailable) return false;

  const connection = await getWearableConnection();
  if (!connection.linked) return false;

  const provider =
    androidNativeProviders.includes(connection.provider) &&
    bridge.provider === "android_health_connect"
      ? connection.provider
      : bridge.provider;
  const permissionsGranted =
    connection.provider === provider && connection.permissionsGranted
      ? true
      : await bridge.requestPermissions();
  if (!permissionsGranted) return false;

  const sample = await bridge.readLatestSample();

  await saveWearableConnection(provider, true, true);
  if (!sample) return false;

  await saveWearableMetricSample({
    ...sample,
    provider,
  });
  return true;
};

export const predictWearableHealth = (
  sample: WearableMetricSample | null,
  elapsedMinutes = 0
) => {
  if (!sample?.heartRateBpm) return null;

  const fatigue = predictFatigueLevel({
    hr: sample.heartRateBpm,
    speedKmh: sample.speedKmh ?? 0,
    elapsedMinutes,
  });
  const risk = predictPhysioRisk({
    hr: sample.heartRateBpm,
    speedKmh: sample.speedKmh ?? 0,
    elapsedMinutes,
    fatigue,
  });

  let level: HealthPredictionLevel = "normal";
  if (risk.label === "alto" || sample.heartRateBpm >= 165 || fatigue === "alto") {
    level = "high";
  } else if (risk.label === "medio" || sample.heartRateBpm >= 145 || fatigue === "medio") {
    level = "caution";
  }

  if (level === "high") {
    return {
      level,
      title: "Revisar intensidad",
      message:
        "Tu esfuerzo actual aparece elevado. Pausa, hidratate y evalua como te sentis antes de continuar.",
      fatigue,
    };
  }

  if (level === "caution") {
    return {
      level,
      title: "Mantener atencion",
      message:
        "Las metricas indican esfuerzo moderado. Baja el ritmo si notas cansancio, mareos o falta de aire.",
      fatigue,
    };
  }

  return {
    level,
    title: "Metricas estables",
    message:
      "No se observan senales de esfuerzo elevado con las metricas disponibles.",
    fatigue,
  };
};

export const getWearableRuntimeStatus = async (
  elapsedMinutes = 0
): Promise<WearableRuntimeStatus> => {
  const [connection, latestSample, privacy] = await Promise.all([
    getWearableConnection(),
    getLatestWearableMetricSample(),
    getPrivacyPreferences(),
  ]);

  const prediction =
    connection.linked && connection.permissionsGranted && privacy.sensitiveDataConsent
      ? predictWearableHealth(latestSample, elapsedMinutes)
      : null;

  return {
    connection,
    status: !privacy.sensitiveDataConsent
      ? "requires_consent"
      : connection.linked && connection.permissionsGranted
        ? latestSample
          ? "linked"
          : "waiting_for_native_data"
        : "not_linked",
    latestSample,
    prediction,
    displayName: getWearableProviderName(connection.provider),
  };
};
