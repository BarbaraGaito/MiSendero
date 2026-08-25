const { z } = require("zod");

const createActivitySchema = z.object({
  trail_id: z.number().int().positive().nullish(),
  started_at: z.string().datetime().or(z.string().min(1)),
  ended_at: z.string().datetime().or(z.string().min(1)).nullish(),
  distance_km: z.number().nonnegative().nullish(),
  duration_minutes: z.number().int().nonnegative().nullish(),
});

module.exports = { createActivitySchema };
