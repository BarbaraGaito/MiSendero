const { query } = require("./db");

// PDF section 2.1.7.1: "los reportes obsoletos serán descartados automáticamente."
const REPORT_STALE_AFTER_DAYS = Number(process.env.REPORT_STALE_AFTER_DAYS || 30);
if (!Number.isInteger(REPORT_STALE_AFTER_DAYS) || REPORT_STALE_AFTER_DAYS < 1 || REPORT_STALE_AFTER_DAYS > 365) throw new Error("REPORT_STALE_AFTER_DAYS debe estar entre 1 y 365.");

const cleanupStaleReports = async () => {
  const { rowCount } = await query(
    `DELETE FROM trail_reports WHERE COALESCE(observed_at, created_at) <= now() - ($1 || ' days')::interval
      AND id NOT IN (SELECT report_id FROM report_feedback WHERE last_seen_at > now() - ($1 || ' days')::interval)`,
    [REPORT_STALE_AFTER_DAYS]
  );

  return rowCount;
};

module.exports = { cleanupStaleReports, REPORT_STALE_AFTER_DAYS };
