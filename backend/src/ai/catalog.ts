import type { Difficulty, Duration, TrailPreferences, TrailRecommendation, TrailType } from "./contracts";

export const normalize = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
export interface CatalogRow {
  id: number; name: string; location: string; difficulty: string; duration: string;
  distance_km: number | string; description: string; image_url: string | null;
  verified_ascent_m?: number | null;
  provenance: { checked_at: string; route_type: string; duration_basis: string;
    sources: { title: string; url: string }[];
    recommendation?: { trail_types?: TrailType[]; terrain?: string[]; source_url?: string };
    review?: { confirmed_fields: string[]; unconfirmed_fields: string[]; finding: string; warning: string | null };
  } | null;
}
export type Candidate = Omit<TrailRecommendation, "explanation">;
const trustedHosts = new Set(["www.argentina.gob.ar", "www.barilocheturismo.gob.ar", "refugiofreybariloche.com",
  "larutanatural.gob.ar", "turismocapilla.gob.ar", "www.ambiente.gba.gob.ar", "www.turismoelbolson.gob.ar",
  "saltaciudad.travel", "www.turismo.jujuy.gob.ar", "www.tucumanturismo.gob.ar", "turismo.neuquen.gob.ar",
  "villapehuenia.gob.ar", "villademerlo.tur.ar", "www.esquel.tur.ar", "misiones.tur.ar",
  "barilochetrekking.com", "patagonia.gob.ar", "informacionoficial.mendoza.gob.ar",
  "experiencias.turismosalta.gov.ar", "fundacionfunke.org.ar", "www.ischigualasto.gob.ar"]);
