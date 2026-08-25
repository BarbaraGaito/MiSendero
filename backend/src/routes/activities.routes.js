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
    const { trail_id, started_at, ended_at, distance_km, duration_minutes } = req.body;

    const { rows } = await query(
      `
        INSERT INTO activities (user_id, trail_id, started_at, ended_at, distance_km, duration_minutes)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING *
      `,
      [
        req.userId,
        trail_id ?? null,
        started_at,
        ended_at ?? null,
        distance_km ?? null,
        duration_minutes ?? null,
      ]
    );

    res.status(201).json(rows[0]);
  } catch (error) {
    next(error);
  }
});

module.exports = router;
