import { FatigueLevel } from "../types";

export const calculateFatigue = (
  hr: number,
  speedKmh: number,
  elapsedMinutes: number
): FatigueLevel => {

  if (hr > 150 && speedKmh < 2.5) {
    return "alto";
  }

  if (hr > 135 || (hr > 120 && elapsedMinutes > 25)) {
    return "medio";
  }

  return "bajo";
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
