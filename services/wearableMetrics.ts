import * as SQLite from "expo-sqlite";
import { wearableStorageSql } from "../database/wearableSchema";
import {
  predictFatigue,
  predictPhysioRisk,
} from "../ai/inferenceEngine";
import {
  FatigueLevel,
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

export const createDevelopmentMetricSequence = async (
  scenario: WearableSimulationScenario = "normal",
  sampleCount = 8
) => {
  const connection = await getWearableConnection();
  const provider = connection.provider || "development_simulator";
  const now = Date.now();
  const range = simulationScenarioRanges[scenario] ?? simulationScenarioRanges.normal;
  const resolvedSampleCount = Math.max(3, Math.min(12, Math.round(sampleCount)));
  const spacingMs = 2 * 60 * 1000;

  for (let index = 0; index < resolvedSampleCount; index += 1) {
    const progress = resolvedSampleCount <= 1 ? 1 : index / (resolvedSampleCount - 1);
    const point = getScenarioPoint(range, progress, now / 1000 + index);
    const steps = Math.round(
      randomInRange(range.stepsMin, range.stepsMax) * (0.78 + progress * 0.34)
    );
    const activeEnergyKcal = Number(
      (randomInRange(range.kcalMin, range.kcalMax) * (0.82 + progress * 0.32)).toFixed(1)
    );

    await saveWearableMetricSample({
      provider,
      heartRateBpm: point.heartRateBpm,
      steps,
      activeEnergyKcal,
      speedKmh: point.speedKmh,
      oxygenSaturation: point.oxygenSaturation,
      recordedAt: now - (resolvedSampleCount - index - 1) * spacingMs,
    });
  }
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

export const MAX_HEALTH_SAMPLE_AGE_MS = 5 * 60 * 1000;

export const isFreshHealthSample = (sample: WearableMetricSample | null, now = Date.now()) =>
  !!sample && Number.isFinite(sample.recordedAt) && sample.recordedAt <= now + 30000 && now - sample.recordedAt <= MAX_HEALTH_SAMPLE_AGE_MS;

export const predictWearableHealth = (
  sample: WearableMetricSample | null,
  elapsedMinutes = 0,
  elevationGainM?: number | null
): WearableHealthPrediction | null => {
  if (!sample?.heartRateBpm || !isFreshHealthSample(sample) || !Number.isFinite(sample.heartRateBpm) || sample.heartRateBpm < 30 || sample.heartRateBpm > 240) return null;

  const fatiguePrediction = predictFatigue({
    hr: sample.heartRateBpm,
    speedKmh: sample.speedKmh ?? Number.NaN,
    elapsedMinutes,
  });
  const fatigue = fatiguePrediction.label === "alto" || fatiguePrediction.label === "medio" || fatiguePrediction.label === "bajo"
    ? fatiguePrediction.label : "sin_datos";
  const risk = predictPhysioRisk({
    hr: sample.heartRateBpm,
    spo2: sample.oxygenSaturation,
    speedKmh: sample.speedKmh ?? Number.NaN,
    elapsedMinutes,
    elevationGainM,
    fatigue: fatigue as FatigueLevel,
  });
  const riskLabel =
    risk.label === "alto" || risk.label === "medio" || risk.label === "bajo"
      ? risk.label
      : "sin_datos";

  const criticalOxygen =
    sample.oxygenSaturation !== null && sample.oxygenSaturation >= 50 && sample.oxygenSaturation < 90;
  const criticalHeartRate = sample.heartRateBpm >= 180;
  const factors = [
    sample.heartRateBpm >= 180
      ? "Pulso elevado: revisar lectura"
      : sample.heartRateBpm >= 165
        ? "Frecuencia cardiaca muy elevada"
        : sample.heartRateBpm >= 145
          ? "Frecuencia cardiaca elevada"
          : `Pulso medido: ${sample.heartRateBpm} bpm`,
    sample.oxygenSaturation === null || !Number.isFinite(sample.oxygenSaturation) || sample.oxygenSaturation < 50 || sample.oxygenSaturation > 100
      ? "SpO₂ sin lectura válida"
      : sample.oxygenSaturation < 90
      ? "Oxigeno bajo"
      : sample.oxygenSaturation !== null && sample.oxygenSaturation < 94
        ? "SpO₂ por debajo del umbral de aviso experimental"
        : `SpO₂ medida: ${sample.oxygenSaturation}%`,
    fatigue === "sin_datos" ? "Fatiga sin datos suficientes" : fatigue === "alto"
      ? "Fatiga estimada alta"
      : fatigue === "medio"
        ? "Fatiga estimada media"
        : "Fatiga estimada baja",
    sample.speedKmh === null ? "Velocidad no medida" : sample.speedKmh < 2
      ? "Ritmo reducido"
      : `Velocidad medida: ${sample.speedKmh} km/h`,
  ];
  const level = getWearablePredictionLevel({
    criticalHeartRate,
    criticalOxygen,
    fatigue,
    heartRateBpm: sample.heartRateBpm,
    riskLabel,
  });

  const recommendedAction =
    level === "high"
      ? criticalOxygen || criticalHeartRate
        ? "Detenerse, descansar y evaluar SOS si los sintomas continuan."
        : "Pausar, hidratarse y retomar solo si las metricas bajan."
      : level === "caution"
        ? "Bajar el ritmo y volver a revisar las metricas en unos minutos."
        : "Revisá cómo te sentís y los datos disponibles. La IA no autoriza a continuar.";

  return {
    level,
    ...getWearablePredictionCopy(level, {
      criticalHeartRate,
      criticalOxygen,
      heartRateBpm: sample.heartRateBpm,
      oxygenSaturation: sample.oxygenSaturation,
    }),
    ...(riskLabel === "sin_datos" && level === "normal" ? { title: "Análisis limitado", message: "Faltan variables para evaluar riesgo. Una lectura disponible no confirma que estés fuera de peligro." } : {}),
    fatigue,
    fatigueConfidence: fatiguePrediction.confidence,
    riskLabel,
    riskConfidence: risk.confidence,
    analysisSummary: `Modelo experimental local. Fatiga: ${fatigue === "sin_datos" ? "sin datos" : fatigue}. Riesgo: ${riskLabel === "sin_datos" ? "no estimable; faltan variables medidas" : riskLabel}. No evalúa si es seguro continuar.`,
    factors,
    recommendedAction,
  };
};

const getWearablePredictionLevel = ({
  criticalHeartRate,
  criticalOxygen,
  fatigue,
  heartRateBpm,
  riskLabel,
}: {
  criticalHeartRate: boolean;
  criticalOxygen: boolean;
  fatigue: FatigueLevel | "sin_datos";
  heartRateBpm: number;
  riskLabel: string;
}): HealthPredictionLevel => {
  if (criticalOxygen || criticalHeartRate) {
    return "high";
  }

  if (
    riskLabel === "alto" ||
    riskLabel === "medio" ||
    heartRateBpm >= 145 ||
    fatigue === "alto" ||
    fatigue === "medio"
  ) {
    return "caution";
  }

  return "normal";
};

const getWearablePredictionCopy = (
  level: HealthPredictionLevel,
  sample: {
    criticalHeartRate: boolean;
    criticalOxygen: boolean;
    heartRateBpm: number;
    oxygenSaturation: number | null;
  }
) => {
  if (level === "high") return getHighWearablePredictionCopy(sample);
  if (level === "caution") {
    return {
      title: sample.heartRateBpm >= 160 ? "Fatiga alta" : "Mantener atencion",
      message:
        sample.heartRateBpm >= 160
          ? "Las metricas muestran esfuerzo alto. Hace una pausa, hidratate y continua solo si te sentis bien."
          : "Las metricas indican esfuerzo moderado. Baja el ritmo si notas cansancio, mareos o falta de aire.",
    };
  }

  return {
    title: "Estimación con datos disponibles",
    message:
      "Estimación orientativa con las variables disponibles. No es una evaluación clínica.",
  };
};

const getHighWearablePredictionCopy = ({
  criticalHeartRate,
  criticalOxygen,
  heartRateBpm,
  oxygenSaturation,
}: {
  criticalHeartRate: boolean;
  criticalOxygen: boolean;
  heartRateBpm: number;
  oxygenSaturation: number | null;
}) => {
  if (criticalOxygen) {
    return {
      title: "SpO₂ baja: revisar lectura",
      message: `Tu oxigeno en sangre (${oxygenSaturation}%) esta por debajo del umbral de aviso experimental. Deten la actividad, respira con calma y busca ayuda si no mejora.`,
    };
  }

  if (criticalHeartRate) {
    return {
      title: "Pulso elevado: revisar lectura",
      message: `Tu frecuencia cardiaca (${heartRateBpm} bpm) es muy elevada. Deten la actividad de inmediato y evalua pedir ayuda.`,
    };
  }

  return {
    title: "Revisar intensidad",
    message:
      "Tu esfuerzo actual aparece elevado. Pausa, hidratate y evalua como te sentis antes de continuar.",
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
          ? isFreshHealthSample(latestSample) ? "linked" : "stale_data"
          : "waiting_for_native_data"
        : "not_linked",
    latestSample: privacy.sensitiveDataConsent ? latestSample : null,
    prediction,
    displayName: getWearableProviderName(connection.provider),
  };
};
