const express = require("express");
const { query } = require("../db");
const { requireAuth } = require("../middleware/requireAuth");
const { validateBody } = require("../middleware/validate");
const { createEmergencyAlertSchema } = require("../schemas/emergencyAlerts.schemas");

const router = express.Router();

router.get("/", requireAuth, async (req, res, next) => {
  try {
    const { rows } = await query(
      `SELECT * FROM emergency_alerts WHERE user_id = $1 ORDER BY created_at DESC LIMIT 50`,
      [req.userId]
    );
    res.json(rows);
  } catch (error) {
    next(error);
  }
});

router.post("/", requireAuth, validateBody(createEmergencyAlertSchema), async (req, res, next) => {
  try {
    const {
      trail_id,
      latitude,
      longitude,
      status,
      device_battery_percent,
      contact_name,
      contact_phone,
      message_body,
      last_known_at,
    } = req.body;

    const { rows } = await query(
      `
        INSERT INTO emergency_alerts (
          user_id,
          trail_id,
          latitude,
          longitude,
          status,
          device_battery_percent,
          contact_name,
          contact_phone,
          message_body,
          last_known_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING *
      `,
      [
        req.userId,
        trail_id ?? null,
        latitude,
        longitude,
        status ?? "sent",
        device_battery_percent ?? null,
        contact_name ?? null,
        contact_phone ?? null,
        message_body ?? null,
        last_known_at ?? null,
      ]
    );

    res.status(201).json(rows[0]);
  } catch (error) {
    next(error);
  }
});

module.exports = router;
