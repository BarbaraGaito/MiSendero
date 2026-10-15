import { FatigueLevel } from "../types";
import { OfflinePrediction, RandomForestModel } from "./modelTypes";

// No fatigue or physiological-risk model has deployment approval. The public
// research forests (training/data/public) use other labels and time scales, and
// the former prototype forests trained on rule-generated targets were removed.
const NO_APPROVED_MODEL =
  "No hay un modelo con validación aprobada con mediciones y etiquetas públicas reales para este uso.";

const unavailable = (reason: string): OfflinePrediction => ({ label: "sin_datos", confidence: 0, distances: {}, reason });

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
    return unavailable("Faltan variables requeridas por el modelo.");
  }
  const featureValues = model.feature_order.map((feature) => input[feature]);
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
    label: model.classes[bestIndex],
    confidence: Number(averageProbabilities[bestIndex].toFixed(2)),
    distances,
  };
};

export const predictFatigue = (_input: {
  hr: number;
  speedKmh: number;
  elapsedMinutes: number;
}): OfflinePrediction => unavailable(NO_APPROVED_MODEL);

export const predictPhysioRisk = (_input: {
  hr: number;
  spo2?: number | null;
  speedKmh: number;
  elapsedMinutes: number;
  elevationGainM?: number | null;
  fatigue: FatigueLevel;
}): OfflinePrediction => unavailable(NO_APPROVED_MODEL);
