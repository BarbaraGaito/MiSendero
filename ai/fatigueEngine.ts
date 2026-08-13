import { FatigueLevel } from "../types";
import { predictFatigueLevel } from "./inferenceEngine";

export const calculateFatigue = (
  hr: number,
  speedKmh: number,
  elapsedMinutes: number
): FatigueLevel => {
  return predictFatigueLevel({ hr, speedKmh, elapsedMinutes });
};

export const fatigueToScore = (fatigue: FatigueLevel) => {
  if (fatigue === "alto") return 3;
  if (fatigue === "medio") return 2;
  return 1;
};

export const scoreToFatigue = (score: number): FatigueLevel => {
  if (score >= 2.5) return "alto";
  if (score >= 1.5) return "medio";
  return "bajo";
};
