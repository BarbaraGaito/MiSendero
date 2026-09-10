import { predictWearableHealth } from "../wearableMetrics";
import { WearableMetricSample } from "../../types";

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
  test("does not present missing oxygen or speed as stable measured values", () => {
    const result = predictWearableHealth(sample({ oxygenSaturation: null, speedKmh: null }));
    expect(result?.riskLabel).toBe("sin_datos");
    expect(result?.fatigue).toBe("sin_datos");
    expect(result?.factors).toContain("SpO₂ sin lectura válida");
    expect(result?.title).toBe("Análisis limitado");
    expect(result?.analysisSummary).not.toContain("Confianza");
  });
  test("does not infer from stale, future, or invalid pulse readings", () => {
    expect(predictWearableHealth(sample({ recordedAt: Date.now() - 301000 }))).toBeNull();
    expect(predictWearableHealth(sample({ recordedAt: Date.now() + 60000 }))).toBeNull();
    expect(predictWearableHealth(sample({ heartRateBpm: Number.NaN }))).toBeNull();
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
