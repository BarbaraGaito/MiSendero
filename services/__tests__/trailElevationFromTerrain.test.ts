import { trailElevationFromTerrain } from "../trailElevationFromTerrain";
import type { TerrainGridData } from "../terrainElevation";

const data: TerrainGridData = {
  grid: {
    size: 3,
    center: [0.5, 0.5],
    bounds: { north: 1, south: 0, west: 0, east: 1 },
    sideLengthMeters: 1000,
    cellSizeMeters: 500,
    elevationsMeters: [300, 300, 300, 200, 200, 200, 100, 100, 100],
    minElevationMeters: 100,
    maxElevationMeters: 300,
  },
  source: {
    provider: "AWS Terrain Tiles",
    dataset: "Mapzen Terrain Tiles",
    resolutionMeters: 90,
    endpoint: "https://example.test/terrain",
    attribution: "Terrain tiles",
    fetchedAt: "2026-11-10T12:00:00.000Z",
  },
};

test("builds a descending trail profile from the same DEM used by the 3D map", () => {
  const profile = trailElevationFromTerrain(9, [[1, 0.5], [0, 0.5]], data)!;
  expect(profile.source).toBe("Mapzen Terrain Tiles");
  expect(profile.points.length).toBeGreaterThan(2);
  expect(profile.points[0].latitude).toBe(1);
  expect(profile.points.at(-1)!.latitude).toBe(0);
  expect(profile.points[0].elevation_m).toBeGreaterThan(profile.points.at(-1)!.elevation_m);
  expect(profile.descent_m).toBeGreaterThan(100);
  expect(profile.ascent_m).toBe(0);
  expect(profile.distance_m).toBeGreaterThan(100000);
});

test("does not invent a profile when the DEM has missing values", () => {
  expect(trailElevationFromTerrain(9, [[1, 0.5], [0, 0.5]], {
    ...data, grid: { ...data.grid, elevationsMeters: [300] },
  })).toBeNull();
});
