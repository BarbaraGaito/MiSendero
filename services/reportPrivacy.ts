import { TrailReport } from "../types";
import { minimizeCachedPublicReport } from "./publicReportMinimization";

// Also strips author data from downloads made by older versions.
export function sanitizeReports(reports: TrailReport[], now = Date.now()): TrailReport[] {
  if (!Array.isArray(reports)) return [];
  return reports.flatMap((report) => {
    if (!report || typeof report !== "object" || !Number.isInteger(report.id)) return [];
    const observed = Date.parse(report.observed_at || report.created_at);
    const expires = report.expires_at ? Date.parse(report.expires_at) : observed + 30 * 86400000;
    if (!Number.isFinite(observed) || !Number.isFinite(expires) || expires <= now) return [];
    const { id, trail_id, issue_summary, severity, trail_state, cause, blocks_path, details, latitude, longitude, route_progress_meters, created_at, updated_at, is_mine,
      end_latitude, end_longitude, route_end_progress_meters, confirmation_count, cleared_count, unsure_count, last_confirmed_at, last_checked_at, community_status, my_feedback } = report;
    return [minimizeCachedPublicReport({ id, trail_id, issue_summary, severity, trail_state, cause, blocks_path, details, latitude, longitude, route_progress_meters, created_at, updated_at, is_mine,
      end_latitude, end_longitude, route_end_progress_meters, confirmation_count, cleared_count, unsure_count, last_confirmed_at, last_checked_at, community_status, my_feedback,
      observed_at: new Date(observed).toISOString(), received_at: report.received_at || created_at, expires_at: new Date(expires).toISOString() })];
  });
}
