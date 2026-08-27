import { Trail } from "../../types";

const trail: Trail = {
  id: 7,
  name: "Sendero de prueba",
  location: "Bariloche",
  difficulty: "Media",
  distance_km: 3.2,
  duration: "1 h",
  description: "Ruta de prueba",
  image_url: null,
  route_coordinates: JSON.stringify([
    [-41.1734, -71.4752],
    [-41.1718, -71.4698],
  ]),
  center_lat: -41.1734,
  center_lng: -71.4752,
  map_zoom: 10,
  created_at: "2026-08-27T00:00:00.000Z",
};

type FileRecord = { isDirectory: boolean; size?: number };

const loadMapTileCache = async ({
  downloadStatus = 200,
  tileSize = 512,
}: {
  downloadStatus?: number;
  tileSize?: number;
} = {}) => {
  jest.resetModules();

  const files = new Map<string, FileRecord>();
  const getInfoAsync = jest.fn(async (uri: string) => {
    const record = files.get(uri);

    if (!record) {
      return { exists: false, uri, isDirectory: false };
    }

    if (record.isDirectory) {
      return { exists: true, uri, isDirectory: true };
    }

    return {
      exists: true,
      uri,
      isDirectory: false,
      size: record.size ?? 0,
    };
  });
  const makeDirectoryAsync = jest.fn(async (uri: string) => {
    files.set(uri, { isDirectory: true });
  });
  const deleteAsync = jest.fn(async (uri: string) => {
    files.delete(uri);
  });
  const moveAsync = jest.fn(async ({ from, to }: { from: string; to: string }) => {
    const record = files.get(from);

    if (!record) {
      throw new Error("source-not-found");
    }

    files.set(to, record);
    files.delete(from);
  });
  const downloadAsync = jest.fn(async (_url: string, uri: string) => {
    files.set(uri, { isDirectory: false, size: tileSize });
    return { uri, status: downloadStatus, headers: {} };
  });

  jest.doMock("expo-file-system/legacy", () => ({
    documentDirectory: "file:///documents/",
    getInfoAsync,
    makeDirectoryAsync,
    deleteAsync,
    moveAsync,
    downloadAsync,
  }));

  const module = require("../mapTileCache") as typeof import("../mapTileCache");

  return {
    ...module,
    deleteAsync,
    downloadAsync,
    files,
    getInfoAsync,
    makeDirectoryAsync,
    moveAsync,
  };
};

describe("mapTileCache", () => {
  test("descarga todos los tiles a archivos locales verificables", async () => {
    const cache = await loadMapTileCache();
    const progress: Array<[number, number]> = [];

    const result = await cache.downloadOfflineTilesForTrail(trail, (downloaded, total) => {
      progress.push([downloaded, total]);
    });

    expect(result.totalTiles).toBeGreaterThan(0);
    expect(result.downloadedTiles).toBe(result.totalTiles);
    expect(cache.downloadAsync).toHaveBeenCalledTimes(result.totalTiles);
    expect(progress.at(-1)).toEqual([result.totalTiles, result.totalTiles]);

    const coverage = await cache.getOfflineTileCoverageForTrail(trail);
    expect(coverage).toMatchObject({
      availableTiles: result.totalTiles,
      totalTiles: result.totalTiles,
      isComplete: true,
    });
  });

  test("no usa archivos corruptos como tiles descargados", async () => {
    const cache = await loadMapTileCache({ tileSize: 48 });

    await expect(cache.downloadOfflineTilesForTrail(trail)).rejects.toMatchObject({
      code: "tile-download-failed",
    });

    const temporaryFiles = Array.from(cache.files.keys()).filter((uri) =>
      uri.endsWith(".download")
    );
    const coverage = await cache.getOfflineTileCoverageForTrail(trail);

    expect(temporaryFiles).toHaveLength(0);
    expect(coverage.isComplete).toBe(false);
    expect(coverage.availableTiles).toBe(0);
  });

  test("rechaza respuestas HTTP fallidas y limpia el archivo temporal", async () => {
    const cache = await loadMapTileCache({ downloadStatus: 503 });

    await expect(cache.downloadOfflineTilesForTrail(trail)).rejects.toMatchObject({
      code: "tile-download-failed",
      details: expect.objectContaining({
        downloadedTiles: 0,
        totalTiles: expect.any(Number),
      }),
    });

    expect(Array.from(cache.files.keys()).some((uri) => uri.endsWith(".download"))).toBe(false);
  });

  test("permite cancelar una descarga entre tiles sin guardar archivos temporales", async () => {
    const cache = await loadMapTileCache();
    let shouldCancel = false;

    await expect(
      cache.downloadOfflineTilesForTrail(
        trail,
        (downloaded) => {
          if (downloaded >= 1) shouldCancel = true;
        },
        { shouldCancel: () => shouldCancel }
      )
    ).rejects.toMatchObject({
      code: "download-cancelled",
    });

    expect(Array.from(cache.files.keys()).some((uri) => uri.endsWith(".download"))).toBe(false);
  });

  test("elimina los tiles offline asociados a una ruta", async () => {
    const cache = await loadMapTileCache();
    const result = await cache.downloadOfflineTilesForTrail(trail);

    const deletedTiles = await cache.deleteOfflineTilesForTrail(trail);
    const coverage = await cache.getOfflineTileCoverageForTrail(trail);

    expect(deletedTiles).toBe(result.totalTiles);
    expect(coverage.availableTiles).toBe(0);
    expect(coverage.isComplete).toBe(false);
  });
});
