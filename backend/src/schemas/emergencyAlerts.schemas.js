const { z } = require("zod");

const createEmergencyAlertSchema = z.object({
  trail_id: z.number().int().positive().nullish(),
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
  status: z.enum(["sent", "pending"]).nullish(),
  device_battery_percent: z.number().int().min(0).max(100).nullish(),
  contact_name: z.string().trim().max(200).nullish(),
  contact_phone: z.string().trim().max(80).nullish(),
  message_body: z.string().trim().max(1000).nullish(),
  last_known_at: z.string().datetime().nullish(),
});

module.exports = { createEmergencyAlertSchema };
