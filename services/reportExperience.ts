import type { TrailReport } from "../types";
import { Coordinate, getClosestPointOnRoute, getDistanceMeters, getRouteLengthMeters } from "./geoUtils";
import { sanitizeReports } from "./reportPrivacy";

export const passageOptions = [
  { id: "clear", label: "Se puede pasar", hint: "Molestia leve, sin dificultad para avanzar", severity: "Leve", trailState: "Transitable", blocksPath: false },
  { id: "careful", label: "Con precaución", hint: "Requiere atención al caminar", severity: "Media", trailState: "Precaucion", blocksPath: false },
  { id: "difficult", label: "Paso difícil", hint: "Obstáculo importante o paso complicado", severity: "Alta", trailState: "Paso dificil", blocksPath: false },
  { id: "blocked", label: "No se puede pasar", hint: "El incidente corta el recorrido", severity: "Critica", trailState: "No transitable", blocksPath: true },
] as const;

const normalize = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
export const isActiveReport = (report: TrailReport) => report.community_status !== "resolved";

export function findSimilarReports(reports: TrailReport[], trailId: number, issues: string[], coordinate: Coordinate | null,
  progress: number | null, endProgress: number | null = null, now = Date.now()): TrailReport[] {
  if (!coordinate || issues.length === 0) return [];
  const selected = issues.map(normalize);
  return sanitizeReports(reports, now).filter(report => {
    if (report.trail_id !== trailId || !isActiveReport(report) || !report.issue_summary.split(",").some(issue => selected.includes(normalize(issue)))) return false;
    const reportStart = report.route_progress_meters;
    const reportEnd = report.route_end_progress_meters ?? reportStart;
    const start = progress, end = endProgress ?? progress;
    const nearbyProgress = reportStart != null && reportEnd != null && start != null && end != null &&
      Math.max(Math.min(reportStart, reportEnd), Math.min(start, end)) <= Math.min(Math.max(reportStart, reportEnd), Math.max(start, end)) + 180;
    if (report.latitude == null || report.longitude == null) return nearbyProgress;
    const nearbyPosition = getDistanceMeters(coordinate, [report.latitude, report.longitude]) <= 220;
    return nearbyProgress && (nearbyPosition || endProgress != null || report.route_end_progress_meters != null) || ((start == null || reportStart == null) && nearbyPosition);
  }).sort((a, b) => Date.parse(b.last_confirmed_at || b.observed_at || b.created_at) - Date.parse(a.last_confirmed_at || a.observed_at || a.created_at));
}

export function reportAge(value: string | null | undefined, now = Date.now()): string {
  const timestamp = value ? Date.parse(value) : NaN;
  if (!Number.isFinite(timestamp)) return "Sin fecha disponible";
  const minutes = Math.max(0, Math.floor((now - timestamp) / 60000));
  if (minutes < 1) return "hace un momento";
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  return `hace ${Math.floor(hours / 24)} días`;
}

export function parseObservationDate(value: string, now = Date.now()): string | null {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})\s+(\d{2}):(\d{2})$/.exec(value.trim());
  if (!match) return null;
  const [, day, month, year, hours, minutes] = match.map(Number);
  const date = new Date(year, month - 1, day, hours, minutes);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day || date.getHours() !== hours || date.getMinutes() !== minutes) return null;
  const timestamp = date.getTime();
  return timestamp > now || timestamp < now - 30 * 86400000 ? null : date.toISOString();
}

export function reportCommunityLabel(report: TrailReport): string {
  if (report.community_status === "resolved") return "Marcado como resuelto";
  if (report.community_status === "disputed") return "Hay respuestas distintas · verificar al llegar";
  if (report.last_confirmed_at && (report.confirmation_count ?? 0) > 0) {
    return `${report.confirmation_count} ${report.confirmation_count === 1 ? "persona confirmó" : "personas confirmaron"} · última vez ${reportAge(report.last_confirmed_at)}`;
  }
  if (report.last_confirmed_at) return `Última observación confirmada ${reportAge(report.last_confirmed_at)} · sin nuevas verificaciones`;
  return "Todavía sin confirmaciones de otros senderistas";
}

