import { FatigueLevel } from "../types";
import { OfflinePrediction, RandomForestModel } from "./modelTypes";
import { fatigueInputs, predictFieldModel, type BorgCheckin, type FieldPrediction } from "./fieldInference";
import { fieldModels, amsBinaryDecisionSupported } from "./fieldRegistry";

// Legacy research forests retain their approval gate. Scoped public-data models
// use the separate registry and causal input contract below.

const unavailable = (reason: string, status: "model_not_approved" | "missing_inputs" = "model_not_approved"): OfflinePrediction =>
  ({ status, label: "sin_datos", confidence: 0, distances: {}, reason });

// sklearn's exported tree.children_left uses -1 to mark a leaf node; there is
// no separate "is_leaf" flag, so that convention is the traversal stop
// condition here too.
export const predictRandomForest = (
  model: RandomForestModel,
  input: Record<string, number>
): OfflinePrediction => {
  if (model.evaluation_validity?.real_public_ground_truth !== true ||
      model.evaluation_validity.deployment_approved !== true) {
    return unavailable("El modelo no tiene validación aprobada con mediciones y etiquetas públicas reales para este uso.");
  }
  if (model.feature_order.some((feature) => !Number.isFinite(input[feature]))) {
    return unavailable("Faltan variables requeridas por el modelo.", "missing_inputs");
  }
  const featureValues = model.feature_order.map((feature) => Math.fround(input[feature]));
  const classCount = model.classes.length;
  const summedProbabilities = new Array(classCount).fill(0);

  for (const tree of model.trees) {
    let nodeIndex = 0;

    while (tree.left[nodeIndex] !== -1) {
      const featureIndex = tree.feature[nodeIndex];
      const goLeft = featureValues[featureIndex] <= tree.threshold[nodeIndex];
      nodeIndex = goLeft ? tree.left[nodeIndex] : tree.right[nodeIndex];
    }

    const leafProbabilities = tree.value[nodeIndex];
    for (let classIndex = 0; classIndex < classCount; classIndex++) {
      summedProbabilities[classIndex] += leafProbabilities[classIndex] ?? 0;
    }
  }

  const averageProbabilities = summedProbabilities.map(
    (sum) => sum / model.trees.length
  );
  const distances: Record<string, number> = {};
  let bestIndex = 0;

  for (let classIndex = 0; classIndex < classCount; classIndex++) {
    distances[model.classes[classIndex]] = Number(averageProbabilities[classIndex].toFixed(4));

    if (averageProbabilities[classIndex] > averageProbabilities[bestIndex]) {
      bestIndex = classIndex;
    }
  }

  return {
    status: "available",
    label: model.classes[bestIndex],
    confidence: Number(averageProbabilities[bestIndex].toFixed(2)),
    distances,
  };
};

const legacyPrediction = (result: FieldPrediction): OfflinePrediction => ({
  status: result.status === "available" ? "available" : result.status === "not_eligible" ? "model_not_approved" : "missing_inputs",
  label: result.label ?? "sin_datos", confidence: 0, distances: {}, reason: result.reason,
});

export const predictFatigue = (input: {
  hr: number;
  speedKmh: number;
  elapsedMinutes: number;
  checkins?: BorgCheckin[];
  assessedAt?: number;
  completedMinuteHr?: number;
}): OfflinePrediction => {
  const now = input.assessedAt ?? Date.now();
  return legacyPrediction(predictFieldModel(fieldModels.fatigue, "fatigue", fatigueInputs(input.completedMinuteHr ?? null, input.checkins ?? [], now), "fatigue_recent_borg", now));
};

export const predictPhysioRisk = (input: {
  hr: number;
  spo2?: number | null;
  speedKmh: number;
  elapsedMinutes: number;
  elevationGainM?: number | null;
  fatigue: FatigueLevel;
  altitudeM?: number;
  morningRestConfirmed?: boolean;
  assessedAt?: number;
}): OfflinePrediction => {
  const result = predictFieldModel(fieldModels.ams, "ams", {
  hr: input.hr, spo2: input.spo2, altitude_m: input.altitudeM,
  }, input.morningRestConfirmed === true ? "ams_morning_next_ascent" : "unsupported", input.assessedAt ?? Date.now());
  if (result.status === "available" && !amsBinaryDecisionSupported) return unavailable("El control de altura ofrece una puntuación orientativa, sin clasificación binaria validada.");
  return legacyPrediction(result);
};
