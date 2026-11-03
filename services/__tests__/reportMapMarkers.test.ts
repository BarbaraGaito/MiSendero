import type { TrailReport } from "../../types";
import { getReportMapMarkers } from "../reportMapMarkers";
import { Coordinate } from "../geoUtils";

const now = Date.UTC(2026, 10, 3, 12);
const route: Coordinate[] = [[-41, -71], [-41.01, -71]];
const report: TrailReport = {
  id: 1, trail_id: 7, issue_summary: "Derrumbe", severity: "Alta", trail_state: "No transitable",
  cause: "Lluvia", blocks_path: true, details: "Texto privado", latitude: -41.00049, longitude: -71.00049,
  route_progress_meters: 54, created_at: new Date(now - 3600000).toISOString(),
};

test("map warnings keep public positions approximate and omit expired and other-trail reports", () => {
  const markers = getReportMapMarkers([report, { ...report, id: 2, trail_id: 8 },
    { ...report, id: 3, expires_at: new Date(now - 1).toISOString() },
    { ...report, id: 4, created_at: "invalid" }], 7, route, now);
  expect(markers).toHaveLength(1);
  expect(markers[0]).toMatchObject({ coordinate: [-41, -71], color: "#BD332B", precisionMeters: 150,
    report: { details: null, route_progress_meters: 100 } });
});

test("legacy reports with only route progress use that approximate section, never an invented start point", () => {
  const markers = getReportMapMarkers([{ ...report, latitude: null, longitude: null, route_progress_meters: 550 },
    { ...report, id: 2, latitude: null, longitude: null, route_progress_meters: null },
    { ...report, id: 3, latitude: null, longitude: null, route_progress_meters: 9000 }], 7, route, now);
  expect(markers).toHaveLength(1);
  expect(markers[0].coordinate[0]).toBeCloseTo(-41.0054, 4);
  expect(markers[0].coordinate[1]).toBe(-71);
});

test("own positions and risk colors distinguish blocking, critical and moderate incidents", () => {
  const markers = getReportMapMarkers([{ ...report, is_mine: true },
    { ...report, id: 2, blocks_path: false, severity: "Media" },
    { ...report, id: 3, blocks_path: false, severity: "Crítica" }], 7, route, now);
  expect(markers[0].coordinate).toEqual([-41.00049, -71.00049]);
  expect(markers[1].color).toBe("#A85A00");
  expect(markers[2].color).toBe("#BD332B");
});
