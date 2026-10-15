import {
  formatDistance,
  formatKilometers,
  getClosestPointOnRoute,
  getDistanceMeters,
  getDistanceToRouteMeters,
  getRouteLengthMeters,
  getRouteProgressMeters,
  parseRouteCoordinates,
} from "../geoUtils";

describe("geoUtils", () => {
  test("getDistanceMeters returns 0 for identical points", () => {
    expect(getDistanceMeters([-41.17, -71.47], [-41.17, -71.47])).toBe(0);
  });

  test("getDistanceMeters matches a known great-circle distance", () => {
    // Bariloche centro -> Villa Catedral, roughly 18km apart.
    const distance = getDistanceMeters([-41.1335, -71.3103], [-41.1568, -71.4489]);

    expect(distance).toBeGreaterThan(10_000);
    expect(distance).toBeLessThan(20_000);
  });

  test("parseRouteCoordinates accepts valid JSON arrays and rejects invalid input", () => {
    const parsed = parseRouteCoordinates("[[-41.1, -71.1], [-41.2, -71.2]]");
    expect(parsed).toEqual([
      [-41.1, -71.1],
      [-41.2, -71.2],
    ]);

    expect(parseRouteCoordinates(null)).toEqual([]);
    expect(parseRouteCoordinates("not json")).toEqual([]);
    expect(parseRouteCoordinates('["not-a-point"]')).toEqual([]);
  });

  test("getRouteLengthMeters sums consecutive segment distances", () => {
    const route: [number, number][] = [
      [-41.0, -71.0],
      [-41.01, -71.0],
      [-41.02, -71.0],
    ];
    const total = getRouteLengthMeters(route);
    const segment = getDistanceMeters(route[0], route[1]);

    expect(total).toBeCloseTo(segment * 2, 0);
  });

  test("getDistanceToRouteMeters is 0 for a point on the route", () => {
    const route: [number, number][] = [
      [-41.0, -71.0],
      [-41.01, -71.0],
    ];

    expect(getDistanceToRouteMeters(route[0], route)).toBe(0);
  });

  test("getRouteProgressMeters increases along the route", () => {
    const route: [number, number][] = [
      [-41.0, -71.0],
      [-41.01, -71.0],
      [-41.02, -71.0],
    ];

    const progressAtStart = getRouteProgressMeters(route[0], route) ?? 0;
    const progressAtEnd = getRouteProgressMeters(route[2], route) ?? 0;

    expect(progressAtEnd).toBeGreaterThan(progressAtStart);
  });

  test("getClosestPointOnRoute snaps a nearby map selection onto the trail", () => {
    const route: [number, number][] = [
      [-41.0, -71.0],
      [-41.01, -71.0],
    ];

    const closest = getClosestPointOnRoute([-41.005, -71.0002], route);

    expect(closest).not.toBeNull();
    expect(closest?.distanceMeters).toBeLessThan(30);
    expect(closest?.coordinate[1]).toBeCloseTo(-71.0, 3);
    expect(closest?.progressMeters).toBeGreaterThan(0);
  });

  test("GPS distance distinguishes outward and return legs at the same coordinate", () => {
    const route: [number, number][] = [[-41, -71], [-41.01, -71], [-41.02, -71], [-41.01, -71], [-41, -71]];
    const total = getRouteLengthMeters(route);
    expect(getRouteProgressMeters(route[0], route, 0)).toBeCloseTo(0, 0);
    expect(getRouteProgressMeters(route[1], route, total / 4)).toBeCloseTo(total / 4, 0);
    expect(getRouteProgressMeters(route[2], route, total / 2)).toBeCloseTo(total / 2, 0);
    expect(getRouteProgressMeters(route[3], route, total * 0.75)).toBeCloseTo(total * 0.75, 0);
    expect(getRouteProgressMeters(route[4], route, total)).toBeCloseTo(total, 0);
    expect(getRouteProgressMeters(route[4], route)).toBeCloseTo(0, 0);
  });

  test("every new out-and-back trail supports completion at its starting coordinate", () => {
    const catalog = require("../../backend/src/data/additionalTrails");
    for (const trail of catalog.filter((item: { provenance: { route_type: string } }) => item.provenance.route_type === "out_and_back")) {
      const route = trail.route_coordinates as [number, number][];
      const total = getRouteLengthMeters(route);
      expect(getRouteProgressMeters(route[0], route, 0)).toBeCloseTo(0, 0);
      expect(getRouteProgressMeters(route.at(-1)!, route, total)).toBeCloseTo(total, 0);
    }
  });

  test("getClosestPointOnRoute exposes distance so callers can reject off-trail selections", () => {
    const route: [number, number][] = [
      [-41.0, -71.0],
      [-41.01, -71.0],
    ];

    const closest = getClosestPointOnRoute([-41.005, -71.01], route);

    expect(closest?.distanceMeters).toBeGreaterThan(800);
  });

  test("formatDistance switches between meters and kilometers", () => {
    expect(formatDistance(500)).toBe("500 m");
    expect(formatDistance(1500)).toBe("1,5 km");
    expect(formatDistance(7637)).toBe("7,64 km");
  });

  test.each([[7.637, "7,64 km"], [7.453, "7,45 km"], [0.738, "0,74 km"],
    [18.84, "18,84 km"], [2, "2 km"], [0, "0 km"], [1234.567, "1234,57 km"]])(
    "formats %s km with a decimal comma and at most two decimals", (distance, label) => {
      expect(formatKilometers(distance as number)).toBe(label);
    }
  );
});
