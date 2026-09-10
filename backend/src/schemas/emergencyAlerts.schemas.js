const { z } = require("zod");

const createEmergencyAlertSchema = z.object({
  client_event_id: z.string().uuid().optional(),
  trail_id: z.number().int().positive().nullish(),
  latitude: z.number().min(-90).max(90).nullable(),
  longitude: z.number().min(-180).max(180).nullable(),
  device_battery_percent: z.number().int().min(0).max(100).nullish(),
  contact_name: z.string().trim().max(200).nullish(),
  contact_phone: z.string().trim().max(80).nullish(),
  message_body: z.string().trim().max(1000).nullish(),
  last_known_at: z.string().datetime().nullish(),
}).refine((value) => (value.latitude === null) === (value.longitude === null), {
  message: "Las dos coordenadas deben estar presentes o ser nulas.",
});

module.exports = { createEmergencyAlertSchema };
