import fatigueModel from "./models/fatigueModel.json";
import riskModel from "./models/riskModel.json";
import routeDifficultyModel from "./models/routeDifficultyModel.json";
import { FatigueLevel, Trail } from "../types";
import { OfflineAiModel, OfflinePrediction } from "./modelTypes";

type FeatureInput = Record<string, number | null | undefined>;

const fatigueScoreByLevel: Record<FatigueLevel, number> = {
  bajo: 1,
  medio: 2,
  alto: 3,
};

const technicalScoreByDifficulty = (difficulty?: string | null) => {
  const normalized = String(difficulty || "").toLowerCase();

  if (normalized.includes("alta")) return 4;
  if (normalized.includes("media")) return 2;
  return 1;
};

const toModel = (model: unknown) => model as OfflineAiModel;

const predictNearestCentroid = (
  model: OfflineAiModel,
  input: FeatureInput
): OfflinePrediction => {
  const distances = model.labels.reduce<Record<string, number>>((result, label) => {
    const centroid = model.centroids[label];
    const squaredDistance = model.features.reduce((sum, feature) => {
      const stat = model.statistics[feature];
      const rawValue = input[feature] ?? stat.mean;
      const normalizedValue = (rawValue - stat.mean) / stat.std;
      return sum + (normalizedValue - centroid[feature]) ** 2;
    }, 0);

    result[label] = Math.sqrt(squaredDistance);
    return result;
  }, {});

  const sorted = Object.entries(distances).sort((a, b) => a[1] - b[1]);
  const [label, distance] = sorted[0];
  const secondDistance = sorted[1]?.[1] ?? distance + 1;
  const confidence = Math.max(
    0.52,
    Math.min(0.98, secondDistance / (distance + secondDistance || 1))
  );

  return {
    label,
    confidence: Number(confidence.toFixed(2)),
    distances,
  };
};

export const predictFatigue = (input: {
  hr: number;
  speedKmh: number;
  elapsedMinutes: number;
}): OfflinePrediction => {
  const hrReservePercent = Math.max(0, Math.min(100, ((input.hr - 60) / 120) * 100));

  return predictNearestCentroid(toModel(fatigueModel), {
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

export const predictPhysioRisk = (input: {
  hr: number;
  speedKmh: number;
  elapsedMinutes: number;
  elevationGainM?: number | null;
  fatigue: FatigueLevel;
}): OfflinePrediction => {
  return predictNearestCentroid(toModel(riskModel), {
    hr: input.hr,
    speed_kmh: input.speedKmh,
    elapsed_minutes: input.elapsedMinutes,
    elevation_gain_m: input.elevationGainM ?? 0,
    fatigue_score: fatigueScoreByLevel[input.fatigue],
  });
};

export const predictRouteDifficulty = (trail: Trail): OfflinePrediction => {
  const distanceKm = trail.distance_km ?? 0;
  const technicalScore = technicalScoreByDifficulty(trail.difficulty);
  const elevationGainM = distanceKm * (technicalScore === 4 ? 82 : technicalScore === 2 ? 48 : 24);
  const avgSlopePercent = distanceKm > 0 ? Math.min(14, elevationGainM / (distanceKm * 100)) : 0;
  const maxSlopePercent = avgSlopePercent * (technicalScore === 4 ? 3.4 : technicalScore === 2 ? 2.8 : 2.2);

  return predictNearestCentroid(toModel(routeDifficultyModel), {
    distance_km: distanceKm,
    elevation_gain_m: elevationGainM,
    avg_slope_percent: avgSlopePercent,
    max_slope_percent: maxSlopePercent,
    technical_score: technicalScore,
  });
};

export const offlineAiMetadata = {
  fatigueModel: toModel(fatigueModel),
  riskModel: toModel(riskModel),
  routeDifficultyModel: toModel(routeDifficultyModel),
};
