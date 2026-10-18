import type { Difficulty, Duration, TrailPreferences, TrailRecommendation, TrailType } from "./contracts";

export const normalize = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
export interface CatalogRow {
  id: number; name: string; location: string; difficulty: string; duration: string;
  distance_km: number | string; description: string; image_url: string | null;
  verified_ascent_m?: number | null;
  provenance: { checked_at: string; route_type: string; duration_basis: string;
    sources: { title: string; url: string }[];
    recommendation?: { trail_types?: TrailType[]; terrain?: string[]; source_url?: string };
  } | null;
}
export type Candidate = Omit<TrailRecommendation, "explanation">;
const trustedHosts = new Set(["www.argentina.gob.ar", "www.barilocheturismo.gob.ar", "refugiofreybariloche.com",
  "larutanatural.gob.ar", "turismocapilla.gob.ar", "www.ambiente.gba.gob.ar", "www.turismoelbolson.gob.ar",
  "saltaciudad.travel", "www.turismo.jujuy.gob.ar", "www.tucumanturismo.gob.ar", "turismo.neuquen.gob.ar",
  "villapehuenia.gob.ar", "villademerlo.tur.ar", "www.esquel.tur.ar", "misiones.tur.ar",
  "barilochetrekking.com", "patagonia.gob.ar"]);
const safeUrl = (value: unknown, source = false): value is string => {
  try { const url = new URL(String(value)); return url.protocol === "https:" && !url.username && !url.password &&
    (!source || trustedHosts.has(url.hostname)); } catch { return false; }
};
export function durationMinutes(value: string): number | null {
  // Keep the source interval in duration; use the conservative upper endpoint for ranking.
  const range = value.trim().match(/^(\d+)\s*[-–]\s*(\d+)\s*h$/i);
  if (range) return Number(range[1]) > 0 && Number(range[2]) >= Number(range[1]) ? Number(range[2]) * 60 : null;
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
    if (!p || !/^\d{4}-\d{2}-\d{2}$/.test(p.checked_at) || !Number.isFinite(Date.parse(p.checked_at)) || !Array.isArray(p.sources) || typeof row.difficulty !== "string") return [];
    const sources = p.sources.filter((s) => s && typeof s.title === "string" && safeUrl(s.url, true));
    const minutes = typeof row.duration === "string" ? durationMinutes(row.duration) : null;
    const difficulty: Difficulty | undefined = ({ baja: "facil", media: "moderada", alta: "dificil" } as const)[normalize(row.difficulty) as "baja" | "media" | "alta"];
    // An out-and-back itinerary must explicitly document a total duration.
    const durationKnown = p.route_type === "out_and_back"
      ? ["official_round_trip", "round_trip_from_official_one_way"].includes(p.duration_basis)
      : p.route_type === "point_to_point" ? p.duration_basis === "official_one_way"
        : p.route_type === "loop" && p.duration_basis === "official_circuit";
    if (!sources.length || !minutes || !durationKnown || !difficulty || !Number.isFinite(Number(row.distance_km)) || Number(row.distance_km) <= 0 || !row.description) return [];
    // Only positive descriptions are used: variants explicitly excluded by the catalog are not facets.
    const text = normalize(`${row.name} ${row.description.split(/\bno\b/i)[0]}`);
    const trailTypes: TrailType[] = ["naturaleza"];
    if (/montan|ascenso|cerro|cumbre|crater|volcan|fitz roy/.test(text)) trailTypes.push("montaña");
    if (/cascada|salto|arrechea/.test(text)) trailTypes.push("cascadas");
    if (/laguna|lago\b/.test(text)) trailTypes.push("lagos");
    if (/bosque|selva|yunga|caldenes/.test(text)) trailTypes.push("bosques");
    if (/mirador|balcon|panoramic/.test(text)) trailTypes.push("miradores");
    const metadata = p.recommendation;
    const documented = metadata && sources.some((s) => s.url === metadata.source_url);
    if (documented && Array.isArray(metadata.trail_types) && metadata.trail_types.length && metadata.trail_types.every((t) => ["naturaleza", "montaña", "cascadas", "lagos", "bosques", "miradores"].includes(t))) {
      trailTypes.splice(0, trailTypes.length, ...new Set(metadata.trail_types));
    }
    const terrain = documented && Array.isArray(metadata.terrain) && metadata.terrain.every((t) => ["rocky", "steep", "boardwalk", "mud", "sand"].includes(t)) ? metadata.terrain : null;
    return [{ trailId: row.id, name: row.name, location: row.location,
      imageUrl: safeUrl(row.image_url) ? row.image_url : null, trailTypes, difficulty,
      duration: row.duration, durationMinutes: minutes, routeType: p.route_type as Candidate["routeType"],
      distanceKm: Number(row.distance_km), description: row.description, sources, checkedAt: p.checked_at,
      durationIsEstimated: p.duration_basis === "round_trip_from_official_one_way",
      ascentM: typeof row.verified_ascent_m === "number" && Number.isFinite(row.verified_ascent_m) && row.verified_ascent_m >= 0 ? row.verified_ascent_m : null, terrain }];
  });
}

// Local aliases are deliberately limited to documented catalog areas. No guessed geocoding.
const aliases: Record<string, string[]> = {
  "bariloche": ["san carlos de bariloche", "bariloche"],
  "el chalten": ["el chalten", "chalten"], "ushuaia": ["ushuaia"],
  "cordoba": ["cordoba"], "mendoza": ["mendoza", "aconcagua"],
  "san martin de los andes": ["san martin de los andes"],
};
export function destinationMatches(candidate: Candidate, destination: string): boolean {
  const parts = normalize(destination).split(",").map((part) => part.trim()).filter((part) => part && part !== "argentina");
  destination = parts[0] || "";
  if (!destination || !parts.slice(1).every((part) => normalize(candidate.location).includes(part))) return false;
  const text = normalize(`${candidate.location} ${candidate.name}`);
  const key = Object.keys(aliases).find((k) => aliases[k].includes(destination));
  if (key === "bariloche") return /refugio frey|bariloche/.test(text);
  if (key === "el chalten") return /el chalten/.test(text);
  if (key === "ushuaia") return /tierra del fuego|tierra mayor/.test(text);
  return (` ${text.replace(/[^a-z0-9]+/g, " ")} `).includes(` ${key || destination} `);
}
export function compatibleCandidates(catalog: Candidate[], preferences: TrailPreferences): Candidate[] {
  const desired = preferences.trailTypes.filter((type) => type !== "cualquiera");
  return catalog.filter((c) => destinationMatches(c, normalize(preferences.destination)) &&
    (!desired.length || desired.some((type) => c.trailTypes.includes(type))) &&
    durationFits(c.durationMinutes, preferences.duration) &&
    // A published 3-4h circuit must not match a 4-6h request just because its upper bound is 4h.
    durationFits(Number(c.duration.match(/^(\d+)\s*[-–]/)?.[1] || c.durationMinutes / 60) * 60, preferences.duration) &&
    experienceFits(c, preferences) &&
    (preferences.difficulty === "cualquiera" || c.difficulty === preferences.difficulty))
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
    const labels: Record<string, string> = { bariloche: "Bariloche", "el chalten": "El Chaltén", ushuaia: "Ushuaia", cordoba: "Córdoba", mendoza: "Mendoza", "san martin de los andes": "San Martín de los Andes" };
    values.add(labels[key]);
  }
  return [...values].filter((v) => v.length <= 120).sort((a, b) => a.localeCompare(b, "es"));
}
