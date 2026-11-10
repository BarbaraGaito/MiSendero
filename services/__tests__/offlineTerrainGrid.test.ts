jest.mock("../api", () => ({ getTrailById: jest.fn() }));
jest.mock("../authSession", () => ({ getAuthSession: jest.fn().mockResolvedValue({ user: { id: 3 } }) }));
jest.mock("../../database/database", () => ({ initDB: jest.fn() }));
jest.mock("../../database/connection", () => {
  const { DatabaseSync } = jest.requireActual("node:sqlite");
  const store = new DatabaseSync(":memory:");
  return {
    db: {
      execAsync: async (sql: string) => store.exec(sql),
      getAllAsync: async (sql: string, bindings: unknown[] = []) => store.prepare(sql).all(...bindings),
      getFirstAsync: async (sql: string, bindings: unknown[] = []) => store.prepare(sql).get(...bindings),
      runAsync: async (sql: string, bindings: unknown[] = []) => store.prepare(sql).run(...bindings),
    },
  };
});
jest.mock("../mapTileCache", () => ({
  downloadOfflineTilesForTrail: jest.fn(),
  getOfflineTileCoverageForTrail: jest.fn(),
  deleteOfflineTilesForTrail: jest.fn(),
}));

import { db } from "../../database/connection";
import * as tiles from "../mapTileCache";
import * as auth from "../authSession";
import { backfillOfflineTerrainGrid, getOfflineMapByTrailId, getOfflineTerrainGrid, saveOfflineTrailMap } from "../offlineMaps";
import { parseRouteCoordinates } from "../geoUtils";
import {
  OPEN_METEO_ELEVATION_ATTRIBUTION,
  clearTerrainElevationCache,
  createTerrainGridCoordinates,
  getTerrainElevation,
} from "../terrainElevation";
import { loadTerrainElevationState } from "../../mobile/hooks/useTerrainElevation";
import { Trail } from "../../types";

const trail: Trail = {
  id: 7, name: "Ruta", location: "Mendoza", difficulty: "Media",
  duration: null, distance_km: null, description: null, image_url: null,
  center_lat: -32, center_lng: -69, map_zoom: 12,
  route_coordinates: "[[-32,-69],[-32.01,-69]]", created_at: "2026-10-11",
  elevation: {
    version: 1, geometry_hash: "test-geometry", source: "Copernicus DEM GLO-90 / Open-Meteo",
    source_url: "https://open-meteo.com/en/docs/elevation-api", resolution_m: 90,
    sample_spacing_m: 90, noise_threshold_m: 5, fetched_at: "2026-10-11",
    ascent_m: 50, descent_m: 0, min_m: 2000, max_m: 2050, distance_m: 1112,
    points: [
      { latitude: -32, longitude: -69, distance_m: 0, elevation_m: 2000 },
      { latitude: -32.01, longitude: -69, distance_m: 1112, elevation_m: 2050 },
    ],
  },
};
const route = parseRouteCoordinates(trail.route_coordinates);
const movedRouteJson = "[[-32,-69],[-32.02,-69.01]]";
const movedRoute = parseRouteCoordinates(movedRouteJson);

// Altura determinista por coordenada consultada: permite comprobar que lo
// guardado es exactamente lo que devolvio el proveedor.
const providerElevation = (latitude: string, longitude: string) =>
  Math.round((Math.abs(Number(latitude) * 7919 + Number(longitude) * 104729) % 3000) * 10) / 10;

const providerFetch = jest.fn(async (input: string) => {
  const url = new URL(input);
  const longitudes = url.searchParams.get("longitude")!.split(",");
  const elevation = url.searchParams
    .get("latitude")!
    .split(",")
    .map((latitude, index) => providerElevation(latitude, longitudes[index]));
  return { ok: true, status: 200, json: async () => ({ elevation }) };
});
const fetchMock = jest.fn();

const expectedGridElevations = (coordinates = route) =>
  createTerrainGridCoordinates(coordinates)!.coordinates.map(([latitude, longitude]) =>
    providerElevation(latitude.toFixed(6), longitude.toFixed(6)));

const storedTerrainJson = async () =>
  (await db.getFirstAsync<{ terrain_json: string | null }>(
    "SELECT terrain_json FROM offline_maps WHERE trail_id = 7"
  ))?.terrain_json;

// Build a legacy 3D cache explicitly; new base-map downloads never fetch a DEM.
const storeLegacyTerrain = async () => {
  await saveOfflineTrailMap(trail);
  const data = await getTerrainElevation(trail.id, route);
  if (data) await backfillOfflineTerrainGrid(trail.id, route, data);
  return getOfflineMapByTrailId(trail.id);
};

beforeAll(() => {
  global.fetch = fetchMock as unknown as typeof fetch;
});

beforeEach(async () => {
  await db.execAsync("DROP TABLE IF EXISTS offline_maps");
  clearTerrainElevationCache();
  jest.clearAllMocks();
  (auth.getAuthSession as jest.Mock).mockResolvedValue({ user: { id: 3 } });
  fetchMock.mockImplementation(providerFetch);
  (tiles.downloadOfflineTilesForTrail as jest.Mock).mockResolvedValue({ sizeMb: 1 });
  (tiles.getOfflineTileCoverageForTrail as jest.Mock).mockResolvedValue({ isComplete: true, availableTiles: 2, totalTiles: 2 });
});

