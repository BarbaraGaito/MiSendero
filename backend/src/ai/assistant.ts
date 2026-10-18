import type { RecommendationResponse, TrailPreferences } from "./contracts";
import type { CatalogRow, Candidate } from "./catalog";
import { compatibleCandidates, normalize, verifiedCatalog } from "./catalog";
import { localRanker, Ranker } from "./model";
import { baselineScore, featuresFor } from "./features";
import { responseSchema } from "./schemas";

export const SCOPE_MESSAGE = "🥾 Soy el asistente de senderos de MiSendero. Solo puedo ayudarte a encontrar y elegir rutas de trekking. ¿Querés que busquemos un sendero para vos?";
export function destinationIsSafe(destination: string): boolean {
  const text = normalize(destination);
  // A destination is a place name, never a prompt or a free-form request. Reject mixed payloads before AI.
  return /^[\p{L}\p{M}\s,'’().-]+$/u.test(destination) && destination.split(/\s+/).length <= 14 &&
    !/\b(ignora\w*|ignor[ae]\w*|instruccion\w*|actua\w*|chat\w*|prompt|system|assistant|developer|codigo|code|mundial|politica|presidente|responde\w*|resolv\w*|matematica\w*|olvida\w*|reglas|traduc\w*|escrib\w*|explica\w*|revela\w*|secreto\w*|override|ignore|disregard|pretend|jailbreak)\b/.test(text);
}
function explain(candidate: Candidate, preferences: TrailPreferences, reasons: string[]): string {
  const wanted = preferences.trailTypes.filter((t) => t !== "cualquiera" && candidate.trailTypes.includes(t));
  const labels = { facil: "fácil", moderada: "moderada", dificil: "difícil" };
  const sentences: Record<string, string> = {
    destination: `Está en ${candidate.location}, dentro del destino que elegiste.`,
    landscape: wanted.length ? `Combina ${wanted.join(" y ")}, en línea con la experiencia que buscás.`
      : `Te permite descubrir un entorno de ${candidate.trailTypes.join(" y ")}.`,
    duration: `Su duración aproximada de ${candidate.duration} ${candidate.routeType === "out_and_back" ? "incluye ida y vuelta" : candidate.routeType === "loop" ? "cubre el circuito completo" : "corresponde al trayecto de ida; necesitás coordinar el regreso"}${preferences.duration !== "cualquiera" ? ", dentro del tiempo que seleccionaste" : ""}.${candidate.durationIsEstimated ? " El total se calculó a partir de una referencia publicada de ida." : ""}`,
    difficulty: `Su dificultad ${labels[candidate.difficulty]} respeta el límite aplicado para tu experiencia ${preferences.experience || "principiante"}${preferences.difficulty !== "cualquiera" ? " y coincide con la dificultad que elegiste" : ""}.`,
  };
  return reasons.map((reason) => sentences[reason]).join(" ");
}
export async function recommendTrail(preferences: TrailPreferences, rows: CatalogRow[], ranker: Ranker = localRanker): Promise<RecommendationResponse> {
  const empty = (status: RecommendationResponse["status"], message: string): RecommendationResponse => ({ status, message, recommendation: null });
  if (!destinationIsSafe(preferences.destination)) return empty("out_of_scope", SCOPE_MESSAGE);
  const catalog = verifiedCatalog(rows);
  const destination = normalize(preferences.destination);
  if (["santa", "san", "argentina", "patagonia", "cordillera"].includes(destination)) {
    return empty("clarification", "El destino es amplio o ambiguo. Indicá una ciudad, provincia o parque para buscar un sendero cercano.");
  }
  const candidates = compatibleCandidates(catalog, preferences);
  if (!candidates.length) return empty("no_results", "No encontramos un sendero verificado compatible con esas respuestas. Probá modificar el destino, el tipo de sendero, la duración o la dificultad.");
  const vectors = candidates.map((c) => featuresFor(preferences, c));
  let prediction = null;
  try { prediction = await ranker.predict(vectors); } catch { /* Keep the API usable if inference fails. */ }
  if (prediction && (!Array.isArray(prediction.scores) || prediction.scores.length !== candidates.length || prediction.scores.some((s) => !Number.isFinite(s)) || typeof prediction.modelVersion !== "string" || !prediction.modelVersion || prediction.modelVersion.length > 100)) prediction = null;
  const scores = prediction?.scores || vectors.map(baselineScore);
  const selected = candidates.map((candidate, i) => ({ candidate, score: scores[i] }))
    .sort((a, b) => b.score - a.score || a.candidate.trailId - b.candidate.trailId)[0].candidate;
  const reasons = ["destination", "landscape", "duration", "difficulty"];
  return responseSchema.parse({ status: "ok", message: "¡Encontramos un sendero para vos!",
    ranking: { method: prediction ? "supervised" : "baseline", modelVersion: prediction?.modelVersion || null },
    recommendation: { ...selected, explanation: explain(selected, preferences, reasons) } });
}
