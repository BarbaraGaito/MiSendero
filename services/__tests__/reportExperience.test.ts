import type { TrailReport } from "../../types";
import { Coordinate, coordinateAtRouteProgress, getDistanceMeters, getRouteSectionCoordinates } from "../geoUtils";
import { buildReportRouteRanges, findSimilarReports, getUpcomingReport, parseObservationDate } from "../reportExperience";
const route: Coordinate[] = [[-41, -71], [-41.01, -71], [-41.01, -71.01]];
const report = (extra: Partial<TrailReport> = {}): TrailReport => ({ id: 1, trail_id: 7, issue_summary: "Barro", severity: "Alta", trail_state: "Paso dificil",
  blocks_path: false, cause: null, details: null, latitude: -41.004, longitude: -71, route_progress_meters: 445,
  created_at: new Date().toISOString(), ...extra });

test("section geometry follows every bend and refuses progress outside the actual route", () => {
  const bend = getDistanceMeters(route[0], route[1]);
  const points = getRouteSectionCoordinates(route, bend - 100, bend + 200);
  expect(points).toHaveLength(3); expect(points[1]).toEqual(route[1]);
  expect(coordinateAtRouteProgress(route, 99999)).toBeNull();
  expect(getRouteSectionCoordinates(route, -1, 20)).toEqual([]);
});

test("duplicate suggestions match incident type and overlapping route sections, excluding resolved and other trails", () => {
  const reports = [report(), report({ id: 2, issue_summary: "Basura" }), report({ id: 3, trail_id: 8 }), report({ id: 4, community_status: "resolved" }),
    report({ id: 5, route_progress_meters: 900, latitude: -41.008 })];
  expect(findSimilarReports(reports, 7, ["Barro"], [-41.0041, -71], 450).map(item => item.id)).toEqual([1]);
  expect(findSimilarReports([report({ route_progress_meters: 100, route_end_progress_meters: 700 })], 7, ["Barro"], [-41.005, -71], 550, 600)).toHaveLength(1);
  expect(findSimilarReports(reports, 7, [], [-41.0041, -71], 450)).toEqual([]);
  expect(findSimilarReports([report({ route_progress_meters: null })], 7, ["Barro"], [-41.0041, -71], 450)).toHaveLength(1);
});

test("proximity uses route distance and direction, not straight-line distance or already-passed warnings", () => {
  const items = buildReportRouteRanges([report({ is_mine: true })], 7, route);
  const forward = getUpcomingReport(items, 100, 1)!;
  expect(forward.report.id).toBe(1); expect(forward.distanceMeters).toBeGreaterThan(300);
  expect(getUpcomingReport(items, 700, 1)).toBeNull();
  expect(getUpcomingReport(items, 700, -1)?.report.id).toBe(1);
  expect(getUpcomingReport(items, null, 1)).toBeNull();
  const folded: Coordinate[] = [[0, 0], [0.01, 0], [0.01, 0.001], [0, 0.001]];
  const aroundCorner = buildReportRouteRanges([report({ latitude: 0, longitude: 0.001, route_progress_meters: 2300, is_mine: true })], 7, folded);
  expect(getUpcomingReport(aroundCorner, 0, 1)).toBeNull();
});

test("the same physical hazard warns again on a retraced return leg and resolved hazards stop warning", () => {
  const retraced: Coordinate[] = [[-41, -71], [-41.01, -71], [-41, -71]];
  const ranges = buildReportRouteRanges([report({ is_mine: true })], 7, retraced);
  expect(ranges[0].ranges.length).toBe(2);
  const outward = getUpcomingReport(ranges, 200, 1)!;
  const returning = getUpcomingReport(ranges, 1400, 1)!;
  expect(outward.occurrence).not.toBe(returning.occurrence);
  expect(buildReportRouteRanges([report({ community_status: "resolved" })], 7, retraced)).toEqual([]);
});

test("custom observation times validate calendar dates, future entries and the retention window", () => {
  const now = new Date(2026, 10, 5, 12).getTime();
  expect(parseObservationDate("04/11/2026 14:30", now)).toBe(new Date(2026, 10, 4, 14, 30).toISOString());
  expect(parseObservationDate("31/02/2026 12:00", now)).toBeNull();
  expect(parseObservationDate("20/11/2026 12:00", now)).toBeNull();
  expect(parseObservationDate("05/11/2026 12:01", now)).toBeNull();
  expect(parseObservationDate("01/01/2026 12:00", now)).toBeNull();
});