test("legacy DEM grids keep their real source and geometry readable", async () => {
  const saved = await storeLegacyTerrain();

  expect(saved?.status).toBe("disponible");
  expect(saved?.terrain?.grid.size).toBe(createTerrainGridCoordinates(route)!.size);
  expect(saved?.terrain?.grid.elevationsMeters).toEqual(expectedGridElevations());
  expect(saved?.terrain).toMatchObject({
    version: 1,
    geometry_hash: "test-geometry",
    source: {
      provider: "Open-Meteo",
      dataset: "Copernicus DEM GLO-90",
      resolutionMeters: 90,
      attribution: OPEN_METEO_ELEVATION_ATTRIBUTION,
      fetchedAt: expect.any(String),
    },
  });
  // Solo grilla y fuente: no se duplica el perfil ni se guardan datos derivados.
  expect(Object.keys(saved!.terrain!).sort()).toEqual(["geometry_hash", "grid", "route_key", "source", "version"]);

  // La vista 3D en la misma sesion reutiliza la consulta de la descarga.
  const callsAfterDownload = fetchMock.mock.calls.length;
  expect((await loadTerrainElevationState(7, route, false)).status).toBe("ready");
  expect(fetchMock).toHaveBeenCalledTimes(callsAfterDownload);
});

test.each([
  ["a rejected request", () => Promise.reject(new Error("offline"))],
  ["an HTTP error", async () => ({ ok: false, status: 503, json: async () => ({}) })],
  ["missing DEM values", async (input: string) => ({
    ok: true,
    status: 200,
    json: async () => ({ elevation: new URL(input).searchParams.get("latitude")!.split(",").map(() => null) }),
  })],
])("an online 3D failure (%s) does not damage the downloaded basic map", async (_, failure) => {
  fetchMock.mockImplementation(failure);

  const saved = await saveOfflineTrailMap(trail);
  expect(fetchMock).not.toHaveBeenCalled();
  expect((await loadTerrainElevationState(7, route, false)).status).toBe("unavailable");

  expect(saved?.status).toBe("disponible");
  expect(saved?.trail?.elevation).toEqual(trail.elevation);
  expect(saved?.terrain).toBeNull();
  expect(await storedTerrainJson()).toBeNull();
  await expect(loadTerrainElevationState(7, route, true)).resolves.toEqual({
    status: "unavailable",
    reason: "offline",
  });
});

test("after a restart the persisted grid is used offline (and online) without calling the provider", async () => {
  const stored = (await storeLegacyTerrain())!.terrain;
  clearTerrainElevationCache();
  fetchMock.mockClear();
  const fetchFn = jest.fn();

  await expect(loadTerrainElevationState(7, route, true, fetchFn)).resolves.toEqual({ status: "ready", data: stored });
  await expect(loadTerrainElevationState(7, route, false, fetchFn)).resolves.toEqual({ status: "ready", data: stored });
  expect(fetchFn).not.toHaveBeenCalled();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("a route-geometry change invalidates the persisted grid", async () => {
  await storeLegacyTerrain();
  clearTerrainElevationCache();
  fetchMock.mockClear();

  expect(await getOfflineTerrainGrid(7, movedRoute)).toBeNull();
  await expect(loadTerrainElevationState(7, movedRoute, true)).resolves.toEqual({ status: "unavailable", reason: "offline" });

  // The downloaded profile now belongs to another geometry: the old grid no longer matches it.
  const moved = { ...trail, route_coordinates: movedRouteJson, elevation: { ...trail.elevation!, geometry_hash: "moved-geometry" } };
  await db.runAsync("UPDATE offline_maps SET trail_json = ? WHERE trail_id = 7", [JSON.stringify(moved)]);
  expect(await getOfflineTerrainGrid(7, route)).toBeNull();
  expect(await getOfflineTerrainGrid(7, movedRoute)).toBeNull();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("basic re-download preserves compatible legacy data without requesting elevations", async () => {
  const first = (await storeLegacyTerrain())!.terrain;
  clearTerrainElevationCache();
  fetchMock.mockClear();
  fetchMock.mockRejectedValue(new Error("offline"));

  expect((await saveOfflineTrailMap(trail))?.terrain).toEqual(first);

  const moved = { ...trail, route_coordinates: movedRouteJson, elevation: { ...trail.elevation!, geometry_hash: "moved-geometry" } };
  expect((await saveOfflineTrailMap(moved))?.terrain).toBeNull();
  expect(await storedTerrainJson()).toBeNull();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("viewing 3D online does not add terrain to a basic downloaded map", async () => {
  await saveOfflineTrailMap(trail);
  await db.runAsync("UPDATE offline_maps SET terrain_json = NULL WHERE trail_id = 7");
  clearTerrainElevationCache();

  // The view shows a different (updated) trace: nothing is written for the downloaded map.
  expect((await loadTerrainElevationState(7, movedRoute, false)).status).toBe("ready");
  expect(await storedTerrainJson()).toBeNull();

  const online = await loadTerrainElevationState(7, route, false);
  expect(online.status).toBe("ready");
  expect(await getOfflineTerrainGrid(7, route)).toBeNull();
  expect((await getOfflineMapByTrailId(7))?.reports).toEqual([]);

  clearTerrainElevationCache();
  fetchMock.mockClear();
  await expect(loadTerrainElevationState(7, route, true)).resolves.toEqual({ status: "unavailable", reason: "offline" });
  expect(fetchMock).not.toHaveBeenCalled();
});

test("the persisted grid is isolated by user", async () => {
  await storeLegacyTerrain();
  (auth.getAuthSession as jest.Mock).mockResolvedValue({ user: { id: 99 } });

  expect(await getOfflineTerrainGrid(7, route)).toBeNull();
});
