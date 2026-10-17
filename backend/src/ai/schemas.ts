import { z } from "zod";

export const trailTypeSchema = z.enum(["naturaleza", "montaña", "cascadas", "lagos", "bosques", "miradores", "cualquiera"]);
export const preferencesSchema = z.object({
  destination: z.string().trim().min(2).max(120),
  trailTypes: z.array(trailTypeSchema).min(1).max(7).refine((v) => new Set(v).size === v.length)
    .refine((v) => !v.includes("cualquiera") || v.length === 1),
  duration: z.enum(["menos-1", "1-2", "2-4", "4-6", "mas-6", "cualquiera"]),
  difficulty: z.enum(["facil", "moderada", "dificil", "cualquiera"]),
}).strict();

export const reasonSchema = z.enum(["destination", "landscape", "duration", "difficulty"]);
export const decisionSchema = z.object({
  trailId: z.number().int().positive(),
  reasons: z.array(reasonSchema).min(2).max(4).refine((v) => new Set(v).size === v.length),
}).strict();

export const recommendationSchema = z.object({
  trailId: z.number().int().positive(), name: z.string().min(1).max(200),
  location: z.string().min(1).max(200), imageUrl: z.url().nullable(),
  trailTypes: z.array(trailTypeSchema).min(1), difficulty: z.enum(["facil", "moderada", "dificil"]),
  duration: z.string().min(1), durationMinutes: z.number().positive(),
  routeType: z.enum(["out_and_back", "loop", "point_to_point"]),
  distanceKm: z.number().positive(), description: z.string().min(1).max(2000),
  explanation: z.string().min(1).max(1500),
  sources: z.array(z.object({ title: z.string(), url: z.url() }).strict()).min(1),
  checkedAt: z.iso.date(),
}).strict();
export const responseSchema = z.object({
  status: z.enum(["ok", "no_results", "clarification", "out_of_scope"]),
  message: z.string(), recommendation: recommendationSchema.nullable(),
}).strict().refine((v) => (v.status === "ok") === (v.recommendation !== null));