const safeUrl = (value: unknown, source = false): value is string => {
  try { const url = new URL(String(value)); return url.protocol === "https:" && !url.username && !url.password &&
    (!source || trustedHosts.has(url.hostname)); } catch { return false; }
};
export function durationMinutes(value: string): number | null {
  return durationInterval(value)?.max ?? null;
}
function durationInterval(value: string): { min: number; max: number } | null {
  const text = value.trim();
  const sameUnit = text.match(/^(\d+)\s*(?:-|–|a)\s*(\d+)\s*(h|min)$/i);
  if (sameUnit) {
    const factor = sameUnit[3].toLowerCase() === "h" ? 60 : 1;
    const min = Number(sameUnit[1]) * factor, max = Number(sameUnit[2]) * factor;
    return min > 0 && max >= min ? { min, max } : null;
  }
  const range = text.replace(/\s+/g, " ").split(/ (?:a|-|–) /i);
  if (range.length === 2) {
    const min = singleDurationMinutes(range[0]), max = singleDurationMinutes(range[1]);
    return min != null && max != null && min > 0 && max >= min ? { min, max } : null;
  }
  const minutes = singleDurationMinutes(text);
  return minutes != null && minutes > 0 ? { min: minutes, max: minutes } : null;
}
function singleDurationMinutes(value: string): number | null {
  const match = value.trim().match(/^(\d+)\s*h(?:\s+(\d+)\s*min)?$/i);
  const minutes = value.trim().match(/^(\d+)\s*min$/i);
  return match ? Number(match[1]) * 60 + Number(match[2] || 0) : minutes ? Number(minutes[1]) : null;
}
export function durationFits(minutes: number, preference: Duration): boolean {
  switch (preference) {
    case "menos-1": return minutes < 60;
    case "1-2": return minutes >= 60 && minutes <= 120;
    case "2-4": return minutes >= 120 && minutes <= 240;
    case "4-6": return minutes >= 240 && minutes <= 360;
    case "mas-6": return minutes > 360;
    default: return true;
  }
}
export function verifiedCatalog(rows: CatalogRow[]): Candidate[] {
  return rows.flatMap((row) => {
    const p = row.provenance;
    if (!Number.isSafeInteger(row.id) || row.id <= 0 || typeof row.name !== "string" || !row.name.trim() || row.name.length > 200 ||
      typeof row.location !== "string" || !row.location.trim() || row.location.length > 200 || typeof row.description !== "string" || !row.description || row.description.length > 2000) return [];
    if (typeof row.difficulty !== "string") return [];
    if (p && (!/^\d{4}-\d{2}-\d{2}$/.test(p.checked_at) || !Number.isFinite(Date.parse(p.checked_at)) || !Array.isArray(p.sources))) return [];
    const sources = p?.sources.filter((s) => s && typeof s.title === "string" && safeUrl(s.url, true)) || [];
    const minutes = typeof row.duration === "string" ? durationMinutes(row.duration) : null;
    const difficulty: Difficulty | undefined = ({ baja: "facil", media: "moderada", alta: "dificil" } as const)[normalize(row.difficulty) as "baja" | "media" | "alta"];
    // An out-and-back itinerary must explicitly document a total duration.
    const durationKnown = p?.duration_basis === "official_total_itinerary" || (p?.route_type === "out_and_back"
      ? ["official_round_trip", "round_trip_from_official_one_way", "planning_estimate"].includes(p.duration_basis)
      : p?.route_type === "point_to_point" ? p.duration_basis === "official_one_way"
        : p?.route_type === "loop" && p.duration_basis === "official_circuit");
    // Legacy catalog records remain usable without pretending their provenance or time scope was verified.
    // A malformed supplied provenance is still rejected; missing facts are never generated.
    if ((p && !sources.length) || !minutes || !difficulty || !Number.isFinite(Number(row.distance_km)) || Number(row.distance_km) <= 0 || !row.description) return [];
    const routeType = p && ["out_and_back", "loop", "point_to_point"].includes(p.route_type) ? p.route_type as Candidate["routeType"] : "unknown";
    const dataWarnings: string[] = [];
    if (p?.review?.warning) dataWarnings.push(p.review.warning);
    if (!p) dataWarnings.push("Esta ficha proviene del catálogo de MiSendero y todavía no tiene una fuente externa ni una fecha de verificación documentadas.");
    if (!durationKnown && !p?.review?.warning) dataWarnings.push("La duración está registrada en la ficha, pero no está documentado si incluye ida y vuelta. Confirmá el tiempo total antes de planificar la salida.");
    else if (p?.duration_basis === "planning_estimate") dataWarnings.push("La duración de esta ficha es una estimación de planificación, no un tiempo oficial publicado.");
    // Only positive descriptions are used: variants explicitly excluded by the catalog are not facets.
    const text = normalize(`${row.name} ${row.description.split(/\bno\b/i)[0]}`);
    const trailTypes: TrailType[] = ["naturaleza"];
    if (/montan|ascenso|cerro|cumbre|crater|volcan|fitz roy/.test(text)) trailTypes.push("montaña");
    if (/cascada|salto|arrechea/.test(text)) trailTypes.push("cascadas");
    if (/laguna|lago\b/.test(text)) trailTypes.push("lagos");
    if (/bosque|selva|yunga|caldenes/.test(text)) trailTypes.push("bosques");
    if (/mirador|balcon|panoramic/.test(text)) trailTypes.push("miradores");
    const metadata = p?.recommendation;
    const documented = metadata && sources.some((s) => s.url === metadata.source_url);
    if (documented && Array.isArray(metadata.trail_types) && metadata.trail_types.length && metadata.trail_types.every((t) => ["naturaleza", "montaña", "cascadas", "lagos", "bosques", "miradores"].includes(t))) {
      trailTypes.splice(0, trailTypes.length, ...new Set(metadata.trail_types));
    }
    const terrain = documented && Array.isArray(metadata.terrain) && metadata.terrain.every((t) => ["rocky", "steep", "boardwalk", "mud", "sand"].includes(t)) ? metadata.terrain : null;
    return [{ trailId: row.id, name: row.name, location: row.location,
      imageUrl: safeUrl(row.image_url) ? row.image_url : null, trailTypes, difficulty,
      duration: row.duration, durationMinutes: minutes, routeType,
      distanceKm: Number(row.distance_km), description: row.description, sources, checkedAt: p?.checked_at ?? null,
      catalogVerification: p ? p.review?.unconfirmed_fields.length ? "partial" : "verified" : "catalog_only", durationScopeVerified: Boolean(durationKnown),
      ...(dataWarnings.length ? { dataWarnings } : {}),
      durationIsEstimated: ["round_trip_from_official_one_way", "planning_estimate"].includes(p?.duration_basis || ""),
      ascentM: typeof row.verified_ascent_m === "number" && Number.isFinite(row.verified_ascent_m) && row.verified_ascent_m >= 0 ? row.verified_ascent_m : null, terrain }];
  });
}

