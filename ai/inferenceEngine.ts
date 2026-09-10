import fatigueModel from "./models/fatigueModel.json";
import riskModel from "./models/riskModel.json";
import { FatigueLevel } from "../types";
import { OfflinePrediction, RandomForestModel } from "./modelTypes";

const fatigueScoreByLevel: Record<FatigueLevel, number> = {
  bajo: 1,
  medio: 2,
  alto: 3,
};

const toForestModel = (model: unknown) => model as RandomForestModel;

const unavailable = (reason: string): OfflinePrediction => ({ label: "sin_datos", confidence: 0, distances: {}, reason });
const inRange = (value: number | null | undefined, min: number, max: number) =>
  typeof value === "number" && Number.isFinite(value) && value >= min && value <= max;

// sklearn's exported tree.children_left uses -1 to mark a leaf node; there is
// no separate "is_leaf" flag, so that convention is the traversal stop
// condition here too.
const predictRandomForest = (
  model: RandomForestModel,
  input: Record<string, number>
): OfflinePrediction => {
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

export const predictFatigue = (input: {
  hr: number;
  speedKmh: number;
  elapsedMinutes: number;
}): OfflinePrediction => {
  if (!inRange(input.hr, 30, 240) || !inRange(input.speedKmh, 0, 25) || !inRange(input.elapsedMinutes, 0, 1440)) {
    return unavailable("Faltan pulso, velocidad o duración válidos para estimar fatiga.");
  }
  const hrReservePercent = Math.max(0, Math.min(100, ((input.hr - 60) / 120) * 100));

  return predictRandomForest(toForestModel(fatigueModel), {
    hr: input.hr,
    speed_kmh: input.speedKmh,
    elapsed_minutes: input.elapsedMinutes,
    hr_reserve_percent: hrReservePercent,
  });
};

export const predictFatigueLevel = (input: {
  hr: number;
  speedKmh: number;
  elapsedMinutes: number;
}): FatigueLevel => {
  const label = predictFatigue(input).label;

  if (label === "alto" || label === "medio" || label === "bajo") {
    return label;
  }

  throw new Error("No hay datos válidos para estimar fatiga.");
};

export const predictPhysioRisk = (input: {
  hr: number;
  spo2?: number | null;
  speedKmh: number;
  elapsedMinutes: number;
  elevationGainM?: number | null;
  fatigue: FatigueLevel;
}): OfflinePrediction => {
  if (!inRange(input.hr, 30, 240) || !inRange(input.spo2, 50, 100) ||
      !inRange(input.speedKmh, 0, 25) || !inRange(input.elapsedMinutes, 0, 1440) ||
      !inRange(input.elevationGainM, 0, 6000) || !fatigueScoreByLevel[input.fatigue]) {
    return unavailable("El modelo de riesgo necesita pulso, SpO₂, velocidad, tiempo, desnivel medido y fatiga válidos.");
  }
  return predictRandomForest(toForestModel(riskModel), {
    hr: input.hr,
    spo2: input.spo2!,
    speed_kmh: input.speedKmh,
    elapsed_minutes: input.elapsedMinutes,
    elevation_gain_m: input.elevationGainM!,
    fatigue_score: fatigueScoreByLevel[input.fatigue],
  });
};

export const offlineAiMetadata = {
  fatigueModel: toForestModel(fatigueModel),
  riskModel: toForestModel(riskModel),
};
