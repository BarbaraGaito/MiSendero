import { predictFatigue, predictPhysioRisk, predictRandomForest } from "../inferenceEngine";
import { RandomForestModel } from "../modelTypes";

// Hand-written one-split tree used only to exercise the traversal; not a trained model.
const forest = (deploymentApproved: boolean): RandomForestModel => ({
  type: "random_forest_json",
  version: 1,
  feature_order: ["x"],
  classes: ["A", "B"],
  trees: [{ feature: [0, -2, -2], threshold: [5, -2, -2], left: [1, -1, -1], right: [2, -1, -1], value: [[0.5, 0.5], [1, 0], [0, 1]] }],
  evaluation_validity: { real_public_ground_truth: true, deployment_approved: deploymentApproved, reason: "test" },
});

describe("public ground-truth deployment policy", () => {
  test("live measurements abstain because no fatigue model is approved", () => {
    const prediction = predictFatigue({ hr: 150, speedKmh: 2, elapsedMinutes: 90 });
    expect(prediction.label).toBe("sin_datos");
    expect(prediction.status).toBe("model_not_approved");
    expect(prediction.confidence).toBe(0);
    expect(prediction.distances).toEqual({});
    expect(prediction.reason).toContain("validación aprobada");
  });

  test("live measurements abstain because no risk model is approved", () => {
    const prediction = predictPhysioRisk({ hr: 170, spo2: 90, speedKmh: 1.5,
      elapsedMinutes: 150, elevationGainM: 900, fatigue: "alto" });
    expect(prediction.label).toBe("sin_datos");
    expect(prediction.confidence).toBe(0);
    expect(prediction.distances).toEqual({});
    expect(prediction.reason).toContain("validación aprobada");
  });

  test("forests run only with deployment approval and complete inputs", () => {
    expect(predictRandomForest(forest(false), { x: 3 }).label).toBe("sin_datos");
    expect(predictRandomForest(forest(true), { x: Number.NaN }).label).toBe("sin_datos");
    expect(predictRandomForest(forest(true), { x: 3 })).toMatchObject({ label: "A", confidence: 1 });
    expect(predictRandomForest(forest(true), { x: 7 })).toMatchObject({ label: "B", confidence: 1 });
    expect(predictRandomForest(forest(false), { x: 3 }).status).toBe("model_not_approved");
    expect(predictRandomForest(forest(true), { x: Number.NaN }).status).toBe("missing_inputs");
    expect(predictRandomForest(forest(true), { x: 3 }).status).toBe("available");
  });
});
