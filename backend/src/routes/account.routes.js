const express = require("express");
const bcrypt = require("bcrypt");
const { z } = require("zod");
const { query, getPool } = require("../db");
const { requireAuth } = require("../middleware/requireAuth");
const { validateBody } = require("../middleware/validate");
const notices = require("../privacyNotices.json");
const router = express.Router();
router.use(requireAuth);

router.delete("/me", validateBody(z.object({ password: z.string().min(1).max(200) })), async (req, res, next) => {
  const client = await (await getPool()).connect();
  try {
    await client.query("BEGIN");
    const { rows } = await client.query("SELECT password_hash FROM users WHERE id = $1 FOR UPDATE", [req.userId]);
    if (!rows[0] || !(await bcrypt.compare(req.body.password, rows[0].password_hash))) {
      await client.query("ROLLBACK");
      return res.status(401).json({ message: "No pudimos verificar la contraseña", code: "INVALID_PASSWORD" });
    }
    // Remove free text and contact/location copies too; SET NULL leaves names behind.
    await client.query("DELETE FROM trail_reports WHERE reporter_user_id = $1", [req.userId]);
    await client.query("DELETE FROM users WHERE id = $1", [req.userId]);
    await client.query("COMMIT");
    res.json({ deleted: true });
  } catch (error) {
    await client.query("ROLLBACK");
    next(error);
  } finally { client.release(); }
});

router.patch("/me", validateBody(z.object({ name: z.string().trim().min(1).max(120) })), async (req, res, next) => {
  try {
    const { rows } = await query("UPDATE users SET name = $2 WHERE id = $1 RETURNING id, name, email", [req.userId, req.body.name]);
    await query("UPDATE trail_reports SET reporter_name = 'Senderista' WHERE reporter_user_id = $1", [req.userId]);
    res.json(rows[0]);
  } catch (error) { next(error); }
});

router.get("/me/data", async (req, res, next) => {
  try {
    const data = {};
    data.user = (await query("SELECT id, name, email, terms_version, terms_accepted_at, created_at FROM users WHERE id = $1", [req.userId])).rows[0];
    for (const table of ["activities", "emergency_alerts", "trip_plans", "privacy_decisions", "report_flags", "report_blocks"]) {
      data[table] = (await query(`SELECT * FROM ${table} WHERE user_id = $1`, [req.userId])).rows;
    }
    data.reports = (await query("SELECT * FROM trail_reports WHERE reporter_user_id = $1", [req.userId])).rows;
    res.set("Cache-Control", "no-store").json(data);
  } catch (error) { next(error); }
});

const decisionSchema = z.object({
  client_event_id: z.string().min(1).max(100),
  purpose: z.enum(["sensitiveDataConsent", "analyticsTrainingConsent"]),
  notice_version: z.literal(notices.version),
  notice_text: z.string().max(2000),
  granted: z.boolean(),
  decided_at: z.iso.datetime().refine((value) => Date.parse(value) <= Date.now() + 300000, "Fecha futura no válida"),
}).refine((value) => value.notice_text === notices[value.purpose], "Texto de consentimiento no válido");
router.post("/me/privacy-decisions", validateBody(decisionSchema), async (req, res, next) => {
  try {
    const d = req.body;
    await query(`INSERT INTO privacy_decisions (user_id, client_event_id, purpose, notice_version, notice_text, granted, decided_at)
      VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (user_id, client_event_id) DO NOTHING`,
      [req.userId, d.client_event_id, d.purpose, d.notice_version, d.notice_text, d.granted, d.decided_at]);
    res.status(201).json({ recorded: true });
  } catch (error) { next(error); }
});
module.exports = router;
