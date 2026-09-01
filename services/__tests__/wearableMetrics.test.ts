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
