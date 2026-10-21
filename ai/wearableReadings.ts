import type { HealthPredictionLevel, WearableHealthPrediction } from "../types";

// Existing application alert thresholds, made explicit and shared. These are
// engineering screening rules, not validated fatigue labels or medical cutoffs.
export const wearableReadingThresholds = {
  pulseNotice: 145,
  pulseHighLoad: 165,
  pulseReview: 180,
  oxygenNotice: 94,
  oxygenReview: 90,
} as const;

export interface WearableReadingAssessment {
  level: HealthPredictionLevel;
  cardiacLoad: WearableHealthPrediction["cardiacLoad"];
  readingAlert: string;
  coverage: WearableHealthPrediction["coverage"];
  heartRateBpm: number | null;
  oxygenSaturation: number | null;
  criticalHeartRate: boolean;
  criticalOxygen: boolean;
}

export function assessWearableReadings(input: {
  heartRateBpm: number | null;
  oxygenSaturation: number | null;
}): WearableReadingAssessment | null {
  const hr = input.heartRateBpm;
  const oxygen = input.oxygenSaturation;
  const heartRateBpm = typeof hr === "number" && Number.isFinite(hr) && hr >= 30 && hr <= 240 ? hr : null;
  const oxygenSaturation = typeof oxygen === "number" && Number.isFinite(oxygen) && oxygen >= 50 && oxygen <= 100 ? oxygen : null;
  if (heartRateBpm === null && oxygenSaturation === null) return null;

  const t = wearableReadingThresholds;
  const cardiacLoad = heartRateBpm === null ? null : heartRateBpm >= t.pulseHighLoad ? "alta"
    : heartRateBpm >= t.pulseNotice ? "media" : "baja";
  const criticalHeartRate = heartRateBpm !== null && heartRateBpm >= t.pulseReview;
  const criticalOxygen = oxygenSaturation !== null && oxygenSaturation < t.oxygenReview;
  const notice = (heartRateBpm !== null && heartRateBpm >= t.pulseNotice) ||
    (oxygenSaturation !== null && oxygenSaturation < t.oxygenNotice);
  const level = criticalHeartRate || criticalOxygen ? "high" : notice ? "caution" : "normal";
  return { level, cardiacLoad, criticalHeartRate, criticalOxygen, heartRateBpm, oxygenSaturation,
    coverage: heartRateBpm === null ? "oxygen_only" : oxygenSaturation === null ? "pulse_only" : "pulse_and_oxygen",
    readingAlert: level === "high" ? "Priorizar revisión" : level === "caution" ? "Revisar lectura" : "Sin umbrales activados" };
}
