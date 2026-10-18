const express = require("express");
const { z } = require("zod");
const { query } = require("../db");
const { requireAuth } = require("../middleware/requireAuth");
const { validateBody } = require("../middleware/validate");
const { isNotificationChannelConfigured } = require("../tripNotifications");
const router = express.Router();
const schema = z.object({
  client_plan_id: z.string().uuid(), trail_id: z.number().int().positive(),
  expected_return_at: z.string().datetime(), grace_minutes: z.number().int().min(15).max(120),
  contact_name: z.string().trim().min(1).max(200), contact_phone: z.string().regex(/^\+?[0-9 ()-]{6,30}$/),
});
router.use(requireAuth);
router.get("/", async (req, res, next) => {
  try {
    const result = await query(`SELECT p.*, n.status AS notification_status FROM trip_plans p LEFT JOIN trip_notifications n ON n.plan_id = p.id WHERE p.user_id = $1 AND p.retention_purged_at IS NULL ORDER BY p.created_at DESC LIMIT 50`, [req.userId]);
    res.json(result.rows);
  } catch (error) { next(error); }
});
router.post("/", validateBody(schema), async (req, res, next) => {
  try {
    const value = req.body;
    const existing = await query("SELECT * FROM trip_plans WHERE user_id = $1 AND client_plan_id = $2", [req.userId, value.client_plan_id]);
    if (existing.rows[0]) return res.json(existing.rows[0]);
    if (!isNotificationChannelConfigured()) return res.status(503).json({ message: "El aviso automático aún no tiene un canal de notificación configurado. Acordá el regreso directamente con tu contacto." });
    const returnTime = Date.parse(value.expected_return_at);
    if (returnTime <= Date.now() || returnTime > Date.now() + 72 * 3600000) return res.status(400).json({ message: "El regreso debe estar dentro de las próximas 72 horas." });
    const created = await query(`INSERT INTO trip_plans (user_id, client_plan_id, trail_id, expected_return_at, grace_minutes, contact_name, contact_phone)
      VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT (user_id, client_plan_id) DO UPDATE SET client_plan_id = EXCLUDED.client_plan_id RETURNING *`,
      [req.userId, value.client_plan_id, value.trail_id, value.expected_return_at, value.grace_minutes, value.contact_name, value.contact_phone]);
    // A committed plan is the durable schedule. The worker recreates a missing job.
    res.status(201).json(created.rows[0]);
  } catch (error) { next(error); }
});
router.post("/:id/close", validateBody(z.object({ status: z.enum(["checked_in", "cancelled"]) })), async (req, res, next) => {
  try {
    if (!/^\d+$/.test(req.params.id)) return res.status(400).json({ message: "Plan inválido" });
    const closed = await query(`UPDATE trip_plans SET status = $3, closed_at = NOW() WHERE id = $1 AND user_id = $2 AND status IN ('active', 'overdue') RETURNING *`, [Number(req.params.id), req.userId, req.body.status]);
    const result = closed.rows[0] ? closed : await query("SELECT * FROM trip_plans WHERE id = $1 AND user_id = $2", [Number(req.params.id), req.userId]);
    if (!result.rows[0]) return res.status(404).json({ message: "Plan no encontrado" });
    res.json(result.rows[0]);
  } catch (error) { next(error); }
});
module.exports = router;
