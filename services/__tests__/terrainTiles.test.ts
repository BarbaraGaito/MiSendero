import { encode } from "fast-png";
import type { Coordinate } from "../geoUtils";
import { createTerrainGridCoordinates } from "../terrainElevation";
import { buildTerrainSceneModel } from "../../mobile/components/terrainSceneModel";
import {
  TERRAIN_TILES_URL, clearTerrainTileCache, getTerrainTileGrid, peekTerrainTileGrid,
  type TerrainTileFetch,
} from "../terrainTiles";

// A real PNG encoding a known height, including its fractional metre.
const png = encode({ width: 256, height: 256, channels: 3,
  data: Uint8Array.from({ length: 256 * 256 * 3 }, (_, index) => [132, 210, 128][index % 3]) });
const okResponse = () => ({ ok: true, status: 200,
  arrayBuffer: async () => new Uint8Array(png).buffer });
const route: Coordinate[] = [[-32.824, -69.941], [-32.759, -69.968]];

beforeEach(() => clearTerrainTileCache());

test("loads a full 33x33 DEM from at most nine tiles instead of 1089 API locations", async () => {
  let active = 0, peak = 0;
  const fetchFn = jest.fn(async (url: string) => {
    expect(url.startsWith(TERRAIN_TILES_URL + "/")).toBe(true);
    active += 1; peak = Math.max(peak, active);
    await Promise.resolve(); active -= 1;
    return okResponse();
  }) as jest.MockedFunction<TerrainTileFetch>;
  const data = await getTerrainTileGrid(1, route, fetchFn);
  expect(data?.grid.size).toBe(33);
  expect(data?.grid.elevationsMeters).toHaveLength(1089);
  expect(new Set(data?.grid.elevationsMeters)).toEqual(new Set([1234.5]));
  expect(data?.source).toMatchObject({ provider: "AWS Terrain Tiles", dataset: "Mapzen Terrain Tiles" });
  expect(fetchFn.mock.calls.length).toBeLessThanOrEqual(9);
  expect(peak).toBeLessThanOrEqual(3);
  expect(buildTerrainSceneModel(data!.grid, route)).not.toBeNull();
});

test("samples the PNG's northern row first and preserves the longitude direction", async () => {
  const ramp = encode({ width: 256, height: 256, channels: 3,
    data: Uint8Array.from({ length: 256 * 256 * 3 }, (_, index) => {
      const pixel = Math.floor(index / 3);
      const value = 32768 + Math.floor(pixel / 256) + (pixel % 256) / 256;
      return [Math.floor(value / 256), Math.floor(value % 256), Math.round((value % 1) * 256)][index % 3];
    }) });
  // Entire grid is contained in one tile, away from the equator/tile edges.
  const local: Coordinate[] = [[-41.15, -71.35], [-41.149, -71.349]];
  const geometry = createTerrainGridCoordinates(local)!;
  const data = await getTerrainTileGrid(2, local, async () => ({ ok: true, status: 200,
    arrayBuffer: async () => new Uint8Array(ramp).buffer }));
  const size = geometry.size;
  expect(data).not.toBeNull();
  const heights = data!.grid.elevationsMeters;
  expect(heights[0]).toBeLessThan(heights[(size - 1) * size]);
  expect(heights[0]).toBeLessThan(heights[size - 1]);
});

test("shares in-flight grids and adjacent tiles across different trail IDs", async () => {
  const fetchFn = jest.fn(async () => okResponse());
  const first = getTerrainTileGrid(3, route, fetchFn);
  expect(getTerrainTileGrid(3, route, fetchFn)).toBe(first);
  const data = await first;
  const count = fetchFn.mock.calls.length;
  const adjacent = await getTerrainTileGrid(4, route, fetchFn);
  expect(adjacent?.grid).toEqual(data?.grid);
  expect(fetchFn).toHaveBeenCalledTimes(count);
  await expect(peekTerrainTileGrid(3, route)).resolves.toBe(data);
});

test("a failed download does not poison the cache or fabricate a flat surface", async () => {
  const local: Coordinate[] = [[0.01, 0.01], [0.011, 0.011]];
  const fetchFn = jest.fn(async () => okResponse())
    .mockResolvedValueOnce({ ok: false, status: 503, arrayBuffer: async () => new ArrayBuffer(0) });
  await expect(getTerrainTileGrid(5, local, fetchFn)).resolves.toBeNull();
  expect(peekTerrainTileGrid(5, local)).toBeNull();
  await expect(getTerrainTileGrid(5, local, fetchFn)).resolves.toMatchObject({ grid: { size: 17 } });
});

test.each(["corrupt", "transparent", "wrong-size"])("rejects %s DEM data", async (kind) => {
  const bytes = kind === "corrupt" ? new Uint8Array([1, 2, 3]) : kind === "wrong-size"
    ? encode({ width: 1, height: 1, channels: 3, data: new Uint8Array([132, 210, 128]) })
    : encode({ width: 256, height: 256, channels: 4, data: new Uint8Array(256 * 256 * 4) });
  await expect(getTerrainTileGrid(6, route, async () => ({ ok: true, status: 200,
    arrayBuffer: async () => new Uint8Array(bytes).buffer }))).resolves.toBeNull();
});

test("invalid routes do not make a network request", async () => {
  const fetchFn = jest.fn(async () => okResponse());
  await expect(getTerrainTileGrid(7, [], fetchFn)).resolves.toBeNull();
  await expect(getTerrainTileGrid(7, [[89.5, 0], [89.6, 1]], fetchFn)).resolves.toBeNull();
  expect(fetchFn).not.toHaveBeenCalled();
});

test("aborts a stalled tile download instead of leaving the map loading forever", async () => {
  jest.useFakeTimers();
  try {
    const fetchFn: TerrainTileFetch = (_url, init) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new Error("aborted")));
    });
    const request = getTerrainTileGrid(8, [[0.01, 0.01], [0.011, 0.011]], fetchFn);
    await jest.advanceTimersByTimeAsync(15000);
    await expect(request).resolves.toBeNull();
  } finally { jest.useRealTimers(); }
});
