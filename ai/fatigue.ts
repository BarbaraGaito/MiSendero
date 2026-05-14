import { FatigueAssessment, FatigueInput, FatigueLevel } from '../types';

export function evaluateFatigue({
  durationSec,
  heartRate,
  speedMps,
}: FatigueInput): FatigueAssessment {
  const durationMinutes = durationSec / 60;

  if (heartRate >= 165 || (heartRate > 150 && speedMps < 1.0) || (heartRate > 145 && durationMinutes > 45)) {
    return {
      level: 'alto',
      reason: 'Pulso alto con bajo desplazamiento o esfuerzo sostenido.',
      score: 3,
    };
  }

  if (heartRate >= 125 || durationMinutes > 30 || speedMps < 1.0) {
    return {
      level: 'medio',
      reason: 'Carga moderada: pulso estable o ritmo contenido.',
      score: 2,
    };
  }

  return {
    level: 'bajo',
    reason: 'Pulso controlado y buen ritmo de marcha.',
    score: 1,
  };
}

export function fatigueLevelFromScore(score: number): FatigueLevel {
  if (score >= 2.5) {
    return 'alto';
  }

  if (score >= 1.6) {
    return 'medio';
  }

  return 'bajo';
}

