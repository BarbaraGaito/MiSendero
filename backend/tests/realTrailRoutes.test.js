const realTrailRoutes = require("../src/data/realTrailRoutes");

describe("real seeded trail geometries", () => {
  test("keeps a detailed trace for every seeded trail", () => {
    expect(Object.keys(realTrailRoutes)).toHaveLength(10);

    for (const [name, coordinates] of Object.entries(realTrailRoutes)) {
      expect(coordinates.length).toBeGreaterThanOrEqual(6);

      for (const coordinate of coordinates) {
        expect(coordinate).toHaveLength(2);
        expect(Number.isFinite(coordinate[0])).toBe(true);
        expect(Number.isFinite(coordinate[1])).toBe(true);
        expect(coordinate[0]).toBeGreaterThanOrEqual(-90);
        expect(coordinate[0]).toBeLessThanOrEqual(90);
        expect(coordinate[1]).toBeGreaterThanOrEqual(-180);
        expect(coordinate[1]).toBeLessThanOrEqual(180);
      }

      expect(new Set(coordinates.map((point) => point.join(","))).size).toBeGreaterThanOrEqual(6);
      expect(name).not.toMatch(/placeholder|example/i);
    }
  });

  test("anchors the corrected Salta route at the real attraction", () => {
    const finish = realTrailRoutes.saltaGarganta.at(-1);

    expect(finish[0]).toBeCloseTo(-25.848657, 5);
    expect(finish[1]).toBeCloseTo(-65.69947, 5);
  });
});
