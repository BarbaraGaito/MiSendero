const express = require("express");
const { z } = require("zod");
const { query } = require("../db");
const { requireAuth, requireAdmin } = require("../middleware/requireAuth");
const { validateBody } = require("../middleware/validate");
const { publicReport, publicReportColumns } = require("../reportContract");
const router = express.Router();
router.use(requireAuth);
const reportId = (req, res, next) => {
  if (!/^\d+$/.test(req.params.reportId)) return res.status(400).json({ message: "Reporte inválido" });
  next();
};
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
    const { rows } = await query("SELECT id FROM trail_reports WHERE reporter_user_id = $1", [report.reporter_user_id]);
    res.json({ hidden_report_ids: rows.map((row) => row.id) });
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
    res.json(publicReport(rows[0]));
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
