import type { Coordinate } from "../geoUtils";
import {
  ElevationFetch,
  TERRAIN_DIFFICULTY_COLORS,
  TERRAIN_ELEVATION_BATCH_SIZE,
  TERRAIN_GRID_SIZE,
  TERRAIN_PROFILE_MAX_POINTS,
  TERRAIN_PROFILE_MIN_POINTS,
  TerrainElevationGrid,
  buildElevationProfile,
  buildTerrainElevationCacheKey,
  buildTerrainSectors,
  buildTerrainSegments,
  calculateElevationStatistics,
  classifyTerrainDifficulty,
  clearTerrainElevationCache,
  createTerrainGridCoordinates,
  fetchElevationsForCoordinates,
  getTerrainElevation,
  peekTerrainElevation,
  sampleRouteByDistance,
  sampleTerrainGridElevation,
  smoothElevationSeries,
} from "../terrainElevation";

describe("terrainElevation", () => {
  beforeEach(() => {
    clearTerrainElevationCache();
  });

  test("muestrea toda la ruta por distancia entre 32 y 96 puntos", () => {
    const shortRoute: Coordinate[] = [
      [-41, -71],
      [-41.01, -71],
    ];
    const longRoute: Coordinate[] = [
      [-41, -71],
      [-41.25, -71],
    ];
    const shortSamples = sampleRouteByDistance(shortRoute);
    const longSamples = sampleRouteByDistance(longRoute);

    expect(shortSamples).toHaveLength(TERRAIN_PROFILE_MIN_POINTS);
    expect(longSamples).toHaveLength(TERRAIN_PROFILE_MAX_POINTS);
    expect(shortSamples[0].coordinate).toEqual(shortRoute[0]);
    expect(shortSamples.at(-1)?.coordinate[0]).toBeCloseTo(shortRoute[1][0], 6);
    expect(shortSamples.at(-1)?.coordinate[1]).toBeCloseTo(shortRoute[1][1], 6);

    const gaps = shortSamples.slice(1).map(
      (sample, index) => sample.distanceMeters - shortSamples[index].distanceMeters
    );
    expect(Math.max(...gaps) - Math.min(...gaps)).toBeLessThan(0.01);
  });

  test("crea una grilla cuadrada 17x17 con margen alrededor de la ruta", () => {
    const route: Coordinate[] = [
      [-41.01, -71.02],
      [-41, -71],
      [-40.99, -70.98],
    ];
    const grid = createTerrainGridCoordinates(route);

    expect(grid).not.toBeNull();
    expect(grid?.size).toBe(TERRAIN_GRID_SIZE);
    expect(grid?.coordinates).toHaveLength(TERRAIN_GRID_SIZE ** 2);
    expect(grid?.cellSizeMeters).toBeCloseTo(
      (grid?.sideLengthMeters ?? 0) / (TERRAIN_GRID_SIZE - 1),
      6
    );
    expect(grid?.sideLengthMeters).toBeGreaterThanOrEqual(1_440);

    route.forEach(([latitude, longitude]) => {
      expect(latitude).toBeLessThanOrEqual(grid!.bounds.north);
      expect(latitude).toBeGreaterThanOrEqual(grid!.bounds.south);
      expect(longitude).toBeLessThanOrEqual(grid!.bounds.east);
      expect(longitude).toBeGreaterThanOrEqual(grid!.bounds.west);
    });
  });

  test("suaviza el perfil y calcula desnivel, pendiente y sectores sin inventar muestras", () => {
    const smoothed = smoothElevationSeries([100, 100, 200, 100, 100]);
    expect(smoothed).toHaveLength(5);
    expect(smoothed[2]).toBeGreaterThan(100);
    expect(smoothed[2]).toBeLessThan(200);

    const coordinates: Coordinate[] = [
      [-41, -71],
      [-40.9991, -71],
      [-40.9982, -71],
      [-40.9973, -71],
    ];
    const profile = coordinates.map((coordinate, index) => ({
      coordinate,
      distanceMeters: index * 100,
      rawElevationMeters: [100, 110, 130, 120][index],
      elevationMeters: [100, 110, 130, 120][index],
    }));
    const segments = buildTerrainSegments(profile);
    const sectors = buildTerrainSectors(segments);
    const statistics = calculateElevationStatistics(profile, segments);

    expect(segments.map((segment) => segment.level)).toEqual([
      "moderado",
      "exigente",
      "moderado",
    ]);
    expect(segments[2].direction).toBe("descenso");
    expect(sectors).toHaveLength(3);
    expect(statistics).toMatchObject({
      totalDistanceMeters: 300,
      elevationGainMeters: 30,
      elevationLossMeters: 10,
      minElevationMeters: 100,
      maxElevationMeters: 130,
      maxGradePercent: 20,
    });
  });

  test("expone niveles y colores estables para pintar los tramos", () => {
    expect(classifyTerrainDifficulty(4)).toBe("suave");
    expect(classifyTerrainDifficulty(-10)).toBe("moderado");
    expect(classifyTerrainDifficulty(20)).toBe("exigente");
    expect(classifyTerrainDifficulty(-30)).toBe("extremo");
    expect(TERRAIN_DIFFICULTY_COLORS.extremo).toMatch(/^#/);
  });

  test("consulta perfil y grilla en lotes de hasta 100 y reutiliza el cache", async () => {
    const batchSizes: number[] = [];
    const fetchFn = jest.fn(async (input: string) => {
      const url = new URL(input);
      const latitudes = decodeURIComponent(
        url.searchParams.get("latitude") ?? ""
      )
        .split(",")
        .filter(Boolean)
        .map(Number);
      const longitudes = decodeURIComponent(
        url.searchParams.get("longitude") ?? ""
      )
        .split(",")
        .filter(Boolean)
        .map(Number);
      batchSizes.push(latitudes.length);

      return {
        ok: true,
        status: 200,
        json: async () => ({
          elevation: latitudes.map(
            (latitude, index) =>
              1_000 + latitude * 4 + (longitudes[index] ?? 0) * 2
          ),
        }),
      };
    }) as ElevationFetch;
    const route: Coordinate[] = [
      [-41.01, -71.01],
      [-41, -71],
    ];
    const options = {
      fetchFn,
      now: () => new Date("2026-09-29T12:00:00.000Z"),
    };
    const first = await getTerrainElevation(7, route, options);
    const callsAfterFirstRequest = jest.mocked(fetchFn).mock.calls.length;
    const second = await getTerrainElevation(7, route, options);

    expect(first).not.toBeNull();
    expect(second).toBe(first);
    expect(first?.profile).toHaveLength(TERRAIN_PROFILE_MIN_POINTS);
    expect(first?.grid.elevationsMeters).toHaveLength(TERRAIN_GRID_SIZE ** 2);
    expect(first?.source).toMatchObject({
      provider: "Open-Meteo",
      dataset: "Copernicus DEM GLO-90",
      resolutionMeters: 90,
      fetchedAt: "2026-09-29T12:00:00.000Z",
    });
    expect(fetchFn).toHaveBeenCalledTimes(callsAfterFirstRequest);
    expect(batchSizes.length).toBeGreaterThan(1);
    expect(Math.max(...batchSizes)).toBeLessThanOrEqual(
      TERRAIN_ELEVATION_BATCH_SIZE
    );
    expect(batchSizes.reduce((total, size) => total + size, 0)).toBe(
      TERRAIN_PROFILE_MIN_POINTS + TERRAIN_GRID_SIZE ** 2
    );
  });

  test("interpola bilinealmente una elevacion dentro de la grilla", () => {
    const elevationsMeters = Array.from(
      { length: TERRAIN_GRID_SIZE ** 2 },
      (_, index) => {
        const row = Math.floor(index / TERRAIN_GRID_SIZE);
        const column = index % TERRAIN_GRID_SIZE;
        return row * 10 + column;
      }
    );
    const grid: TerrainElevationGrid = {
      size: TERRAIN_GRID_SIZE,
      center: [0.5, 0.5],
      bounds: { north: 1, south: 0, west: 0, east: 1 },
      sideLengthMeters: 1_600,
      cellSizeMeters: 100,
      elevationsMeters,
      minElevationMeters: 0,
      maxElevationMeters: 176,
    };

    expect(sampleTerrainGridElevation(grid, [0.5, 0.5])).toBeCloseTo(88, 6);
    expect(
      sampleTerrainGridElevation(grid, [1 - 8.5 / 16, 8.5 / 16])
    ).toBeCloseTo(93.5, 6);
    expect(sampleTerrainGridElevation(grid, [1.1, 0.5])).toBeNull();
  });

  test("retorna null ante fallos y no deja el fallo fijado en cache", async () => {
    const fetchFn = jest.fn(async () => ({
      ok: false,
      status: 503,
      json: async () => ({}),
    })) as ElevationFetch;
    const route: Coordinate[] = [
      [-41.01, -71.01],
      [-41, -71],
    ];

    await expect(getTerrainElevation("falla", route, { fetchFn })).resolves.toBeNull();
    await expect(getTerrainElevation("falla", route, { fetchFn })).resolves.toBeNull();
    expect(fetchFn).toHaveBeenCalledTimes(2);
  });

  test("peek solo lee el cache y nunca consulta al proveedor", async () => {
    const fetchFn = jest.fn(async (input: string) => {
      const count = new URL(input).searchParams.get("latitude")!.split(",").length;
      return {
        ok: true,
        status: 200,
        json: async () => ({ elevation: Array.from({ length: count }, () => 900) }),
      };
    }) as ElevationFetch;
    const route: Coordinate[] = [
      [-41.01, -71.01],
      [-41, -71],
    ];

    expect(peekTerrainElevation(9, route)).toBeNull();
    expect(fetchFn).not.toHaveBeenCalled();

    const loaded = await getTerrainElevation(9, route, { fetchFn });
    const calls = jest.mocked(fetchFn).mock.calls.length;

    await expect(peekTerrainElevation(9, route)).resolves.toBe(loaded);
    expect(fetchFn).toHaveBeenCalledTimes(calls);
  });

  test("la consulta de bajo nivel rechaza respuestas incompletas", async () => {
    const fetchFn = jest.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ elevation: [1] }),
    })) as ElevationFetch;

    await expect(
      fetchElevationsForCoordinates(
        [
          [-41, -71],
          [-40.99, -71],
        ],
        { fetchFn }
      )
    ).rejects.toMatchObject({ code: "invalid-response" });
  });

  test("el perfil y la clave cambian cuando cambia la geometria", () => {
    const routeA: Coordinate[] = [
      [-41, -71],
      [-40.99, -71],
    ];
    const routeB: Coordinate[] = [
      [-41, -71],
      [-40.98, -71],
    ];
    const samples = sampleRouteByDistance(routeA);
    const profile = buildElevationProfile(
      samples,
      samples.map((_, index) => 800 + index)
    );

    expect(profile).toHaveLength(samples.length);
    expect(buildTerrainElevationCacheKey(1, routeA)).not.toBe(
      buildTerrainElevationCacheKey(1, routeB)
    );
  });
});
