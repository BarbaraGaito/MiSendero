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
  client_event_id: z.string().uuid().optional(),
  observed_at: z.iso.datetime().refine((value) => Date.parse(value) <= Date.now() + 300000, "La observación no puede estar en el futuro").optional(),
  issue_summary: z.string().trim().min(1).max(300),
  severity: z.string().trim().min(1).max(50),
  trail_state: z.string().trim().min(1).max(50),
  cause: z.string().trim().max(100).nullish(),
  blocks_path: z.boolean().nullish(),
  details: z.string().max(1000).nullish(),
  latitude: z.number().min(-90).max(90).nullish(),
  longitude: z.number().min(-180).max(180).nullish(),
  accuracy_meters: z.number().nonnegative().nullish(),
  route_progress_meters: z.number().nonnegative().nullish(),
  end_latitude: z.number().min(-90).max(90).nullish(),
  end_longitude: z.number().min(-180).max(180).nullish(),
  route_end_progress_meters: z.number().nonnegative().nullish(),
}).refine(value => {
  const section = [value.end_latitude, value.end_longitude, value.route_end_progress_meters];
  return section.every(item => item == null) || (section.every(item => item != null) && value.latitude != null && value.longitude != null &&
    value.route_progress_meters != null && value.route_end_progress_meters > value.route_progress_meters);
}, "Elegí inicio y fin válidos para el tramo afectado");

module.exports = { createTrailSchema, createReportSchema };
