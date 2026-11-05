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

    let { rows } = await query(
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
        DO NOTHING
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

    if (client_session_id) {
      rows = (await query("SELECT * FROM activities WHERE user_id = $1 AND client_session_id = $2", [req.userId, client_session_id])).rows;
      const row = rows[0];
      const date = (v) => v == null ? null : new Date(v).toISOString();
      const number = (v) => v == null ? null : Number(v);
      // PostgreSQL REAL stores float32; compare both payloads at that precision.
      const real = (v) => v == null ? null : Math.fround(Number(v));
      const canonical = (v) => JSON.stringify([
        number(v.trail_id), date(v.started_at), date(v.ended_at), real(v.distance_km),
        number(v.duration_minutes), v.completion_status, real(v.route_progress_meters),
        real(v.route_total_meters), real(v.ended_latitude), real(v.ended_longitude),
      ]);
      if (!row || canonical(row) !== canonical(req.body)) {
        return res.status(409).json({ code: "IDEMPOTENCY_CONFLICT", error: "La identidad de actividad ya pertenece a otros datos; no se sobrescribió." });
      }
    }
    res.status(201).json(rows[0]);
  } catch (error) {
    next(error);
  }
});

module.exports = router;