type Range = { start: number; end: number };
export type ReportRouteRange = { report: TrailReport; ranges: Range[]; precisionMeters: number };

// Cache this result when reports or geometry change. Multiple occurrences cover
// a retraced trail on both the outward and return legs, without straight-line shortcuts.
export function buildReportRouteRanges(reports: TrailReport[], trailId: number, route: Coordinate[], now = Date.now()): ReportRouteRange[] {
  if (route.length < 2) return [];
  const total = getRouteLengthMeters(route);
  const occurrences = (coordinate: Coordinate, precision: number) => {
    const found: { progress: number; distance: number; last: number }[] = [];
    let traversed = 0;
    for (let index = 1; index < route.length; index++) {
      const candidate = getClosestPointOnRoute(coordinate, [route[index - 1], route[index]]);
      const length = getDistanceMeters(route[index - 1], route[index]);
      if (candidate && candidate.distanceMeters <= precision + 25) {
        const progress = traversed + candidate.progressMeters;
        const previous = found.at(-1);
        if (previous && progress - previous.last <= precision * 2 + 50) {
          previous.last = progress;
          if (candidate.distanceMeters < previous.distance) { previous.progress = progress; previous.distance = candidate.distanceMeters; }
        } else found.push({ progress, distance: candidate.distanceMeters, last: progress });
      }
      traversed += length;
    }
    return found.map(item => item.progress);
  };
  return sanitizeReports(reports, now).filter(report => report.trail_id === trailId && isActiveReport(report)).map(report => {
    const precisionMeters = report.is_mine ? Math.max(report.accuracy_meters ?? 0, 15) : 150;
    const ranges: Range[] = [];
    const start = report.route_progress_meters, end = report.route_end_progress_meters ?? start;
    if (start != null && end != null && start >= 0 && end >= start && end <= total + precisionMeters) ranges.push({ start, end: Math.min(end, total) });
    if (report.latitude != null && report.longitude != null) {
      const starts = occurrences([report.latitude, report.longitude], precisionMeters);
      if (report.end_latitude != null && report.end_longitude != null && end != null && start != null) {
        const ends = occurrences([report.end_latitude, report.end_longitude], precisionMeters);
        starts.forEach(a => ends.forEach(b => {
          if (Math.abs(Math.abs(b - a) - (end - start)) <= precisionMeters * 2 + 30) ranges.push({ start: Math.min(a, b), end: Math.max(a, b) });
        }));
      } else starts.forEach(value => ranges.push({ start: value, end: value }));
    }
    const merged: Range[] = [];
    ranges.sort((a, b) => a.start - b.start).forEach(range => {
      const previous = merged.at(-1);
      if (previous && range.start <= previous.end + precisionMeters * 2 + 40) previous.end = Math.max(previous.end, range.end);
      else merged.push({ ...range });
    });
    return { report, ranges: merged, precisionMeters };
  }).filter(item => item.ranges.length > 0);
}

export function getUpcomingReport(items: ReportRouteRange[], progress: number | null, direction: 1 | -1, maxDistance = 500) {
  if (progress == null || !Number.isFinite(progress)) return null;
  return items.flatMap(item => {
    const candidates = item.ranges.flatMap((range, occurrence) => {
      if (direction === 1 && range.end + item.precisionMeters < progress || direction === -1 && range.start - item.precisionMeters > progress) return [];
      return [{ distanceMeters: Math.max(0, direction === 1 ? range.start - progress - item.precisionMeters : progress - range.end - item.precisionMeters), occurrence }];
    });
    const nearest = candidates.sort((a, b) => a.distanceMeters - b.distanceMeters)[0];
    return nearest && nearest.distanceMeters <= maxDistance ? [{ ...item, ...nearest }] : [];
  }).sort((a, b) => a.distanceMeters - b.distanceMeters || Number(b.report.blocks_path) - Number(a.report.blocks_path))[0] ?? null;
}
