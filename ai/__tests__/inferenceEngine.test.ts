import { predictFatigue, predictFatigueLevel, predictPhysioRisk, offlineAiMetadata } from "../inferenceEngine";

describe("public ground-truth deployment policy", () => {
  test("legacy forests remain auditable but have no deployment approval", () => {
    for (const model of [offlineAiMetadata.fatigueModel, offlineAiMetadata.riskModel]) {
      expect(model.type).toBe("random_forest_json");
      expect(model.trees.length).toBeGreaterThan(0);
      expect(model.evaluation_validity?.deployment_approved).not.toBe(true);
    }
  });

  test("valid live measurements cannot activate an unvalidated fatigue model", () => {
    const prediction = predictFatigue({ hr: 150, speedKmh: 2, elapsedMinutes: 90 });
    expect(prediction.label).toBe("sin_datos");
    expect(prediction.confidence).toBe(0);
    expect(prediction.distances).toEqual({});
    expect(prediction.reason).toContain("validación aprobada");
    expect(() => predictFatigueLevel({ hr: 100, speedKmh: 4, elapsedMinutes: 10 })).toThrow();
  });

  test("all required live measurements cannot activate an unvalidated risk model", () => {
    const prediction = predictPhysioRisk({ hr: 170, spo2: 90, speedKmh: 1.5,
      elapsedMinutes: 150, elevationGainM: 900, fatigue: "alto" });
    expect(prediction.label).toBe("sin_datos");
    expect(prediction.confidence).toBe(0);
    expect(prediction.distances).toEqual({});
    expect(prediction.reason).toContain("validación aprobada");
  });

  test("missing/non-finite measurements still abstain", () => {
    const input = { hr: 110, speedKmh: 3, elapsedMinutes: 20, fatigue: "bajo" as const };
    expect(predictPhysioRisk(input).label).toBe("sin_datos");
    expect(predictPhysioRisk({ ...input, spo2: 98 }).label).toBe("sin_datos");
    expect(predictFatigue({ hr: Number.NaN, speedKmh: 3, elapsedMinutes: 20 }).label).toBe("sin_datos");
    expect(predictFatigue({ hr: 110, speedKmh: -1, elapsedMinutes: 20 }).label).toBe("sin_datos");
  });
});
