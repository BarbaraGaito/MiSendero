import spec from "./featureSpec.json";
import type { Candidate } from "./catalog";
import type { TrailPreferences } from "./contracts";
export { spec as featureSpec };
export type FeatureVector = (number | null)[];
export function featuresFor(preferences: TrailPreferences, candidate: Candidate): FeatureVector {
  const desired = preferences.trailTypes.filter((t) => t !== "cualquiera");
  const center = ({ "menos-1": 30, "1-2": 90, "2-4": 180, "4-6": 300, "mas-6": 480, cualquiera: null } as const)[preferences.duration];
  // Declared preference reference points, never estimates of missing trail attributes.
  const proximity = center === null ? null : 1 / (1 + Math.abs(candidate.durationMinutes - center) / center);
  const terrain = (tag: string) => candidate.terrain == null ? null : Number(candidate.terrain.includes(tag));
  return [1, desired.length ? desired.filter((t) => candidate.trailTypes.includes(t)).length / desired.length : 1,
    proximity, candidate.durationMinutes, candidate.distanceKm,
    { facil: 0, moderada: 1, dificil: 2 }[candidate.difficulty],
    { principiante: 0, intermedio: 1, avanzado: 2 }[preferences.experience || "principiante"],
    candidate.ascentM ?? null, terrain("rocky"), terrain("steep"), terrain("boardwalk"), terrain("mud"), terrain("sand"),
    preferences.difficulty === "cualquiera" ? null : { facil: 0, moderada: 1, dificil: 2 }[preferences.difficulty]];
}
export function baselineScore(vector: FeatureVector): number {
  return spec.baselineWeights.type_match_fraction * Number(vector[1]) + spec.baselineWeights.duration_proximity * Number(vector[2] ?? 0) +
    spec.baselineWeights.effort_margin * (2 - Number(vector[5])) / 2;
}
