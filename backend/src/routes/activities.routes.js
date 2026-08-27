const express = require("express");
const { query } = require("../db");
const { requireAuth } = require("../middleware/requireAuth");
const { validateBody } = require("../middleware/validate");
const { createActivitySchema } = require("../schemas/activities.schemas");

const router = express.Router();

router.get("/", requireAuth, async (req, res, next) => {
  try {
    const { rows } = await query(
      `SELECT * FROM activities WHERE user_id = $1 ORDER BY created_at DESC LIMIT 50`,
      [req.userId]
    );
    res.json(rows);
  } catch (error) {
    next(error);
  }
});

router.post("/", requireAuth, validateBody(createActivitySchema), async (req, res, next) => {
  try {
    const {
      client_session_id,
      trail_id,
      started_at,
      ended_at,
      distance_km,
      duration_minutes,
      completion_status,
      route_progress_meters,
      route_total_meters,
      ended_latitude,
      ended_longitude,
    } = req.body;

    const { rows } = await query(
      `
        INSERT INTO activities (
          user_id,
          client_session_id,
          trail_id,
          started_at,
          ended_at,
          distance_km,
          duration_minutes,
          completion_status,
          route_progress_meters,
          route_total_meters,
          ended_latitude,
          ended_longitude
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        ON CONFLICT (user_id, client_session_id)
        DO UPDATE SET
          trail_id = EXCLUDED.trail_id,
          started_at = EXCLUDED.started_at,
          ended_at = EXCLUDED.ended_at,
          distance_km = EXCLUDED.distance_km,
          duration_minutes = EXCLUDED.duration_minutes,
          completion_status = EXCLUDED.completion_status,
          route_progress_meters = EXCLUDED.route_progress_meters,
          route_total_meters = EXCLUDED.route_total_meters,
          ended_latitude = EXCLUDED.ended_latitude,
          ended_longitude = EXCLUDED.ended_longitude
        RETURNING *
      `,
      [
        req.userId,
        client_session_id ?? null,
        trail_id ?? null,
        started_at,
        ended_at ?? null,
        distance_km ?? null,
        duration_minutes ?? null,
        completion_status,
        route_progress_meters ?? null,
        route_total_meters ?? null,
        ended_latitude ?? null,
        ended_longitude ?? null,
      ]
    );

    res.status(201).json(rows[0]);
  } catch (error) {
    next(error);
  }
});

module.exports = router;
