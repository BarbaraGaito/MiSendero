import { TrailReport } from "../types";

// Also strips author data from downloads made by older versions.
export function sanitizeReports(reports: TrailReport[], now = Date.now()): TrailReport[] {
  if (!Array.isArray(reports)) return [];
  return reports.flatMap((report) => {
    if (!report || typeof report !== "object" || !Number.isInteger(report.id)) return [];
    const observed = Date.parse(report.observed_at || report.created_at);
    const expires = report.expires_at ? Date.parse(report.expires_at) : observed + 30 * 86400000;
    if (!Number.isFinite(observed) || !Number.isFinite(expires) || expires <= now) return [];
    const { id, trail_id, issue_summary, severity, trail_state, cause, blocks_path, details, latitude, longitude, route_progress_meters, created_at, updated_at, is_mine } = report;
    return [{ id, trail_id, issue_summary, severity, trail_state, cause, blocks_path, details, latitude, longitude, route_progress_meters, created_at, updated_at, is_mine,
      observed_at: new Date(observed).toISOString(), received_at: report.received_at || created_at, expires_at: new Date(expires).toISOString() }];
  });
}
