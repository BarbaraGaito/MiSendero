import { classifierProbabilities, fieldDecision, fieldVector, predictFieldModel, fatigueInputs, type PortableClassifier, type FieldModel } from "../fieldInference";
import { fieldModels, amsBinaryDecisionSupported } from "../fieldRegistry";
import fatigueFixtures from "../../training/data/field-ai/v1/fatigue/evaluation/parity.json";
import amsFixtures from "../../training/data/field-ai/v1/ams/evaluation/parity.json";
import delivery from "../../training/data/field-ai/v1/delivery.json";
import { predictFatigue, predictPhysioRisk } from "../inferenceEngine";

test.each(["fatigue", "ams"] as const)("%s matches Python on every held-out observation before delivery gates", task => {
  const model = fieldModels[task]!;
  const fixtures = task === "fatigue" ? fatigueFixtures : amsFixtures;
  expect(fixtures.length).toBe(task === "fatigue" ? 179 : 139);
  for (const fixture of fixtures) {
    const actual = classifierProbabilities(model.classifier, fieldVector(model, fixture.inputs));
    actual.forEach((value, i) => expect(Math.abs(value-fixture.probabilities[i])).toBeLessThan(1e-6));
    const decision = fieldDecision(model, actual);
    expect(Math.abs((task === "fatigue" ? decision.value! : decision.score!)-fixture.value)).toBeLessThan(1e-6);
  }
});

test.each(["fatigue", "ams"] as const)("%s delivery coverage keeps the fixed test denominator", task => {
  const model = fieldModels[task]!;
  const fixtures = task === "fatigue" ? fatigueFixtures : amsFixtures;
  const statuses = fixtures.map(row => predictFieldModel(model, task, row.inputs, model.scope).status);
  expect(statuses.filter(value => value === "available")).toHaveLength(delivery[task].within_training_ranges);
  expect(statuses.filter(value => value === "outside_scope")).toHaveLength(delivery[task].outside_scope);
  expect(statuses.length).toBe(delivery[task].fixed_test_rows);
});

test("available scoped predictions require actual inputs, correct scope and observed ranges", () => {
  const model = fieldModels.fatigue!;
  const inputs = { hr: 118, prior_borg: 3, prior_age_minutes: 5 };
  const predict = (m: FieldModel | null = model, values = inputs, scope = model.scope) => predictFieldModel(m, "fatigue", values, scope, 100000);
  expect(predict().status).toBe("available");
  expect(predict(null).status).toBe("not_eligible");
  expect(predict({ ...model, runtime_eligible: false }).status).toBe("not_eligible");
  expect(predict({ ...model, dataset_sha256: "changed" }).status).toBe("invalid_model");
  expect(predict(model, inputs, "ams_morning_next_ascent").status).toBe("outside_scope");
  expect(predict(model, { ...inputs, hr: NaN }).status).toBe("missing_inputs");
  expect(predict(model, { ...inputs, hr: 200 }).status).toBe("outside_scope");
  expect(predict({ ...model, imputation: [] }).status).toBe("invalid_model");
  expect(predict({ ...model, classifier: { ...model.classifier, trees: [] } }).status).toBe("invalid_model");
  expect(() => fieldVector(model, { ...inputs, prior2_borg: Infinity })).toThrow();
});

test("Borg history is causal, bounded and sorted without mutation", () => {
  const now = 10000000;
  const rows = [{ borg: 9, recordedAt: now }, { borg: 5, recordedAt: now-180000 }, { borg: 7, recordedAt: now-60000 },
    { borg: 1, recordedAt: now-900001 }, { borg: 99, recordedAt: now-120000 }, { borg: 8, recordedAt: now+1000 }];
  expect(fatigueInputs(120, rows, now)).toEqual({ hr: 120, prior_borg: 7, prior_age_minutes: 1, prior2_borg: 5, prior2_age_minutes: 3 });
  expect(rows[0].borg).toBe(9);
  expect(fatigueInputs(null, [], now).prior_borg).toBeNull();
  expect(predictFatigue({ hr: 120, completedMinuteHr: 120, checkins: [{ borg: 3, recordedAt: now-300000 }], assessedAt: now, speedKmh: 4, elapsedMinutes: 10 }).status).toBe("available");
});

test("AMS delivery cannot turn the degenerate held-out threshold into risk alerts", () => {
  expect(amsBinaryDecisionSupported).toBe(false);
  expect(predictPhysioRisk({ hr: 75, spo2: 95, altitudeM: 3000, morningRestConfirmed: true, speedKmh: 0, elapsedMinutes: 0, fatigue: "bajo" }).status).not.toBe("available");
  expect(() => fieldDecision({ ...fieldModels.ams!, calibration: null }, [.5,.5])).toThrow();
  expect(() => fieldDecision({ ...fieldModels.fatigue!, classifier: { ...fieldModels.fatigue!.classifier, classes: ["wrong"] } }, [1])).toThrow();
});

test("portable linear and neural exporters implement sklearn probabilities and reject malformed models", () => {
  const linear: PortableClassifier = { type: "scaled_classifier_json", feature_order: ["x"], classes: ["a", "b"], scaler: { mean: [2], scale: [2] }, linear: { coef: [[2]], intercept: [0], multiclass: "ovr" } };
  expect(classifierProbabilities(linear, [2])).toEqual([.5,.5]);
  expect(classifierProbabilities(linear, [4])[1]).toBeCloseTo(1/(1+Math.exp(-2)));
  const multi = { ...linear, classes: ["a","b","c"], linear: { coef: [[0],[0],[0]], intercept: [0,0,0], multiclass: "multinomial" as const } };
  expect(classifierProbabilities(multi, [2])[0]).toBeCloseTo(1/3);
  expect(classifierProbabilities({ ...multi, linear: { ...multi.linear, multiclass: "ovr" } }, [2])[0]).toBeCloseTo(1/3);
  for (const activation of ["relu", "tanh", "identity", "logistic"]) {
    const network = { coefs: [[[1]], [[0,0]]], intercepts: [[0],[0,0]], activation, out_activation: "softmax" };
    expect(classifierProbabilities({ ...linear, linear: undefined, network }, [2])).toEqual([.5,.5]);
  }
  expect(classifierProbabilities({ ...linear, linear: undefined, network: { coefs: [[[1]]], intercepts: [[0]], activation: "relu", out_activation: "logistic" } }, [2])).toEqual([.5,.5]);
  for (const broken of [{ ...linear, scaler: undefined }, { ...linear, linear: undefined }, { ...linear, scaler: { mean: [0], scale: [0] } }, { ...linear, linear: { ...linear.linear!, coef: [[]] } }]) expect(() => classifierProbabilities(broken, [2])).toThrow();
  expect(() => classifierProbabilities(linear, [])).toThrow();
  expect(() => classifierProbabilities({ ...linear, linear: undefined, network: { coefs: [[[1]]], intercepts: [[0]], activation: "relu", out_activation: "bad" } }, [2])).toThrow();
  expect(() => classifierProbabilities({ ...linear, linear: undefined, network: { coefs: [[]], intercepts: [[0]], activation: "relu", out_activation: "softmax" } }, [2])).toThrow();
  const tree = { feature: [0], threshold: [1], left: [0], right: [0], value: [[0,0]] };
  expect(() => classifierProbabilities({ type: "random_forest_json", classes: ["a","b"], feature_order: ["x"], trees: [tree] }, [0])).toThrow();
  expect(() => classifierProbabilities({ type: "random_forest_json", classes: ["a","b"], feature_order: ["x"], trees: [{ ...tree, left: [-1] }] }, [0])).toThrow();
});
