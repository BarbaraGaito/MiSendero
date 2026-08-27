import { predictFatigue, predictFatigueLevel, predictPhysioRisk, offlineAiMetadata } from "../inferenceEngine";

const validLabels = ["bajo", "medio", "alto"];

describe("inferenceEngine (RandomForest, trained via training/python)", () => {
  test("loaded models are well-formed random_forest_json artifacts", () => {
    for (const model of [offlineAiMetadata.fatigueModel, offlineAiMetadata.riskModel]) {
      expect(model.type).toBe("random_forest_json");
      expect(model.trees.length).toBeGreaterThan(0);
      expect(model.classes.sort()).toEqual([...validLabels].sort());
      expect(model.feature_order.length).toBeGreaterThan(0);
    }
  });

  test("predictFatigue returns a valid label with a probability distribution over all classes", () => {
    const prediction = predictFatigue({ hr: 150, speedKmh: 2, elapsedMinutes: 90 });

    expect(validLabels).toContain(prediction.label);
    expect(prediction.confidence).toBeGreaterThanOrEqual(0);
    expect(prediction.confidence).toBeLessThanOrEqual(1);
    expect(Object.keys(prediction.distances).sort()).toEqual([...validLabels].sort());

    const probabilitySum = Object.values(prediction.distances).reduce((a, b) => a + b, 0);
    expect(probabilitySum).toBeCloseTo(1, 1);
  });

  test("predictFatigue trends toward higher fatigue as heart rate and elapsed time rise", () => {
    const early = predictFatigue({ hr: 95, speedKmh: 4.5, elapsedMinutes: 5 });
    const late = predictFatigue({ hr: 165, speedKmh: 2, elapsedMinutes: 120 });

    expect(early.distances.bajo).toBeGreaterThan(late.distances.bajo);
  });

  test("predictFatigueLevel always returns one of the three known levels", () => {
    expect(validLabels).toContain(
      predictFatigueLevel({ hr: 100, speedKmh: 4, elapsedMinutes: 10 })
    );
  });

  test("predictPhysioRisk incorporates elevation gain and fatigue level", () => {
    const lowRisk = predictPhysioRisk({
      hr: 95,
      speedKmh: 4.5,
      elapsedMinutes: 10,
      elevationGainM: 50,
      fatigue: "bajo",
    });
    const highRisk = predictPhysioRisk({
      hr: 170,
      speedKmh: 1.5,
      elapsedMinutes: 150,
      elevationGainM: 900,
      fatigue: "alto",
    });

    expect(validLabels).toContain(lowRisk.label);
    expect(validLabels).toContain(highRisk.label);
    expect(highRisk.distances.alto).toBeGreaterThan(lowRisk.distances.alto);
  });
});
