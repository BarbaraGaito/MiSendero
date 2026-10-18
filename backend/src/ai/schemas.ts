import { z } from "zod";

export const trailTypeSchema = z.enum(["naturaleza", "montaña", "cascadas", "lagos", "bosques", "miradores", "cualquiera"]);
export const preferencesSchema = z.object({
  destination: z.string().trim().min(2).max(120),
  trailTypes: z.array(trailTypeSchema).min(1).max(7).refine((v) => new Set(v).size === v.length)
    .refine((v) => !v.includes("cualquiera") || v.length === 1),
  duration: z.enum(["menos-1", "1-2", "2-4", "4-6", "mas-6", "cualquiera"]),
  difficulty: z.enum(["facil", "moderada", "dificil", "cualquiera"]),
  experience: z.enum(["principiante", "intermedio", "avanzado"]).default("principiante"),
}).strict();

export const recommendationSchema = z.object({
  trailId: z.number().int().positive(), name: z.string().min(1).max(200),
  location: z.string().min(1).max(200), imageUrl: z.url().nullable(),
  trailTypes: z.array(trailTypeSchema).min(1), difficulty: z.enum(["facil", "moderada", "dificil"]),
  duration: z.string().min(1), durationMinutes: z.number().positive(),
  routeType: z.enum(["out_and_back", "loop", "point_to_point", "unknown"]),
  distanceKm: z.number().positive(), description: z.string().min(1).max(2000),
  explanation: z.string().min(1).max(1500),
  sources: z.array(z.object({ title: z.string(), url: z.url() }).strict()),
  checkedAt: z.iso.date().nullable(),
  catalogVerification: z.enum(["verified", "catalog_only"]).optional(),
  durationScopeVerified: z.boolean().optional(),
  dataWarnings: z.array(z.string().min(1).max(300)).min(1).max(3).optional(),
  ascentM: z.number().nonnegative().nullable().optional(),
  terrain: z.array(z.enum(["rocky", "steep", "boardwalk", "mud", "sand"])).nullable().optional(),
  durationIsEstimated: z.boolean().optional(),
  preferenceAdjustments: z.array(z.string().min(1).max(300)).min(1).max(4).optional(),
}).strict().refine(v => (v.sources.length > 0 && v.checkedAt !== null) ||
  (v.catalogVerification === "catalog_only" && v.dataWarnings?.length && v.durationScopeVerified === false));
export const responseSchema = z.object({
  status: z.enum(["ok", "no_results", "clarification", "out_of_scope"]),
  message: z.string(), recommendation: recommendationSchema.nullable(),
  ranking: z.object({ method: z.enum(["baseline", "supervised"]), modelVersion: z.string().nullable() }).strict().optional(),
}).strict().refine((v) => (v.status === "ok") === (v.recommendation !== null));
