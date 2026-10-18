export type TrailType = "naturaleza" | "montaña" | "cascadas" | "lagos" | "bosques" | "miradores" | "cualquiera";
export type Duration = "menos-1" | "1-2" | "2-4" | "4-6" | "mas-6" | "cualquiera";
export type Difficulty = "facil" | "moderada" | "dificil" | "cualquiera";
export type Experience = "principiante" | "intermedio" | "avanzado";
export interface TrailPreferences {
  destination: string;
  trailTypes: TrailType[];
  duration: Duration;
  difficulty: Difficulty;
  experience?: Experience;
}
export interface TrailRecommendation {
  trailId: number;
  name: string;
  location: string;
  imageUrl: string | null;
  trailTypes: TrailType[];
  difficulty: Exclude<Difficulty, "cualquiera">;
  duration: string;
  durationMinutes: number;
  routeType: "out_and_back" | "loop" | "point_to_point";
  distanceKm: number;
  description: string;
  explanation: string;
  sources: { title: string; url: string }[];
  checkedAt: string;
  ascentM?: number | null;
  terrain?: string[] | null;
  durationIsEstimated?: boolean;
}
export interface RecommendationResponse {
  status: "ok" | "no_results" | "clarification" | "out_of_scope";
  message: string;
  recommendation: TrailRecommendation | null;
  ranking?: { method: "baseline" | "supervised"; modelVersion: string | null };
}
