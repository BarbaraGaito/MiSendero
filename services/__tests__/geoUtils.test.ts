import {
  formatDistance,
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

  test("formatDistance switches between meters and kilometers", () => {
    expect(formatDistance(500)).toBe("500 m");
    expect(formatDistance(1500)).toBe("1.5 km");
  });
});
