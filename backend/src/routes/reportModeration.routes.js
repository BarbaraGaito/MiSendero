const express = require("express");
const { z } = require("zod");
const { query } = require("../db");
const { requireAuth, requireAdmin } = require("../middleware/requireAuth");
const { validateBody } = require("../middleware/validate");
const { publicReport, publicReportColumns } = require("../reportContract");
const { withReportCommunity } = require("../reportCommunity");
const { REPORT_STALE_AFTER_DAYS } = require("../cleanupStaleReports");
const router = express.Router();
router.use(requireAuth);
const reportId = (req, res, next) => {
  if (!/^\d+$/.test(req.params.reportId)) return res.status(400).json({ message: "Reporte inválido" });
  next();
};
router.post("/:reportId/feedback", reportId, validateBody(z.object({
  feedback: z.enum(["still_there", "not_there", "unsure"]),
  observed_at: z.iso.datetime().refine(value => Date.parse(value) <= Date.now() + 300000, "La observación no puede estar en el futuro"),
})), async (req, res, next) => {
  try {
    const row = (await query(`SELECT * FROM trail_reports WHERE id = $1 AND moderation_status = 'visible'
      AND (reporter_user_id IS NULL OR reporter_user_id NOT IN (SELECT blocked_user_id FROM report_blocks WHERE user_id = $2))`,
    [req.params.reportId, req.userId])).rows[0];
    if (!row) return res.status(404).json({ message: "Reporte no disponible" });
    const current = (await withReportCommunity([row], req.userId))[0];
    const expires = Date.parse(publicReport(current, true).expires_at);
    if (expires <= Date.now()) return res.status(410).json({ message: "El reporte ya venció. Creá uno con una observación reciente." });
    if (Date.parse(req.body.observed_at) < Date.now() - REPORT_STALE_AFTER_DAYS * 86400000) {
      return res.status(400).json({ message: "La confirmación debe corresponder a una observación reciente." });
    }
    await query(`INSERT INTO report_feedback (report_id, user_id, feedback, observed_at, last_seen_at) VALUES ($1, $2, $3, $4, $5)
      ON CONFLICT (report_id, user_id) DO UPDATE SET
        feedback = CASE WHEN report_feedback.observed_at <= EXCLUDED.observed_at THEN EXCLUDED.feedback ELSE report_feedback.feedback END,
        observed_at = CASE WHEN report_feedback.observed_at <= EXCLUDED.observed_at THEN EXCLUDED.observed_at ELSE report_feedback.observed_at END,
        last_seen_at = CASE WHEN EXCLUDED.last_seen_at IS NOT NULL AND (report_feedback.last_seen_at IS NULL OR EXCLUDED.last_seen_at > report_feedback.last_seen_at)
          THEN EXCLUDED.last_seen_at ELSE report_feedback.last_seen_at END,
        received_at = now()`,
    [row.id, req.userId, req.body.feedback, req.body.observed_at, req.body.feedback === "still_there" ? req.body.observed_at : null]);
    const updated = (await withReportCommunity([row], req.userId))[0];
    res.json({ ...publicReport(updated, row.reporter_user_id === req.userId), is_mine: row.reporter_user_id === req.userId });
  } catch (error) { next(error); }
});
router.get("/moderation", requireAdmin, async (_req, res, next) => {
  try {
    const { rows } = await query(`SELECT f.id, f.report_id, f.reason, f.created_at, r.issue_summary, r.details, r.moderation_status
      FROM report_flags f JOIN trail_reports r ON r.id = f.report_id ORDER BY f.created_at DESC LIMIT 100`);
    res.set("Cache-Control", "no-store").json(rows);
  } catch (error) { next(error); }
});
router.post("/:reportId/flag", reportId, validateBody(z.object({ reason: z.string().trim().min(3).max(500) })), async (req, res, next) => {
  try {
    const report = await query("SELECT id FROM trail_reports WHERE id = $1", [req.params.reportId]);
    if (!report.rows[0]) return res.status(404).json({ message: "Reporte no encontrado" });
    await query(`INSERT INTO report_flags (report_id, user_id, reason) VALUES ($1,$2,$3)
      ON CONFLICT (report_id, user_id) DO UPDATE SET reason = EXCLUDED.reason`, [req.params.reportId, req.userId, req.body.reason]);
    res.status(201).json({ received: true });
  } catch (error) { next(error); }
});
router.post("/:reportId/block-author", reportId, async (req, res, next) => {
  try {
    const report = (await query("SELECT reporter_user_id FROM trail_reports WHERE id = $1", [req.params.reportId])).rows[0];
    if (!report?.reporter_user_id) return res.status(404).json({ message: "El autor ya no está disponible" });
    if (report.reporter_user_id === req.userId) return res.status(400).json({ message: "Podés retirar tu propio reporte" });
    await query(`INSERT INTO report_blocks (user_id, blocked_user_id) VALUES ($1,$2) ON CONFLICT (user_id, blocked_user_id) DO NOTHING`, [req.userId, report.reporter_user_id]);
    res.json({ blocked: true });
  } catch (error) { next(error); }
});
router.delete("/:reportId", reportId, async (req, res, next) => {
  try {
    const { rowCount } = await query("DELETE FROM trail_reports WHERE id = $1 AND reporter_user_id = $2", [req.params.reportId, req.userId]);
    if (!rowCount) return res.status(404).json({ message: "Reporte propio no encontrado" });
    res.json({ withdrawn: true });
  } catch (error) { next(error); }
});
router.patch("/:reportId", reportId, validateBody(z.object({ issue_summary: z.string().trim().min(1).max(300), details: z.string().max(1000) })), async (req, res, next) => {
  try {
    const { rows } = await query(`UPDATE trail_reports SET issue_summary = $3, details = $4, updated_at = now()
      WHERE id = $1 AND reporter_user_id = $2 RETURNING ${publicReportColumns}`, [req.params.reportId, req.userId, req.body.issue_summary, req.body.details]);
    if (!rows[0]) return res.status(404).json({ message: "Reporte propio no encontrado" });
    res.json(publicReport(rows[0], true));
  } catch (error) { next(error); }
});
router.post("/:reportId/moderate", reportId, requireAdmin, validateBody(z.object({ status: z.enum(["visible", "hidden"]) })), async (req, res, next) => {
  try {
    const { rowCount } = await query("UPDATE trail_reports SET moderation_status = $2, updated_at = now() WHERE id = $1", [req.params.reportId, req.body.status]);
    if (!rowCount) return res.status(404).json({ message: "Reporte no encontrado" });
    res.json({ moderated: true });
  } catch (error) { next(error); }
});
module.exports = router;
