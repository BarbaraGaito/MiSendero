import * as Network from "expo-network";
import { recommendTrail, getTrailRecommendationDestinations } from "./api";
import { getAuthSession } from "./authSession";
import type { RecommendationResponse, TrailPreferences } from "../backend/src/ai/contracts";
export type { TrailPreferences, RecommendationResponse, TrailRecommendation, TrailType, Duration, Difficulty, Experience } from "../backend/src/ai/contracts";

export async function getCoveredDestinations(): Promise<string[]> {
  const network = await Network.getNetworkStateAsync().catch(() => null);
  if (network?.isConnected === false || network?.isInternetReachable === false) return [];
  const session = await getAuthSession();
  if (!session) return [];
  const result = await getTrailRecommendationDestinations(session.token);
  if (!result || !Array.isArray(result.destinations) || result.destinations.length > 10000 ||
    !result.destinations.every((d) => typeof d === "string" && d.trim().length >= 2 && d.length <= 200)) throw new Error("El catálogo de destinos no es válido.");
  return [...new Set(result.destinations)];
}

const isRecord = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
const isText = (value: unknown, limit: number) => typeof value === "string" && value.length > 0 && value.length <= limit;
const isHttps = (value: unknown) => {
  try { return typeof value === "string" && new URL(value).protocol === "https:"; } catch { return false; }
};
function validRecommendation(value: unknown): boolean {
  if (!isRecord(value)) return false;
  return Number.isSafeInteger(value.trailId) && Number(value.trailId) > 0 && isText(value.name, 200) && isText(value.location, 200) &&
    (value.imageUrl === null || isHttps(value.imageUrl)) &&
    Array.isArray(value.trailTypes) && value.trailTypes.length > 0 && value.trailTypes.every((t: unknown) => typeof t === "string" && ["naturaleza", "montaña", "cascadas", "lagos", "bosques", "miradores"].includes(t)) &&
    typeof value.difficulty === "string" && ["facil", "moderada", "dificil"].includes(value.difficulty) &&
    isText(value.duration, 100) && typeof value.durationMinutes === "number" && Number.isFinite(value.durationMinutes) && value.durationMinutes > 0 &&
    typeof value.routeType === "string" && ["out_and_back", "loop", "point_to_point"].includes(value.routeType) &&
    typeof value.distanceKm === "number" && Number.isFinite(value.distanceKm) && value.distanceKm > 0 &&
    isText(value.description, 2000) && isText(value.explanation, 1500) &&
    Array.isArray(value.sources) && value.sources.length > 0 && value.sources.every((s: unknown) => isRecord(s) && isText(s.title, 200) && isHttps(s.url)) &&
    typeof value.checkedAt === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value.checkedAt);
}

export async function findRecommendedTrail(preferences: TrailPreferences): Promise<RecommendationResponse> {
  const network = await Network.getNetworkStateAsync().catch(() => null);
  if (network?.isConnected === false || network?.isInternetReachable === false) {
    throw new Error("Necesitás Internet para generar una nueva recomendación. Tus mapas descargados siguen disponibles sin conexión.");
  }
  const session = await getAuthSession();
  if (!session) throw new Error("Iniciá sesión para descubrir tu sendero.");
  let result: RecommendationResponse;
  try {
    result = await recommendTrail(preferences, session.token);
  } catch (error) {
    if (error && typeof error === "object" && "status" in error && error.status === 404) {
      throw new Error("No pudimos acceder al servicio de recomendaciones. Intentá nuevamente más tarde.");
    }
    throw error;
  }
  // Defensive contract check before navigation/rendering; the server performs full Zod validation.
  if (!result || !["ok", "no_results", "clarification", "out_of_scope"].includes(result.status) ||
      typeof result.message !== "string" || result.message.length > 1500 ||
      (result.status === "ok" ? !validRecommendation(result.recommendation)
        : result.recommendation !== null)) {
    throw new Error("La recomendación recibida no es válida. Intentá nuevamente.");
  }
  return result;
}
