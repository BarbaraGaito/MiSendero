import { AccountContext, AccountContextChanged, captureAccountContext, assertAccountContext } from "./accountContext";
import { db } from "../database/connection";
import { wearableStorageSql } from "../database/wearableSchema";
import { assessWearableReadings, wearableReadingThresholds } from "../ai/wearableReadings";
import {
  HealthPredictionLevel,
  WearableHealthPrediction,
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
import { isAccountDeletionPending } from "./accountLifecycle";


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
  development_simulator: "Simulador (pruebas)",
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
  await db.execAsync(wearableStorageSql);
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

export const getWearableConnection = async (captured?: AccountContext): Promise<WearableConnection> => {
  const context = captured ?? await captureAccountContext();
  assertAccountContext(context);
  await initWearableTables();

  const userId = context.userId;
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

  assertAccountContext(context);
  return row ? toConnection(row) : defaultConnection;
};

export const saveWearableConnection = async (
  provider: WearableProvider,
  linked: boolean,
  permissionsGranted: boolean,
  captured?: AccountContext
) => {
  const context = captured ?? await captureAccountContext();
  assertAccountContext(context);
  await initWearableTables();

  const userId = context.userId;
  if (!userId) {
    throw new Error("Sesion requerida para vincular metricas de salud.");
  }

  assertAccountContext(context);
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
  sample: Omit<WearableMetricSample, "id" | "user_id" | "createdAt">,
  captured?: AccountContext
) => {
  const context = captured ?? await captureAccountContext();
  assertAccountContext(context);
  if (sample.simulated || sample.provider === "development_simulator") {
    throw new Error("Las metricas simuladas no se guardan.");
  }

  await initWearableTables();

  const userId = context.userId;
  if (!userId) {
    throw new Error("Sesion requerida para guardar metricas del reloj.");
  }
  if (!(await getPrivacyPreferences(context)).sensitiveDataConsent || await isAccountDeletionPending(userId)) {
    throw new Error("Se requiere autorización vigente para guardar métricas fisiológicas.");
  }

  const createdAt = Date.now();
  const existing = await db.getFirstAsync<{ id: number }>(
    `SELECT id
     FROM wearable_metric_samples
     WHERE user_id = ? AND provider = ? AND recorded_at = ?
     LIMIT 1`,
    [userId, sample.provider, sample.recordedAt]
  );

  assertAccountContext(context);
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

  assertAccountContext(context);
  const inserted = await db.runAsync(
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
     SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?
     WHERE EXISTS (SELECT 1 FROM user_privacy_preferences WHERE id = ? AND sensitive_data_consent = 1)
       AND NOT EXISTS (SELECT 1 FROM account_deletion_state WHERE user_id = ?)`,
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
      userId,
      userId,
    ]
  );

  await db.runAsync(
    `UPDATE wearable_connections
     SET last_sync_at = ?,
         updated_at = ?
     WHERE user_id = ?`,
    [sample.recordedAt, createdAt, userId]
  );

  return inserted.changes > 0;
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

type ScenarioSimulationShape = SimulationRange & {
  hrDrift: number;
  speedDrift: number;
  spo2Drift: number;
};

const simulationScenarioRanges: Record<WearableSimulationScenario, ScenarioSimulationShape> = {
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
    hrDrift: 2,
    speedDrift: 0.2,
    spo2Drift: 0.2,
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
    hrDrift: 8,
    speedDrift: -0.4,
    spo2Drift: -0.8,
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
    hrDrift: 12,
    speedDrift: -0.8,
    spo2Drift: -1.8,
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
    hrDrift: 14,
    speedDrift: -0.6,
    spo2Drift: -3,
  },
};

const getSimulationRandomFraction = () => {
  const cryptoObject = globalThis.crypto;

  if (cryptoObject?.getRandomValues) {
    const values = new Uint32Array(1);
    cryptoObject.getRandomValues(values);
    return values[0] / 0xffffffff;
  }

  return Date.now().toString().split("").reduce((seed, digit) => {
    const nextSeed = (seed * 31 + Number(digit)) % 1000;
    return nextSeed;
  }, 0) / 1000;
};

const randomInRange = (min: number, max: number) =>
  min + getSimulationRandomFraction() * (max - min);

const getScenarioPoint = (
  range: ScenarioSimulationShape,
  progress: number,
  wobbleSeed: number
) => {
  const wobble = Math.sin(wobbleSeed * 1.73) * 0.5 + Math.cos(wobbleSeed * 0.91) * 0.5;
  const heartRateBpm = Math.round(
    randomInRange(range.hrMin, range.hrMax) + range.hrDrift * progress + wobble * 3
  );
  const speedKmh = Number(
    Math.max(
      0.3,
      randomInRange(range.speedMin, range.speedMax) + range.speedDrift * progress + wobble * 0.16
    ).toFixed(1)
  );
  const oxygenSaturation = Number(
    clampMetric(
      randomInRange(range.spo2Min, range.spo2Max) + range.spo2Drift * progress - Math.abs(wobble) * 0.35,
      78,
      100
    ).toFixed(1)
  );

  return { heartRateBpm, speedKmh, oxygenSaturation };
};

const clampMetric = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));

// Simulator readings exist only in memory, for testing alert rules. They are
// never written to SQLite, synced, or attributed to a real provider.
const MAX_SIMULATED_SAMPLES = 12;
let simulatedSamples: WearableMetricSample[] = [];

const keepSimulatedSamples = async (samples: WearableMetricSample[]) => {
  const userId = await getCurrentUserId();
  if (!userId) {
    throw new Error("Sesion requerida para simular metricas del reloj.");
  }

  const owned = samples.map((sample) => ({ ...sample, user_id: userId }));
  simulatedSamples = [
    ...simulatedSamples.filter((sample) => sample.user_id === userId),
    ...owned,
  ]
    .sort((left, right) => left.recordedAt - right.recordedAt)
    .slice(-MAX_SIMULATED_SAMPLES);

  return owned;
};

// Most recent first, only for the current account.
export const getSimulatedWearableMetricSamples = async () => {
  const userId = await getCurrentUserId();
  return simulatedSamples.filter((sample) => sample.user_id === userId).reverse();
};

export const createDevelopmentMetricSample = async (
  scenario: WearableSimulationScenario = "normal"
) => {
  const now = Date.now();
  const range = simulationScenarioRanges[scenario] ?? simulationScenarioRanges.normal;

  const heartRateBpm = Math.round(randomInRange(range.hrMin, range.hrMax));
  const speedKmh = Number(randomInRange(range.speedMin, range.speedMax).toFixed(1));
  const oxygenSaturation = Number(randomInRange(range.spo2Min, range.spo2Max).toFixed(1));

  const [sample] = await keepSimulatedSamples([{
    provider: "development_simulator",
    simulated: true,
    heartRateBpm,
    steps: Math.round(randomInRange(range.stepsMin, range.stepsMax)),
    activeEnergyKcal: Number(randomInRange(range.kcalMin, range.kcalMax).toFixed(1)),
    speedKmh,
    oxygenSaturation,
    recordedAt: now,
  }]);
  return sample;
};

export const createDevelopmentMetricSequence = async (
  scenario: WearableSimulationScenario = "normal",
  sampleCount = 8
) => {
  const now = Date.now();
  const range = simulationScenarioRanges[scenario] ?? simulationScenarioRanges.normal;
  const resolvedSampleCount = Math.max(3, Math.min(12, Math.round(sampleCount)));
  const spacingMs = 2 * 60 * 1000;
  const samples: WearableMetricSample[] = [];

  for (let index = 0; index < resolvedSampleCount; index += 1) {
    const progress = resolvedSampleCount <= 1 ? 1 : index / (resolvedSampleCount - 1);
    const point = getScenarioPoint(range, progress, now / 1000 + index);
    const steps = Math.round(
      randomInRange(range.stepsMin, range.stepsMax) * (0.78 + progress * 0.34)
    );
    const activeEnergyKcal = Number(
      (randomInRange(range.kcalMin, range.kcalMax) * (0.82 + progress * 0.32)).toFixed(1)
    );

    samples.push({
      provider: "development_simulator",
      simulated: true,
      heartRateBpm: point.heartRateBpm,
      steps,
      activeEnergyKcal,
      speedKmh: point.speedKmh,
      oxygenSaturation: point.oxygenSaturation,
      recordedAt: now - (resolvedSampleCount - index - 1) * spacingMs,
    });
  }

  return keepSimulatedSamples(samples);
};

export const linkNativeWearable = async () => {
  return linkNativeWearableProvider();
};

export const linkNativeWearableProvider = async (
  preferredProvider?: WearableProvider
) => {
  const context = await captureAccountContext();
  if (!context.userId || !(await getPrivacyPreferences(context)).sensitiveDataConsent) return false;
  const bridge = getNativeWearableBridge();
  const isAvailable = await bridge.isAvailable();

  if (!isAvailable) return false;

  const permissionsGranted = await bridge.requestPermissions();
  if (!permissionsGranted) return false;

  const provider =
    preferredProvider && androidNativeProviders.includes(preferredProvider)
      ? preferredProvider
      : bridge.provider;
  assertAccountContext(context);
  await saveWearableConnection(provider, true, true, context);
  return true;
};

export const syncNativeWearableSampleWithStatus = async (
  options?: NativeWearableReadOptions
): Promise<NativeWearableSyncStatus> => {
  const context = await captureAccountContext();
  try {
  if (!context.userId || !(await getPrivacyPreferences(context)).sensitiveDataConsent) return "permission_denied";
  const bridge = getNativeWearableBridge();
  const isAvailable = await bridge.isAvailable();

  if (!isAvailable) return "unavailable";

  const connection = await getWearableConnection(context);
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

  // Recheck after the native read, since consent can be withdrawn while it runs.
  assertAccountContext(context);
  if (!(await getPrivacyPreferences(context)).sensitiveDataConsent) return "permission_denied";

  await saveWearableConnection(provider, true, true, context);
  if (!sample) return "no_data";

  const saved = await saveWearableMetricSample({
    ...sample,
    provider,
  }, context);
  return saved ? "saved" : "duplicate";
  } catch (error) {
    if (error instanceof AccountContextChanged) return "permission_denied";
    throw error;
  }
};

export const MAX_HEALTH_SAMPLE_AGE_MS = 5 * 60 * 1000;

export const isFreshHealthSample = (sample: WearableMetricSample | null, now = Date.now()) =>
  !!sample && Number.isFinite(sample.recordedAt) && sample.recordedAt <= now + 30000 && now - sample.recordedAt <= MAX_HEALTH_SAMPLE_AGE_MS;

export const predictWearableHealth = (
  sample: WearableMetricSample | null,
  elapsedMinutes = 0,
  _elevationGainM?: number | null
): WearableHealthPrediction | null => {
  if (!sample || !isFreshHealthSample(sample)) return null;
  const assessment = assessWearableReadings(sample);
  if (!assessment) return null;
  const { level, cardiacLoad, readingAlert, coverage, heartRateBpm, oxygenSaturation, criticalHeartRate, criticalOxygen } = assessment;
  const factors: string[] = [];
  if (heartRateBpm !== null) {
    factors.push(`Pulso medido: ${heartRateBpm} bpm`);
    if (heartRateBpm >= wearableReadingThresholds.pulseReview) factors.push("Pulso elevado: revisar lectura");
    else if (heartRateBpm >= wearableReadingThresholds.pulseHighLoad) factors.push("Frecuencia cardiaca muy elevada");
    else if (heartRateBpm >= wearableReadingThresholds.pulseNotice) factors.push("Frecuencia cardiaca elevada");
  }
  if (oxygenSaturation !== null) {
    factors.push(`SpO₂ medida: ${oxygenSaturation}%`);
    if (criticalOxygen) factors.push("SpO₂ baja: revisar lectura");
    else if (oxygenSaturation < wearableReadingThresholds.oxygenNotice) factors.push("SpO₂ por debajo del umbral de aviso");
  }
  if (typeof sample.speedKmh === "number" && Number.isFinite(sample.speedKmh) && sample.speedKmh >= 0) {
    factors.push(`Velocidad medida: ${sample.speedKmh} km/h`);
  }
  if (Number.isFinite(elapsedMinutes) && elapsedMinutes > 0) factors.push(`Tiempo de actividad: ${Math.round(elapsedMinutes)} min`);
  const scope = coverage === "pulse_only" ? "solo pulso" : coverage === "oxygen_only" ? "solo SpO₂" : "pulso y SpO₂";
  const recommendedAction = level === "high"
    ? "Pausá el esfuerzo y repetí la lectura en reposo. Si tenés síntomas intensos o empeoran, buscá ayuda; usá SOS si necesitás asistencia urgente."
    : level === "caution"
      ? "Bajá el ritmo, comprobá la lectura y revisá cómo te sentís antes de seguir."
      : "Seguí revisando cómo te sentís y las condiciones de la caminata; una lectura aislada no determina si es seguro continuar.";
  return {
    method: "sensor_rules", coverage, level, cardiacLoad, readingAlert,
    ...getWearablePredictionCopy(level, { criticalHeartRate, criticalOxygen }),
    analysisSummary: `Análisis de la última lectura (${scope}). ${cardiacLoad === null ? "" : `Carga orientativa por pulso: ${cardiacLoad}. `}Avisos: ${readingAlert.toLowerCase()}. No mide fatiga ni diagnostica enfermedades.`,
    factors, recommendedAction,
  };
};

const getWearablePredictionCopy = (
  level: HealthPredictionLevel,
  sample: { criticalHeartRate: boolean; criticalOxygen: boolean }
) => {
  if (level === "high") {
    return {
      title: sample.criticalOxygen ? "SpO₂ baja: revisar lectura" : "Pulso elevado: revisar lectura",
      message: "Se activó un umbral de revisión prioritaria. Comprobá la lectura en reposo y prestá atención a los síntomas.",
    };
  }
  if (level === "caution") {
    return { title: "Revisar intensidad y lectura", message: "Se activó un aviso por pulso o SpO₂. Bajá el ritmo y comprobá cómo te sentís." };
  }
  return { title: "Lecturas revisadas", message: "No se activaron los umbrales de aviso con las lecturas recibidas. Considerá también tus síntomas y las condiciones del recorrido." };
};

export const getWearableRuntimeStatus = async (
  elapsedMinutes = 0
): Promise<WearableRuntimeStatus> => {
  const [connection, persistedSample, privacy, [simulatedSample = null]] = await Promise.all([
    getWearableConnection(),
    getLatestWearableMetricSample(),
    getPrivacyPreferences(),
    getSimulatedWearableMetricSamples(),
  ]);

  // A fresh in-memory simulated reading takes precedence so alert rules can be
  // tested; it is flagged as simulated and expires like any other reading.
  const isSimulated = isFreshHealthSample(simulatedSample);
  const latestSample = isSimulated ? simulatedSample : persistedSample;
  const isLinked = isSimulated || (connection.linked && connection.permissionsGranted);

  const prediction =
    isLinked && privacy.sensitiveDataConsent
      ? predictWearableHealth(latestSample, elapsedMinutes)
      : null;

  return {
    connection,
    status: !privacy.sensitiveDataConsent
      ? "requires_consent"
      : isLinked
        ? latestSample
          ? isFreshHealthSample(latestSample) ? "linked" : "stale_data"
          : "waiting_for_native_data"
        : "not_linked",
    latestSample: privacy.sensitiveDataConsent ? latestSample : null,
    prediction,
    displayName: getWearableProviderName(isSimulated ? "development_simulator" : connection.provider),
  };
};
