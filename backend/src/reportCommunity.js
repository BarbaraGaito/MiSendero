const { query } = require("./db");

// One current response per account. A single third-party disagreement cannot
// remove a hazard; a later sighting can reopen a previously cleared report.
const summarizeReportFeedback = (report, feedback, viewerId) => {
  const observed = Date.parse(report.observed_at || report.created_at);
  const present = feedback.filter(item => item.feedback === "still_there");
  const seen = feedback.map(item => item.last_seen_at || (item.feedback === "still_there" ? item.observed_at : null)).filter(Boolean).map(value => new Date(value).getTime());
  const latest = Math.max(observed, ...seen);
  const cleared = feedback.filter(item => item.feedback === "not_there");
  const newerCleared = cleared.filter(item => new Date(item.observed_at).getTime() >= latest);
  const ownerCleared = newerCleared.some(item => item.user_id === report.reporter_user_id);
  const status = ownerCleared || newerCleared.length >= 2 ? "resolved" : newerCleared.length ? "disputed" : present.length ? "confirmed" : "reported";
  return {
    ...report,
    confirmation_count: present.length,
    cleared_count: cleared.length,
    unsure_count: feedback.filter(item => item.feedback === "unsure").length,
    last_confirmed_at: seen.length ? new Date(Math.max(...seen)).toISOString() : null,
    last_checked_at: feedback.length ? new Date(Math.max(...feedback.map(item => new Date(item.observed_at).getTime()))).toISOString() : null,
    community_status: status,
    my_feedback: feedback.find(item => item.user_id === viewerId)?.feedback ?? null,
  };
};

const withReportCommunity = async (reports, viewerId = null) => {
  if (!reports.length) return [];
  const placeholders = reports.map((_, index) => `$${index + 1}`).join(",");
  const { rows } = await query(`SELECT report_id, user_id, feedback, observed_at, last_seen_at FROM report_feedback WHERE report_id IN (${placeholders})`, reports.map(report => report.id));
  return reports.map(report => summarizeReportFeedback(report, rows.filter(item => item.report_id === report.id), viewerId));
};

module.exports = { summarizeReportFeedback, withReportCommunity };
