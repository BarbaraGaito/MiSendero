const express = require("express");
const rateLimit = require("express-rate-limit");
const { query } = require("../db");
const { requireAuth } = require("../middleware/requireAuth");
const { preferencesSchema } = require("../../dist/ai/schemas");
const { recommendTrail } = require("../../dist/ai/assistant");
const { verifiedCatalog, catalogDestinations } = require("../../dist/ai/catalog");
const { cachedElevation } = require("../trailElevation");

const router = express.Router();
// Both IP and authenticated account budgets apply. No client-supplied IP/proxy trust changes.
const options = { windowMs: 15 * 60 * 1000, standardHeaders: "draft-8", legacyHeaders: false,
  message: { message: "Alcanzaste el límite de búsquedas. Volvé a intentar en unos minutos." } };
const ipLimiter = rateLimit({ ...options, limit: 30 });
const accountLimiter = rateLimit({ ...options, limit: 10, keyGenerator: (req) => String(req.userId) });
let activeRequests = 0;
const catalogRows = async () => {
  const { rows } = await query({ text: "SELECT * FROM trails ORDER BY id", query_timeout: 5000 });
  return rows.map((row) => ({ ...row, verified_ascent_m: cachedElevation(row)?.ascent_m ?? null }));
};
router.get("/destinations", requireAuth, rateLimit({ ...options, limit: 60 }), async (_req, res, next) => {
  try { res.set("Cache-Control", "no-store").json({ destinations: catalogDestinations(verifiedCatalog(await catalogRows())) }); }
  catch (error) { next(error); }
});
router.post("/recommend-trail", ipLimiter, requireAuth, accountLimiter, express.json({ limit: "2kb" }), async (req, res, next) => {
  res.set("Cache-Control", "no-store");
  if (Buffer.byteLength(JSON.stringify(req.body) || "") > 2048) return res.status(413).json({ message: "La solicitud es demasiado extensa." });
  const parsed = preferencesSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ message: "Revisá el destino y las opciones de la encuesta." });
  if (activeRequests >= 4) return res.status(503).json({ message: "El asistente está ocupado. Intentá nuevamente en un momento." });
  activeRequests++;
  try {
    const rows = await catalogRows();
    const result = await recommendTrail(parsed.data, rows);
    res.json(result);
  } catch (error) {
    next(error);
  } finally { activeRequests--; }
});
module.exports = router;
