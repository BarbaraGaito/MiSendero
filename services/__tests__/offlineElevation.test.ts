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
import * as api from "../api";
import * as tiles from "../mapTileCache";
import * as auth from "../authSession";
import { getOfflineMapByTrailId, getVerifiedOfflineMapByTrailId, refreshOfflineTrailElevation, saveOfflineTrailMap } from "../offlineMaps";
import { Trail } from "../../types";

const trail: Trail = {
  id: 7, name: "Ruta", location: "Mendoza", difficulty: "Media",
  duration: null, distance_km: null, description: null, image_url: null,
  center_lat: -32, center_lng: -69, map_zoom: 12,
  route_coordinates: "[[-32,-69],[-32.01,-69]]", created_at: "2026-10-11",
};
const elevated: Trail = {
  ...trail,
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

beforeEach(async () => {
  await db.execAsync("DROP TABLE IF EXISTS offline_maps");
  jest.clearAllMocks();
  (auth.getAuthSession as jest.Mock).mockResolvedValue({ user: { id: 3 } });
  (api.getTrailById as jest.Mock).mockResolvedValue(elevated);
  (tiles.downloadOfflineTilesForTrail as jest.Mock).mockResolvedValue({ sizeMb: 1 });
  (tiles.getOfflineTileCoverageForTrail as jest.Mock).mockResolvedValue({ isComplete: true, availableTiles: 2, totalTiles: 2 });
});

test("persists all elevations in SQLite and reads them after network loss", async () => {
  await saveOfflineTrailMap(trail);
  (api.getTrailById as jest.Mock).mockRejectedValue(new Error("offline"));
  const local = await getOfflineMapByTrailId(7);
  expect(local?.trail?.elevation).toEqual(elevated.elevation);
  expect(local?.status).toBe("disponible");
  expect(api.getTrailById).toHaveBeenCalledTimes(1);
  expect((await getVerifiedOfflineMapByTrailId(7))?.trail?.elevation).toEqual(elevated.elevation);
});

test("tile failure still preserves elevation, without marking the map complete", async () => {
  (tiles.downloadOfflineTilesForTrail as jest.Mock).mockRejectedValue(new Error("tiles unavailable"));
  await expect(saveOfflineTrailMap(trail)).rejects.toThrow("tiles unavailable");
  expect((await getOfflineMapByTrailId(7))?.trail?.elevation).toEqual(elevated.elevation);
  expect((await getOfflineMapByTrailId(7))?.status).toBe("incompleto");
  expect(await getVerifiedOfflineMapByTrailId(7)).toBeNull();
});

test("downloaded trails retain their access, precautions, sources and photo attribution offline", async () => {
  const { provenance } = require("../../backend/src/data/additionalTrails")[0];
  await saveOfflineTrailMap({ ...elevated, provenance });
  (api.getTrailById as jest.Mock).mockRejectedValue(new Error("offline"));
  expect((await getOfflineMapByTrailId(7))?.trail?.provenance).toEqual(provenance);
});

test("missing elevation prevents an apparently complete offline download", async () => {
  (api.getTrailById as jest.Mock).mockResolvedValue(trail);
  await expect(saveOfflineTrailMap(trail)).rejects.toThrow("offline-elevation-unavailable");
  expect(tiles.downloadOfflineTilesForTrail).not.toHaveBeenCalled();
  expect(await getOfflineMapByTrailId(7)).toBeNull();
});

test("legacy maps gain a persisted profile without losing reports", async () => {
  await saveOfflineTrailMap(elevated, [{ id: 42 } as never]);
  await db.runAsync("UPDATE offline_maps SET trail_json = ? WHERE trail_id = ?", [JSON.stringify(trail), 7]);
  expect(await getVerifiedOfflineMapByTrailId(7)).toBeNull();
  expect(await refreshOfflineTrailElevation(elevated)).toEqual(elevated);
  expect((await getOfflineMapByTrailId(7))?.trail?.elevation).toEqual(elevated.elevation);
  expect((await getOfflineMapByTrailId(7))?.reports).toEqual([{ id: 42 }]);
});

test("a new geometry cannot overwrite the downloaded trace and its elevation", async () => {
  await saveOfflineTrailMap(elevated);
  expect(await refreshOfflineTrailElevation({ ...elevated, route_coordinates: "[[-32,-69],[-33,-69]]" })).toBeUndefined();
  expect((await getOfflineMapByTrailId(7))?.trail).toEqual(elevated);
});

test("institutional data is saved even when a refresh returns no elevation, preserving the existing DEM", async () => {
  await saveOfflineTrailMap({ ...elevated, national_park: null });
  const profile = require("../../backend/src/data/nationalParks").find((park: { slug: string }) => park.slug === "iguazu");
  const refreshed = { ...trail, national_park: profile, national_park_slug: "iguazu" };
  await refreshOfflineTrailElevation(refreshed);
  const saved = (await getOfflineMapByTrailId(7))?.trail;
  expect(saved?.national_park).toEqual(profile);
  expect(saved?.national_park_slug).toBe("iguazu");
  expect(saved?.elevation).toEqual(elevated.elevation);
  expect(saved?.route_coordinates).toBe(elevated.route_coordinates);
});

test("offline elevation is isolated by user", async () => {
  await saveOfflineTrailMap(elevated);
  (auth.getAuthSession as jest.Mock).mockResolvedValue({ user: { id: 99 } });
  expect(await getOfflineMapByTrailId(7)).toBeNull();
  expect(await refreshOfflineTrailElevation(elevated)).toBeUndefined();
});
