import * as SQLite from "expo-sqlite";
import { predictFatigueLevel, predictPhysioRisk } from "../ai/inferenceEngine";
import {
  HealthPredictionLevel,
  WearableConnection,
  WearableMetricSample,
  WearableProvider,
  WearableRuntimeStatus,
  WearableSimulationScenario,
} from "../types";
import { getAuthSession } from "./authSession";
import {
  NativeWearableReadOptions,
  getNativeWearableBridge,
} from "./nativeWearableBridge";
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
  wear_os_health_services: "Wear OS / Health Connect",
  development_simulator: "Simulador de desarrollo",
};

const androidNativeProviders: WearableProvider[] = [
  "android_health_connect",
  "wear_os_health_services",
];

export type NativeWearableSyncStatus =
  | "saved"
  | "duplicate"
  | "no_data"
  | "unavailable"
  | "not_linked"
  | "permission_denied";

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

    CREATE INDEX IF NOT EXISTS idx_wearable_samples_user_provider_recorded
    ON wearable_metric_samples (user_id, provider, recorded_at DESC);
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
  const existing = await db.getFirstAsync<{ id: number }>(
    `SELECT id
     FROM wearable_metric_samples
     WHERE user_id = ? AND provider = ? AND recorded_at = ?
     LIMIT 1`,
    [userId, sample.provider, sample.recordedAt]
  );

  if (existing) {
    await db.runAsync(
      `UPDATE wearable_connections
       SET last_sync_at = MAX(COALESCE(last_sync_at, 0), ?),
           updated_at = ?
       WHERE user_id = ?`,
      [sample.recordedAt, createdAt, userId]
    );
    return false;
  }

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

  return true;
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

type SimulationRange = {
  hrMin: number;
  hrMax: number;
  speedMin: number;
  speedMax: number;
  spo2Min: number;
  spo2Max: number;
  stepsMin: number;
  stepsMax: number;
  kcalMin: number;
  kcalMax: number;
};

const simulationScenarioRanges: Record<WearableSimulationScenario, SimulationRange> = {
  normal: {
    hrMin: 78,
    hrMax: 98,
    speedMin: 4,
    speedMax: 5.5,
    spo2Min: 97,
    spo2Max: 99,
    stepsMin: 1800,
    stepsMax: 3200,
    kcalMin: 140,
    kcalMax: 260,
  },
  esfuerzo_moderado: {
    hrMin: 138,
    hrMax: 152,
    speedMin: 2.5,
    speedMax: 3.5,
    spo2Min: 94,
    spo2Max: 96,
    stepsMin: 2600,
    stepsMax: 4000,
    kcalMin: 260,
    kcalMax: 400,
  },
  fatiga_alta: {
    hrMin: 160,
    hrMax: 176,
    speedMin: 1.5,
    speedMax: 2.3,
    spo2Min: 90,
    spo2Max: 93,
    stepsMin: 3200,
    stepsMax: 4800,
    kcalMin: 380,
    kcalMax: 520,
  },
  riesgo_fisiologico: {
    hrMin: 178,
    hrMax: 197,
    speedMin: 0.8,
    speedMax: 1.6,
    spo2Min: 82,
    spo2Max: 89,
    stepsMin: 3600,
    stepsMax: 5200,
    kcalMin: 420,
    kcalMax: 600,
  },
};

const randomInRange = (min: number, max: number) => min + Math.random() * (max - min);

export const createDevelopmentMetricSample = async (
  scenario: WearableSimulationScenario = "normal"
) => {
  const connection = await getWearableConnection();
  const provider = connection.provider || "development_simulator";
  const now = Date.now();
  const range = simulationScenarioRanges[scenario] ?? simulationScenarioRanges.normal;

  const heartRateBpm = Math.round(randomInRange(range.hrMin, range.hrMax));
  const speedKmh = Number(randomInRange(range.speedMin, range.speedMax).toFixed(1));
  const oxygenSaturation = Number(randomInRange(range.spo2Min, range.spo2Max).toFixed(1));

  await saveWearableMetricSample({
    provider,
    heartRateBpm,
    steps: Math.round(randomInRange(range.stepsMin, range.stepsMax)),
    activeEnergyKcal: Number(randomInRange(range.kcalMin, range.kcalMax).toFixed(1)),
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

export const syncNativeWearableSampleWithStatus = async (
  options?: NativeWearableReadOptions
): Promise<NativeWearableSyncStatus> => {
  const bridge = getNativeWearableBridge();
  const isAvailable = await bridge.isAvailable();

  if (!isAvailable) return "unavailable";

  const connection = await getWearableConnection();
  if (!connection.linked) return "not_linked";

  const provider =
    androidNativeProviders.includes(connection.provider) &&
    bridge.provider === "android_health_connect"
      ? connection.provider
      : bridge.provider;
  const permissionsGranted =
    connection.provider === provider && connection.permissionsGranted
      ? true
      : await bridge.requestPermissions();
  if (!permissionsGranted) return "permission_denied";

  const sample = await bridge.readLatestSample(options);

  await saveWearableConnection(provider, true, true);
  if (!sample) return "no_data";

  const saved = await saveWearableMetricSample({
    ...sample,
    provider,
  });
  return saved ? "saved" : "duplicate";
};

export const syncNativeWearableSample = async (
  options?: NativeWearableReadOptions
) => {
  return (await syncNativeWearableSampleWithStatus(options)) === "saved";
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

  const criticalOxygen =
    sample.oxygenSaturation !== null && sample.oxygenSaturation < 90;
  const criticalHeartRate = sample.heartRateBpm >= 180;

  let level: HealthPredictionLevel = "normal";
  if (
    criticalOxygen ||
    criticalHeartRate ||
    risk.label === "alto" ||
    sample.heartRateBpm >= 165 ||
    fatigue === "alto"
  ) {
    level = "high";
  } else if (risk.label === "medio" || sample.heartRateBpm >= 145 || fatigue === "medio") {
    level = "caution";
  }

  if (level === "high") {
    return {
      level,
      title: criticalOxygen
        ? "Saturacion de oxigeno critica"
        : criticalHeartRate
          ? "Frecuencia cardiaca critica"
          : "Revisar intensidad",
      message: criticalOxygen
        ? `Tu oxigeno en sangre (${sample.oxygenSaturation}%) esta por debajo del umbral seguro. Deten la actividad, respira con calma y busca ayuda si no mejora.`
        : criticalHeartRate
          ? `Tu frecuencia cardiaca (${sample.heartRateBpm} bpm) es muy elevada. Deten la actividad de inmediato y evalua pedir ayuda.`
          : "Tu esfuerzo actual aparece elevado. Pausa, hidratate y evalua como te sentis antes de continuar.",
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