// Local aliases are deliberately limited to documented catalog areas. No guessed geocoding.
const aliases: Record<string, string[]> = {
  "bariloche": ["san carlos de bariloche", "san carlos bariloche", "bariloche"],
  "el chalten": ["el chalten", "chalten"], "ushuaia": ["ushuaia"],
  "cordoba": ["cordoba"], "mendoza": ["mendoza"],
  "san martin de los andes": ["san martin de los andes"],
  "buenos aires": ["buenos aires", "bs as"],
};
const placeText = (value: string) => normalize(value).replace(/[^a-z0-9]+/g, " ").trim().replace(/\s+/g, " ")
  .replace(/^(?:(?:provincia|ciudad|localidad) (?:de |del )?|parque (?:nacional |provincial )?|p n |pn )/, "");
const placeWords = (value: string) => placeText(value).split(" ").filter((w) => !["de", "del", "la", "las", "el", "los", "y", "argentina"].includes(w));
const containsPlace = (text: string, place: string) => {
  const words = placeWords(place);
  return words.length > 0 && (` ${placeWords(text).join(" ")} `).includes(` ${words.join(" ")} `);
};
export function destinationMatches(candidate: Candidate, destination: string): boolean {
  const parts = normalize(destination).split(",").map((part) => part.trim()).filter((part) => part && part !== "argentina");
  destination = parts[0] || "";
  if (!destination || !parts.slice(1).every((part) => containsPlace(candidate.location, part))) return false;
  const text = normalize(`${candidate.location} ${candidate.name}`);
  const head = placeText(destination);
  // Recognize documented aliases even when a province is typed without commas.
  const alias = Object.entries(aliases).flatMap(([key, values]) => values.map((value) => ({ key, value })))
    .sort((a, b) => b.value.length - a.value.length)
    .find(({ value }) => (` ${head} `).includes(` ${value} `));
  // An explicitly requested city must be documented as a locality, not merely a province.
  // The exceptions below have reviewed city aliases for park-based catalog entries.
  if (/^(ciudad|localidad) (de|del) /.test(normalize(destination)) &&
    !["bariloche", "el chalten", "ushuaia", "san martin de los andes"].includes(alias?.key || "")) {
    return candidate.location.split(",").slice(0, -1).some((part) => placeText(part) === head);
  }
  if (alias) {
    const qualifier = head.replace(alias.value, " ").trim();
    if (qualifier && !containsPlace(candidate.location, qualifier)) return false;
    if (alias.key === "bariloche") return containsPlace(candidate.location, "bariloche") ||
      (/refugio frey/.test(normalize(candidate.name)) && containsPlace(candidate.location, "nahuel huapi") && containsPlace(candidate.location, "rio negro"));
    if (alias.key === "el chalten") return /el chalten/.test(text) && containsPlace(candidate.location, "santa cruz");
    if (alias.key === "ushuaia") return containsPlace(candidate.location, "ushuaia") ||
      /parque nacional tierra del fuego|valle de tierra mayor/.test(normalize(candidate.location));
    return containsPlace(candidate.location, alias.key);
  }
  return containsPlace(text, head);
}

// A single insertion, deletion, replacement or adjacent transposition, only for long names.
// Resolve against the verified catalog as a whole; never choose a place per trail.
function onePlaceEdit(a: string, b: string): boolean {
  if (Math.min(a.length, b.length) < 5 || Math.abs(a.length - b.length) > 1 || a === b) return false;
  let i = 0;
  while (i < Math.min(a.length, b.length) && a[i] === b[i]) i++;
  if (a.length === b.length) return a.slice(i + 1) === b.slice(i + 1) ||
    (a[i] === b[i + 1] && a[i + 1] === b[i] && a.slice(i + 2) === b.slice(i + 2));
  return a.length > b.length ? a.slice(i + 1) === b.slice(i) : a.slice(i) === b.slice(i + 1);
}
export function resolveDestination(catalog: Candidate[], destination: string): { destination: string; suggestions: string[] } {
  const parts = destination.split(",");
  const head = placeText(parts[0]);
  if (catalog.some((c) => destinationMatches(c, destination))) {
    return { destination, suggestions: [] };
  }
  const known = catalogDestinations(catalog);
  if (known.some((p) => placeText(p) === head)) {
    return { destination, suggestions: [] };
  }
  const cityPrefix = parts[0].match(/^\s*(?:ciudad|localidad)\s+(?:de|del)\s+/iu)?.[0] || "";
  const alternatives = known.filter((p) => !p.includes(",") && onePlaceEdit(head, placeText(p)))
    .map((p) => ({ label: p, destination: [cityPrefix + p, ...parts.slice(1)].join(",") }))
    .filter((p) => catalog.some((c) => destinationMatches(c, p.destination)));
  // Different spellings resolving to the same set of trails are one interpretation.
  const unique = new Map<string, typeof alternatives[number]>();
  for (const option of alternatives) {
    const key = catalog.filter((c) => destinationMatches(c, option.destination)).map((c) => c.trailId).sort((a, b) => a - b).join(",");
    if (!unique.has(key)) unique.set(key, option);
  }
  // A real city outside the catalog can differ by one letter from a covered city.
  // Suggest spellings, but require the user to edit the destination before recommending.
  return { destination, suggestions: [...unique.values()].map((p) => p.label).slice(0, 3) };
}

