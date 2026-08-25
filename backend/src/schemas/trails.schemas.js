const { z } = require("zod");

const coordinateSchema = z.tuple([z.number(), z.number()]);

const createTrailSchema = z.object({
  name: z.string().trim().min(1).max(200),
  location: z.string().trim().min(1).max(200),
  difficulty: z.string().trim().min(1).max(50),
  duration: z.string().trim().max(50).nullish(),
  distance_km: z.number().nonnegative().nullish(),
  description: z.string().max(2000).nullish(),
  image_url: z.string().url().max(500).nullish(),
  center_lat: z.number().min(-90).max(90).nullish(),
  center_lng: z.number().min(-180).max(180).nullish(),
  map_zoom: z.number().int().min(0).max(22).nullish(),
  route_coordinates: z.array(coordinateSchema).nullish(),
});

const createReportSchema = z.object({
  issue_summary: z.string().trim().min(1).max(300),
  severity: z.string().trim().min(1).max(50),
  trail_state: z.string().trim().min(1).max(50),
  cause: z.string().trim().max(100).nullish(),
  blocks_path: z.boolean().nullish(),
  details: z.string().max(1000).nullish(),
});

module.exports = { createTrailSchema, createReportSchema };
