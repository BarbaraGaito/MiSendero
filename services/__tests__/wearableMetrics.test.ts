import {
  createDevelopmentMetricSample,
  createDevelopmentMetricSequence,
  getRecentWearableMetricSamples,
  getSimulatedWearableMetricSamples,
  getWearableRuntimeStatus,
  predictWearableHealth,
  saveWearableConnection,
  saveWearableMetricSample,
} from "../wearableMetrics";
import { WearableMetricSample } from "../../types";
import { db } from "../../database/connection";
import { initDB } from "../../database/database";
import { saveAuthSession } from "../authSession";
import { savePrivacyPreferences } from "../privacyConsent";

const sample = (overrides: Partial<WearableMetricSample>): WearableMetricSample => ({
  provider: "development_simulator",
  heartRateBpm: 90,
  steps: 2200,
  activeEnergyKcal: 180,
  speedKmh: 4.5,
  oxygenSaturation: 98,
  recordedAt: Date.now(),
  ...overrides,
});

describe("predictWearableHealth", () => {
  test("fresh sensor readings produce an actual assessment without an unavailable model or fabricated confidence", () => {
    const result = predictWearableHealth(sample({ heartRateBpm: 90, speedKmh: 4.5, oxygenSaturation: 98 }));
    expect(result).toMatchObject({ method: "sensor_rules", coverage: "pulse_and_oxygen", level: "normal", cardiacLoad: "baja", readingAlert: "Sin umbrales activados" });
    expect(result?.title).toBe("Lecturas revisadas");
    expect(JSON.stringify(result)).not.toMatch(/sin_datos|Sin datos|modelo validado/);
    expect(result).not.toHaveProperty("riskConfidence");
    expect(result).not.toHaveProperty("fatigueConfidence");
  });
  test("does not present missing oxygen or speed as stable measured values", () => {
    const result = predictWearableHealth(sample({ oxygenSaturation: null, speedKmh: null }));
    expect(result).toMatchObject({ coverage: "pulse_only", cardiacLoad: "baja", level: "normal" });
    expect(result?.factors).toContain("Pulso medido: 90 bpm");
    expect(result?.factors?.join(" ")).not.toContain("SpO₂ medida");
    expect(result?.factors?.join(" ")).not.toContain("Velocidad medida");
    expect(result?.analysisSummary).toContain("solo pulso");
    expect(result?.analysisSummary).not.toContain("Confianza");
  });
  test("does not infer from stale, future, or invalid pulse readings", () => {
    expect(predictWearableHealth(sample({ recordedAt: Date.now() - 301000 }))).toBeNull();
    expect(predictWearableHealth(sample({ recordedAt: Date.now() + 60000 }))).toBeNull();
    expect(predictWearableHealth(sample({ heartRateBpm: Number.NaN, oxygenSaturation: null }))).toBeNull();
  });
  test("oxygen alone still triggers review without inventing pulse or cardiac load", () => {
    const result = predictWearableHealth(sample({ heartRateBpm: null, oxygenSaturation: 88, speedKmh: null }));
    expect(result).toMatchObject({ coverage: "oxygen_only", level: "high", cardiacLoad: null, title: "SpO₂ baja: revisar lectura" });
    expect(result?.analysisSummary).toContain("solo SpO₂");
    expect(result?.factors?.join(" ")).not.toContain("Pulso medido");
  });
  test("an oxygen notice is not hidden by an ordinary pulse reading", () => {
    expect(predictWearableHealth(sample({ heartRateBpm: 90, oxygenSaturation: 92 }))?.level).toBe("caution");
  });
  test("invalid supplementary values are ignored and never treated as measurements", () => {
    const result = predictWearableHealth(sample({ heartRateBpm: 150, oxygenSaturation: NaN, speedKmh: -1 }), Infinity);
    expect(result).toMatchObject({ coverage: "pulse_only", level: "caution", cardiacLoad: "media" });
    expect(result?.factors?.join(" ")).not.toMatch(/NaN|Infinity|Velocidad|Tiempo de actividad/);
  });
  test("mantiene esfuerzo moderado y fatiga alta como advertencia sin emergencia", () => {
    expect(
      predictWearableHealth(sample({ heartRateBpm: 145, speedKmh: 3.2, oxygenSaturation: 95 }))?.level
    ).toBe("caution");
    expect(
      predictWearableHealth(sample({ heartRateBpm: 170, speedKmh: 1.8, oxygenSaturation: 92 }))?.level
    ).toBe("caution");
  });

  test("marca riesgo fisiologico critico cuando hay FC critica u oxigeno bajo", () => {
    expect(
      predictWearableHealth(sample({ heartRateBpm: 184, speedKmh: 1.1, oxygenSaturation: 91 }))?.level
    ).toBe("high");
    expect(
      predictWearableHealth(sample({ heartRateBpm: 168, speedKmh: 1.1, oxygenSaturation: 88 }))?.level
    ).toBe("high");
  });
});

describe("development simulator", () => {
  beforeAll(async () => {
    await initDB();
    await saveAuthSession({ token: "sim-301", user: { id: 301, name: "Test", email: "301@example.test" } });
    await savePrivacyPreferences({ sensitiveDataConsent: true, analyticsTrainingConsent: false });
    // A real provider is linked: simulated readings must never be attributed to it.
    await saveWearableConnection("apple_healthkit", true, true);
  });
  afterEach(() => jest.restoreAllMocks());

  test("keeps simulated samples in memory only and never under a real provider", async () => {
    const runAsync = jest.spyOn(db, "runAsync");
    const execAsync = jest.spyOn(db, "execAsync");

    const window = await createDevelopmentMetricSequence("riesgo_fisiologico", 8);
    const quick = await createDevelopmentMetricSample("normal");

    expect(runAsync).not.toHaveBeenCalled();
    expect(execAsync.mock.calls.filter(([sql]) => sql.includes("wearable"))).toEqual([]);
    jest.restoreAllMocks();
    const stored = await db.getFirstAsync<{ count: number }>("SELECT COUNT(*) AS count FROM wearable_metric_samples");
    expect(stored?.count).toBe(0);
    expect(await getRecentWearableMetricSamples()).toEqual([]);
    expect(window).toHaveLength(8);
    for (const generated of [...window, quick]) {
      expect(generated.provider).toBe("development_simulator");
      expect(generated.simulated).toBe(true);
    }
    expect((await getSimulatedWearableMetricSamples())[0]).toEqual(quick);
  });

  test("a fresh simulated reading still drives alert rules, labelled as simulator", async () => {
    await createDevelopmentMetricSample("riesgo_fisiologico");
    const status = await getWearableRuntimeStatus();

    expect(status.latestSample?.simulated).toBe(true);
    expect(status.displayName).toBe("Simulador (pruebas)");
    expect(status.prediction?.level).toBe("high");
    expect(status.connection.provider).toBe("apple_healthkit");
  });

  test("refuses to persist simulator samples", async () => {
    const reading = { heartRateBpm: 100, steps: null, activeEnergyKcal: null, speedKmh: 3, oxygenSaturation: 97, recordedAt: Date.now() };
    await expect(saveWearableMetricSample({ ...reading, provider: "development_simulator" })).rejects.toThrow("simuladas");
    await expect(saveWearableMetricSample({ ...reading, provider: "apple_healthkit", simulated: true })).rejects.toThrow("simuladas");
    const stored = await db.getFirstAsync<{ count: number }>("SELECT COUNT(*) AS count FROM wearable_metric_samples");
    expect(stored?.count).toBe(0);
  });
});