export function candidateDurationFits(candidate: Candidate, duration: Duration): boolean {
  if (duration === "cualquiera") return true;
  if (candidate.durationScopeVerified === false) return false;
  const start = durationInterval(candidate.duration)?.min ?? candidate.durationMinutes;
  return durationFits(candidate.durationMinutes, duration) && durationFits(start, duration);
}
export function landscapeFits(candidate: Candidate, preferences: TrailPreferences): boolean {
  const desired = preferences.trailTypes.filter((type) => type !== "cualquiera");
  return !desired.length || desired.some((type) => candidate.trailTypes.includes(type));
}
const difficultyRank = { facil: 0, moderada: 1, dificil: 2 };
export function compatibleCandidates(catalog: Candidate[], preferences: TrailPreferences): Candidate[] {
  const desired = preferences.trailTypes.filter((type) => type !== "cualquiera");
  const resolved = resolveDestination(catalog, preferences.destination);
  if (resolved.suggestions.length) return [];
  const local = catalog.filter((c) => destinationMatches(c, resolved.destination));
  if (!local.length) return [];
  // Geography is mandatory. All other answers rank actual local alternatives rather than emptying the pool.
  // Prefer the saved experience; if none fits, disclose the least demanding local option instead of claiming suitability.
  const experienced = local.filter((c) => experienceFits(c, preferences));
  const lowestDifficulty = Math.min(...local.map(c => difficultyRank[c.difficulty]));
  const pool = experienced.length ? experienced : local.filter(c => difficultyRank[c.difficulty] === lowestDifficulty);
  // Essential trip constraints precede scenery: total duration, difficulty, landscape.
  // These are explicit product rules, not learned relevance or scientific thresholds.
  const tier = (c: Candidate) => Number(!candidateDurationFits(c, preferences.duration)) * 4 +
    Number(preferences.difficulty !== "cualquiera" && c.difficulty !== preferences.difficulty) * 2 +
    Number(!landscapeFits(c, preferences));
  const bestTier = Math.min(...pool.map(tier));
  return pool.filter((c) => tier(c) === bestTier)
    .sort((a, b) => desired.filter((t) => b.trailTypes.includes(t)).length - desired.filter((t) => a.trailTypes.includes(t)).length || a.trailId - b.trailId);
}

export function experienceFits(candidate: Candidate, preferences: TrailPreferences): boolean {
  const level = preferences.experience || "principiante";
  return level === "avanzado" || (level === "intermedio" ? candidate.difficulty !== "dificil" : candidate.difficulty === "facil");
}

export function catalogDestinations(catalog: Candidate[]): string[] {
  const values = new Set<string>();
  for (const c of catalog) {
    values.add(c.location);
    c.location.split(",").map((part) => part.trim()).filter((part) => part.length >= 2).forEach((part) => values.add(part));
  }
  for (const key of Object.keys(aliases)) if (catalog.some((c) => destinationMatches(c, key))) {
    const labels: Record<string, string> = { bariloche: "Bariloche", "el chalten": "El Chaltén", ushuaia: "Ushuaia", cordoba: "Córdoba", mendoza: "Mendoza", "san martin de los andes": "San Martín de los Andes", "buenos aires": "Buenos Aires" };
    values.add(labels[key]);
  }
  return [...values].filter((v) => v.length <= 120).sort((a, b) => a.localeCompare(b, "es"));
}
