import fatigueModel from "./models/fatigueModel.json";
import riskModel from "./models/riskModel.json";
import { FatigueLevel } from "../types";
import { OfflinePrediction, RandomForestModel } from "./modelTypes";

type FeatureInput = Record<string, number | null | undefined>;

const fatigueScoreByLevel: Record<FatigueLevel, number> = {
  bajo: 1,
  medio: 2,
  alto: 3,
};

const toForestModel = (model: unknown) => model as RandomForestModel;

// sklearn's exported tree.children_left uses -1 to mark a leaf node; there is
// no separate "is_leaf" flag, so that convention is the traversal stop
// condition here too.
const predictRandomForest = (
  model: RandomForestModel,
  input: Record<string, number>
): OfflinePrediction => {
  const featureValues = model.feature_order.map((feature) => input[feature] ?? 0);
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

  return "bajo";
};

// A missing/unmeasured reading defaults to a normal, healthy saturation
// instead of 0 - unlike elevation or speed, 0 is not a neutral "no data"
// value for SpO2, it reads as a critical desaturation and would push the
// model toward "alto" for anyone without a pulse oximeter connected.
const DEFAULT_SPO2_PERCENT = 97;

export const predictPhysioRisk = (input: {
  hr: number;
  spo2?: number | null;
  speedKmh: number;
  elapsedMinutes: number;
  elevationGainM?: number | null;
  fatigue: FatigueLevel;
}): OfflinePrediction => {
  return predictRandomForest(toForestModel(riskModel), {
    hr: input.hr,
    spo2: input.spo2 ?? DEFAULT_SPO2_PERCENT,
    speed_kmh: input.speedKmh,
    elapsed_minutes: input.elapsedMinutes,
    elevation_gain_m: input.elevationGainM ?? 0,
    fatigue_score: fatigueScoreByLevel[input.fatigue],
  });
};

export const offlineAiMetadata = {
  fatigueModel: toForestModel(fatigueModel),
  riskModel: toForestModel(riskModel),
};
