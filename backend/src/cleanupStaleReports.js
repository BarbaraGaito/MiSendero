const { query } = require("./db");

// PDF section 2.1.7.1: "los reportes obsoletos serán descartados automáticamente."
const REPORT_STALE_AFTER_DAYS = Number(process.env.REPORT_STALE_AFTER_DAYS || 30);

const cleanupStaleReports = async () => {
  const { rowCount } = await query(
    `DELETE FROM trail_reports WHERE created_at <= now() - ($1 || ' days')::interval`,
    [REPORT_STALE_AFTER_DAYS]
  );

  return rowCount;
};

module.exports = { cleanupStaleReports, REPORT_STALE_AFTER_DAYS };
