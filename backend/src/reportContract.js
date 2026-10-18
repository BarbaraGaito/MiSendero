const { REPORT_STALE_AFTER_DAYS } = require("./cleanupStaleReports");
const { minimizePublicReport } = require("./reportPrivacy");
const publicReportColumns = `id, trail_id, issue_summary, severity, trail_state, cause,
  blocks_path, details, latitude, longitude, route_progress_meters,
  created_at, observed_at, updated_at`;
const publicReport = (row, owner = false) => {
  const report = {};
  for (const key of publicReportColumns.split(",").map((key) => key.trim())) report[key] = row[key];
  report.observed_at = row.observed_at || row.created_at;
  report.received_at = row.created_at;
  report.expires_at = new Date(new Date(report.observed_at).getTime() + REPORT_STALE_AFTER_DAYS * 86400000).toISOString();
  return owner ? report : minimizePublicReport(report);
};
module.exports = { publicReportColumns, publicReport };
