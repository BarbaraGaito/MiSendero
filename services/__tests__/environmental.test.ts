// All numerical values here are software fixtures, never scientific evidence.
jest.mock("../api", () => ({ getTrailEnvironmental: jest.fn() }));
jest.mock("../authSession", () => ({ getAuthSession: jest.fn().mockResolvedValue({ user: { id: 3 } }) }));
jest.mock("../../database/database", () => ({ initDB: jest.fn() }));
jest.mock("expo-crypto", () => ({
  CryptoDigestAlgorithm: { SHA256: "sha256" },
  digestStringAsync: async (_algorithm: string, text: string) => jest.requireActual("node:crypto").createHash("sha256").update(text).digest("hex"),
}));
jest.mock("expo-network", () => ({ getNetworkStateAsync: jest.fn() }));
jest.mock("../../database/connection", () => {
  const { DatabaseSync } = jest.requireActual("node:sqlite");
  const store = new DatabaseSync(":memory:");
  return { db: {
    execAsync: async (sql: string) => store.exec(sql),
    getAllAsync: async (sql: string, bindings: unknown[] = []) => store.prepare(sql).all(...bindings),
    getFirstAsync: async (sql: string, bindings: unknown[] = []) => store.prepare(sql).get(...bindings),
    runAsync: async (sql: string, bindings: unknown[] = []) => store.prepare(sql).run(...bindings),
  } };
});
jest.mock("../mapTileCache", () => ({
  downloadOfflineTilesForTrail: jest.fn(), getOfflineTileCoverageForTrail: jest.fn(), deleteOfflineTilesForTrail: jest.fn(),
}));

import { db } from "../../database/connection";
import * as api from "../api";
import * as auth from "../authSession";
import * as tiles from "../mapTileCache";
import * as Network from "expo-network";
import { getOfflineMapByTrailId, saveOfflineTrailMap } from "../offlineMaps";
import { getTrailEnvironmental } from "../environmental";
import { visibleSnapshots } from "../../backend/src/contracts/environmental";
import { Trail } from "../../types";

const { fixtureTrail, makeBatch } = require("../../testing/fixtures/environmental.cjs");
const trail = fixtureTrail as Trail;

beforeEach(async () => {
  await db.execAsync("DROP TABLE IF EXISTS offline_maps");
  jest.clearAllMocks();
  global.fetch = jest.fn().mockRejectedValue(new Error("offline")) as typeof fetch;
  (auth.getAuthSession as jest.Mock).mockResolvedValue({ user: { id: 3 } });
  (api.getTrailEnvironmental as jest.Mock).mockResolvedValue(makeBatch());
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: true, isInternetReachable: true });
  (tiles.downloadOfflineTilesForTrail as jest.Mock).mockResolvedValue({ sizeMb: 1 });
  (tiles.getOfflineTileCoverageForTrail as jest.Mock).mockResolvedValue({ isComplete: true, availableTiles: 2, totalTiles: 2 });
});

test("download persists a checked snapshot; network loss retains its raw checksum and dates", async () => {
  await saveOfflineTrailMap(trail);
  const saved = (await getOfflineMapByTrailId(trail.id))?.environmental;
  expect(saved).toEqual(makeBatch());
  (api.getTrailEnvironmental as jest.Mock).mockClear();
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: false });
  const offline = await getTrailEnvironmental(trail);
  expect(offline).toEqual({ batch: saved, mode: "offline", error: false });
  expect(api.getTrailEnvironmental).not.toHaveBeenCalled();
  const displayed = visibleSnapshots(offline.batch!, Date.parse("2026-10-22T16:00:00Z"));
  expect(displayed[1].status).toBe("expired");
  expect(displayed[1].prediction).toEqual(makeBatch().snapshots[1].prediction);
  expect((await getOfflineMapByTrailId(trail.id))?.environmental).toEqual(saved);
});

test("provider failure preserves a saved batch; reconnection refreshes it", async () => {
  await saveOfflineTrailMap(trail);
  (api.getTrailEnvironmental as jest.Mock).mockRejectedValue(new Error("provider failure"));
  expect((await getTrailEnvironmental(trail)).batch).toEqual(makeBatch());
  expect((await getTrailEnvironmental(trail)).mode).toBe("cached");
  (api.getTrailEnvironmental as jest.Mock).mockResolvedValue(makeBatch(trail, 2.34));
  expect((await getTrailEnvironmental(trail)).batch).toEqual(makeBatch(trail, 2.34));
  expect((await getOfflineMapByTrailId(trail.id))?.environmental).toEqual(makeBatch(trail, 2.34));
});

test("environmental failure does not prevent verified map download", async () => {
  (api.getTrailEnvironmental as jest.Mock).mockRejectedValue(new Error("provider failure"));
  expect((await saveOfflineTrailMap(trail))?.status).toBe("disponible");
  expect((await getOfflineMapByTrailId(trail.id))?.environmental).toBeNull();
});

test("a changed route, a corrupted payload and another account cannot reuse a forecast", async () => {
  await saveOfflineTrailMap(trail);
  expect((await getTrailEnvironmental({ ...trail, center_lat: -42 }, true)).batch).toBeNull();
  const corrupt = makeBatch();
  corrupt.snapshots[1].prediction.level_m = 999;
  await db.runAsync("UPDATE offline_maps SET environmental_json = ? WHERE trail_id = ?", [JSON.stringify(corrupt), trail.id]);
  expect((await getTrailEnvironmental(trail, true)).batch).toBeNull();
  (auth.getAuthSession as jest.Mock).mockResolvedValue({ user: { id: 4 } });
  expect(await getOfflineMapByTrailId(trail.id)).toBeNull();
  expect((await getTrailEnvironmental(trail, true)).batch).toBeNull();
});
