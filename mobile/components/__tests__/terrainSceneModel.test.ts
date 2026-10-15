import { readFileSync } from "fs";
import { join } from "path";
import type { Coordinate } from "../../../services/geoUtils";
import type { TerrainElevationGrid } from "../../../services/terrainElevation";
import {
  TERRAIN_SCENE_HALF_SIZE,
  buildTerrainMeshData,
  buildTerrainSceneModel,
  coordinateToTerrainScenePoint,
  drapeRouteOnTerrain,
  getTerrainSceneHeight,
  getTerrainWeatherKind,
} from "../terrainSceneModel";

// Grilla 3x3 (fila 0 = norte) como la que devuelve el DEM.
const makeGrid = (
  elevationsMeters = [100, 110, 120, 130, 140, 150, 160, 170, 180]
): TerrainElevationGrid => ({
  size: 3,
  center: [0.5, 0.5],
  bounds: { north: 1, south: 0, west: 0, east: 1 },
  sideLengthMeters: 1_440,
  cellSizeMeters: 720,
  elevationsMeters,
  minElevationMeters: Math.min(...elevationsMeters),
  maxElevationMeters: Math.max(...elevationsMeters),
});

const diagonalRoute: Coordinate[] = [
  [1, 0],
  [0, 1],
];

describe("terrainSceneModel", () => {
  test("usa escala vertical 1:1 y ubica la ruta con las alturas de la grilla", () => {
    const model = buildTerrainSceneModel(makeGrid(), diagonalRoute)!;

    expect(model.metersPerUnit).toBe(100);
    expect(model.maxHeight).toBeCloseTo(0.8, 9);
    expect(model.route[0]).toEqual({
      x: -TERRAIN_SCENE_HALF_SIZE,
      y: 0,
      z: -TERRAIN_SCENE_HALF_SIZE,
    });
    expect(model.route[1].x).toBeCloseTo(TERRAIN_SCENE_HALF_SIZE, 9);
    expect(model.route[1].y).toBeCloseTo(0.8, 9);
    expect(coordinateToTerrainScenePoint(model, [0.5, 0.5])?.y).toBeCloseTo(0.4, 9);
  });

  test("los vertices de la malla son las muestras reales y lo intermedio se interpola", () => {
    const grid = makeGrid();
    const model = buildTerrainSceneModel(grid, diagonalRoute)!;
    const exact = buildTerrainMeshData(model, 1);
    const exactHeights = exact.positions.filter((_, index) => index % 3 === 1);

    expect(exact.verticesPerSide).toBe(3);
    exactHeights.forEach((height, index) => {
      expect(height).toBeCloseTo((grid.elevationsMeters[index] - 100) / 100, 9);
    });

    const mesh = buildTerrainMeshData(model);
    const heights = mesh.positions.filter((_, index) => index % 3 === 1);
    const midpoint = 2 * mesh.verticesPerSide + 2;

    expect(mesh.verticesPerSide).toBe(9);
    expect(mesh.indices).toHaveLength(8 * 8 * 6);
    expect(heights[midpoint]).toBeCloseTo((120 - 100) / 100, 9);
    expect(Math.min(...heights)).toBeCloseTo(0, 9);
    expect(Math.max(...heights)).toBeCloseTo(0.8, 9);
    expect(Math.min(...mesh.relativeElevations)).toBe(0);
    expect(Math.max(...mesh.relativeElevations)).toBe(1);
  });

  test("apoya el trazado sobre el relieve real sin agregar alturas", () => {
    const model = buildTerrainSceneModel(makeGrid(), diagonalRoute)!;
    const draped = drapeRouteOnTerrain(model);

    expect(draped.length).toBeGreaterThan(2);
    expect(draped[0]).toEqual(model.route[0]);
    expect(draped.at(-1)!.y).toBeCloseTo(model.route[1].y, 9);
    draped.forEach((point) => {
      expect(point.y).toBeCloseTo(getTerrainSceneHeight(model, point.x, point.z), 9);
      expect(point.y).toBeGreaterThanOrEqual(0);
      expect(point.y).toBeLessThanOrEqual(model.maxHeight + 1e-9);
    });
  });

  test("sin datos reales completos no construye relieve", () => {
    expect(buildTerrainSceneModel(makeGrid([100, 110, Number.NaN, 130, 140, 150, 160, 170, 180]), diagonalRoute)).toBeNull();
    expect(buildTerrainSceneModel(makeGrid([100, 110, 120]), diagonalRoute)).toBeNull();
    expect(buildTerrainSceneModel(makeGrid(), [[0.5, 0.5]])).toBeNull();
    expect(buildTerrainSceneModel(makeGrid(), [[0.5, 0.5], [1.2, 0.5]])).toBeNull();
  });

  test("no usa azar al construir el modelo", () => {
    const random = jest.spyOn(Math, "random");
    const model = buildTerrainSceneModel(makeGrid(), diagonalRoute)!;
    buildTerrainMeshData(model);
    drapeRouteOnTerrain(model);

    expect(random).not.toHaveBeenCalled();
    random.mockRestore();
  });

  test("la escena 3D no contiene relieve, vegetacion ni ruta inventados", () => {
    const sources = ["../Terrain3DScene.tsx", "../terrainSceneModel.ts"].map((file) =>
      readFileSync(join(__dirname, file), "utf8")
    );

    sources.forEach((source) => {
      expect(source).not.toMatch(
        /Math\.random|hash01|fbm|noise|getTerrainElevationGainMeters|fallbackCenter|addVegetation|addGroundDetails/i
      );
    });
  });

  test("solo hay efectos de clima con un pronostico real", () => {
    expect(getTerrainWeatherKind(null)).toBeNull();
    expect(getTerrainWeatherKind(undefined)).toBeNull();
    expect(
      getTerrainWeatherKind({ condition: "Lluvia débil", rainProbability: 20, temperatureC: 8 })
    ).toBe("rain");
    expect(
      getTerrainWeatherKind({ condition: "Despejado", rainProbability: 0, temperatureC: 15 })
    ).toBe("clear");
  });
});
