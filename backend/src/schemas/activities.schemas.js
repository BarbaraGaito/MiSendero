const { z } = require("zod");

const createActivitySchema = z.object({
  client_session_id: z.string().min(1).max(120).nullish(),
  trail_id: z.number().int().positive().nullish(),
  started_at: z.string().datetime({ offset: true }),
  ended_at: z.string().datetime({ offset: true }).nullish(),
  distance_km: z.number().nonnegative().nullish(),
  duration_minutes: z.number().int().nonnegative().nullish(),
  completion_status: z.enum(["completed", "ended_early", "paused"]).default("completed"),
  route_progress_meters: z.number().nonnegative().nullish(),
  route_total_meters: z.number().positive().nullish(),
  ended_latitude: z.number().min(-90).max(90).nullish(),
  ended_longitude: z.number().min(-180).max(180).nullish(),
});

module.exports = { createActivitySchema };
