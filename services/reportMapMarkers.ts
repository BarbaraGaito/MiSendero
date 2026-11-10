import type { TrailReport } from "../types";
import { Coordinate, getDistanceMeters, getRouteLengthMeters } from "./geoUtils";
import { sanitizeReports } from "./reportPrivacy";

export type ReportMapMarker = {
  report: TrailReport;
  coordinate: Coordinate;
  color: string;
  precisionMeters: number;
};

const coordinateAtProgress = (route: Coordinate[], progress: number): Coordinate | null => {
  if (route.length < 2 || !Number.isFinite(progress) || progress < 0 || progress > getRouteLengthMeters(route)) return null;
  let remaining = progress;
  for (let index = 1; index < route.length; index += 1) {
    const start = route[index - 1], end = route[index];
    const length = getDistanceMeters(start, end);
    if (remaining <= length) {
      const ratio = length > 0 ? remaining / length : 0;
      return [start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio];
    }
    remaining -= length;
  }
  return route.at(-1) ?? null;
};

// Apply the same public minimization to API data and older downloaded copies.
export function getReportMapMarkers(reports: TrailReport[], trailId: number, route: Coordinate[], now = Date.now()): ReportMapMarker[] {
  return sanitizeReports(reports, now).flatMap((report) => {
    if (report.trail_id !== trailId || report.community_status === "resolved") return [];
    const { latitude, longitude } = report;
    const hasCoordinate = typeof latitude === "number" && Number.isFinite(latitude) && Math.abs(latitude) <= 90 &&
      typeof longitude === "number" && Number.isFinite(longitude) && Math.abs(longitude) <= 180;
    const coordinate: Coordinate | null = hasCoordinate ? [latitude, longitude] :
      report.route_progress_meters != null ? coordinateAtProgress(route, report.route_progress_meters) : null;
    if (!coordinate) return [];
    const severity = report.severity.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    return [{ report, coordinate, precisionMeters: report.is_mine ? Math.max(0, report.accuracy_meters ?? 0) : 150,
      color: report.blocks_path || ["alta", "critica"].includes(severity) ? "#BD332B" : "#A85A00" }];
  });
}
