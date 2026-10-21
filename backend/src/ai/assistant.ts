import type { RecommendationResponse, TrailPreferences } from "./contracts";
import type { CatalogRow, Candidate } from "./catalog";
import { candidateDurationFits, compatibleCandidates, experienceFits, landscapeFits, normalize, resolveDestination, verifiedCatalog } from "./catalog";
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
      : `Te permite descubrir un entorno de ${candidate.trailTypes.join(" y ")}${landscapeFits(candidate, preferences) ? "" : "; no tiene documentados los paisajes que seleccionaste"}.`,
    duration: `Su duración registrada es ${candidate.duration}${candidate.durationScopeVerified === false ? "; el tiempo total de la ficha no está confirmado" : candidate.routeType === "out_and_back" ? " e incluye ida y vuelta" : candidate.routeType === "loop" ? " para el circuito completo" : candidate.routeType === "point_to_point" ? " para el trayecto de ida; necesitás coordinar el regreso" : " para el recorrido completo"}${preferences.duration !== "cualquiera" && candidate.durationScopeVerified !== false ? candidateDurationFits(candidate, preferences.duration) ? ", dentro del tiempo que seleccionaste" : ", fuera del rango que seleccionaste" : ""}.${candidate.durationIsEstimated ? " Es un tiempo orientativo de planificación." : ""}`,
    difficulty: `Su dificultad es ${labels[candidate.difficulty]}${preferences.difficulty !== "cualquiera" ? candidate.difficulty === preferences.difficulty ? " y coincide con la que elegiste" : ", diferente de la que elegiste" : ""}. ${experienceFits(candidate, preferences) ? `Está dentro del nivel de dificultad considerado para tu perfil ${preferences.experience || "principiante"}.` : `Supera el nivel considerado para tu perfil ${preferences.experience || "principiante"}. Es una alternativa del destino, no una indicación de que sea adecuada para tu experiencia.`}`,
  };
  const facts = `Distancia registrada: ${candidate.distanceKm} km. ${candidate.ascentM == null ? "Desnivel de ascenso no documentado." : `Desnivel de ascenso estimado: ${candidate.ascentM} m.`}`;
  return `${reasons.map((reason) => sentences[reason]).join(" ")} ${facts}`;
}
export async function recommendTrail(preferences: TrailPreferences, rows: CatalogRow[]): Promise<RecommendationResponse> {
  const empty = (status: RecommendationResponse["status"], message: string): RecommendationResponse => ({ status, message, recommendation: null });
  if (!destinationIsSafe(preferences.destination)) return empty("out_of_scope", SCOPE_MESSAGE);
  const catalog = verifiedCatalog(rows);
  const destination = normalize(preferences.destination);
  if (["santa", "san", "argentina", "patagonia", "cordillera"].includes(destination)) {
    return empty("clarification", "El destino es amplio o ambiguo. Indicá una ciudad, provincia o parque para buscar un sendero cercano.");
  }
  const resolved = resolveDestination(catalog, preferences.destination);
  if (resolved.suggestions.length) return empty("clarification", resolved.suggestions.length === 1
    ? `No encontramos ese nombre en el catálogo. ¿Quisiste decir «${resolved.suggestions[0]}»? Si es así, modificá el destino. No buscamos en otra ciudad automáticamente.`
    : `El destino puede referirse a varios lugares del catálogo: ${resolved.suggestions.join(" o ")}. Escribí el nombre completo y, si hace falta, la provincia.`);
  const candidates = compatibleCandidates(catalog, { ...preferences, destination: resolved.destination });
  if (!candidates.length) return empty("no_results", "No tenemos senderos registrados con información suficiente para ese destino. Probá escribir la ciudad, la provincia o el parque con otro nombre.");
  // Explicit catalog rules, with no learned relevance, ratings or weighted score.
  // Among equally compatible options prefer lower published difficulty, a known
  // total duration, then shorter duration/distance. Unknown ascent is never zero.
  const difficultyRank = { facil: 0, moderada: 1, dificil: 2 };
  const selected = candidates.slice().sort((a, b) =>
    difficultyRank[a.difficulty] - difficultyRank[b.difficulty] ||
    Number(a.durationScopeVerified === false) - Number(b.durationScopeVerified === false) ||
    (a.durationScopeVerified !== false && b.durationScopeVerified !== false ? a.durationMinutes - b.durationMinutes : 0) ||
    a.distanceKm - b.distanceKm || a.trailId - b.trailId)[0];
  const reasons = ["destination", "landscape", "duration", "difficulty"];
  const adjustments: string[] = [];
  if (!landscapeFits(selected, preferences)) adjustments.push(`Este sendero tiene otros paisajes: ${selected.trailTypes.join(", ")}. No tiene documentados los que seleccionaste.`);
  if (!candidateDurationFits(selected, preferences.duration)) adjustments.push(selected.durationScopeVerified === false
    ? `La ficha indica ${selected.duration}, pero el tiempo total del recorrido no está confirmado. No podemos asegurar que se ajuste al rango que elegiste.`
    : `Dura aproximadamente ${selected.duration}, fuera del rango elegido. Revisá si disponés de ese tiempo antes de elegirlo.`);
  const grades = { facil: "fácil", moderada: "moderada", dificil: "difícil" };
  const gradeRank = { facil: 0, moderada: 1, dificil: 2 };
  if (preferences.difficulty !== "cualquiera" && selected.difficulty !== preferences.difficulty) adjustments.push(`Su dificultad es ${grades[selected.difficulty]}, ${gradeRank[selected.difficulty] > gradeRank[preferences.difficulty] ? "mayor" : "menor"} que la seleccionada (${grades[preferences.difficulty]}). Revisá esa exigencia antes de elegirlo.`);
  if (!experienceFits(selected, preferences)) adjustments.push(`No hay senderos dentro del nivel considerado para tu perfil ${preferences.experience || "principiante"} en este destino. Esta alternativa es de dificultad ${grades[selected.difficulty]} y supera ese nivel; no la consideres adecuada para tu experiencia sin asesoramiento profesional.`);
  const alternative = !landscapeFits(selected, preferences) || !candidateDurationFits(selected, preferences.duration) ||
    (preferences.difficulty !== "cualquiera" && selected.difficulty !== preferences.difficulty) || !experienceFits(selected, preferences);
  return responseSchema.parse({ status: "ok", message: alternative ? "No encontramos una coincidencia exacta; te sugerimos otro sendero en el destino que elegiste" : "¡Encontramos un sendero para vos!",
    ranking: { method: "catalog", modelVersion: null },
    recommendation: { ...selected, ...(adjustments.length ? { preferenceAdjustments: adjustments } : {}), explanation: explain(selected, preferences, reasons) } });
}
