jest.mock("expo-sqlite", () => {
  const { DatabaseSync } = jest.requireActual("node:sqlite");
  const fs = jest.requireActual("node:fs");
  const path = jest.requireActual("node:path");
  const directory = fs.mkdtempSync(path.join(jest.requireActual("node:os").tmpdir(), "misendero-functional-"));
  const filename = path.join(directory, "fixture.sqlite");
  let connection = new DatabaseSync(filename);
  const adapter = {
    closeAsync: async () => {},
    execAsync: async (sql: string) => connection.exec(sql),
    runAsync: async (sql: string, args: unknown[] = []) => {
      const info = connection.prepare(sql).run(...args);
      return { lastInsertRowId: Number(info.lastInsertRowid), changes: info.changes };
    },
    getAllAsync: async (sql: string, args: unknown[] = []) => connection.prepare(sql).all(...args),
    getFirstAsync: async (sql: string, args: unknown[] = []) => connection.prepare(sql).get(...args) ?? null,
    withTransactionAsync: async (work: () => Promise<void>) => {
      connection.exec("BEGIN");
      try { await work(); connection.exec("COMMIT"); }
      catch (error) { connection.exec("ROLLBACK"); throw error; }
    },
  };
  return {
    openDatabaseAsync: async () => adapter,
    fixture: { filename, close: () => connection.close(), reopen: () => { connection = new DatabaseSync(filename); },
      cleanup: () => { connection.close(); fs.rmSync(filename); fs.rmdirSync(directory); } },
  };
});
jest.mock("../authSession", () => ({ getAuthSession: jest.fn().mockResolvedValue({ token: "fixture-901", user: { id: 901 } }) }));
jest.mock("expo-sms", () => ({ isAvailableAsync: jest.fn().mockResolvedValue(true), sendSMSAsync: jest.fn().mockResolvedValue({ result: "sent" }) }));
jest.mock("expo-network", () => ({ getNetworkStateAsync: jest.fn() }));
jest.mock("../api", () => ({ createTrailReport: jest.fn(), getTrailReports: jest.fn().mockResolvedValue([]), recommendTrail: jest.fn() }));
jest.mock("../mapTileCache", () => ({ downloadOfflineTilesForTrail: jest.fn(), getOfflineTileCoverageForTrail: jest.fn(), deleteOfflineTilesForTrail: jest.fn() }));
jest.mock("../terrainElevation", () => ({ getTerrainElevation: jest.fn().mockRejectedValue(new Error("DEM unavailable in fixture")) }));
import { db, initDB } from "../../database/database";
import { saveOfflineTrailMap, getVerifiedOfflineMapByTrailId, getOfflineMapByTrailId } from "../offlineMaps";
import { enqueue, runSync, getPendingOperations } from "../syncQueue";
import { ensureRouteSession, getActiveRouteSession, pauseRouteSession } from "../routeSession";
import { saveRouteTrackingPoint, getRouteTrackingSummary } from "../routeTracking";
import { saveEmergencyContact } from "../emergencyContact";
import { sendDeparturePlanSms } from "../departureMessages";
import { findRecommendedTrail } from "../trailAssistant";
import { saveExperienceProfile } from "../experienceProfile";
import * as Network from "expo-network";
import * as api from "../api";
import * as tiles from "../mapTileCache";
import type { Trail } from "../../types";
const { fixture } = require("expo-sqlite");
const startedAt = 1792231200000;
const trail: Trail = {
  id: 7, name: "Ruta funcional", location: "Fixture", difficulty: "Media", duration: null, distance_km: 1,
  description: null, image_url: null, center_lat: -32, center_lng: -69, map_zoom: 12,
  route_coordinates: "[[-32,-69],[-32.01,-69]]", created_at: "2026-10-17",
  elevation: { version: 1, geometry_hash: "fixture", source: "Fixture DEM", source_url: "https://example.test/dem", resolution_m: 90,
    sample_spacing_m: 90, noise_threshold_m: 5, fetched_at: "2026-10-17", ascent_m: 10, descent_m: 0, min_m: 1000, max_m: 1010, distance_m: 1112,
    points: [{ latitude: -32, longitude: -69, distance_m: 0, elevation_m: 1000 }, { latitude: -32.01, longitude: -69, distance_m: 1112, elevation_m: 1010 }] },
};
beforeEach(async () => {
  jest.clearAllMocks();
  jest.spyOn(Date, "now").mockReturnValue(startedAt + 60000);
  await initDB(); await getActiveRouteSession();
  for (const table of ["pending_operations", "route_runtime", "route_tracking_points", "sessions", "departure_messages", "offline_maps"]) await db.runAsync(`DELETE FROM ${table}`);
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: false, isInternetReachable: false });
  (tiles.downloadOfflineTilesForTrail as jest.Mock).mockResolvedValue({ sizeMb: 1 });
  (tiles.getOfflineTileCoverageForTrail as jest.Mock).mockResolvedValue({ isComplete: true, availableTiles: 2, totalTiles: 2 });
});
afterEach(() => jest.restoreAllMocks());
afterAll(() => fixture.cleanup());

test("MF05 committed route, points, report and map survive an independent Node process", async () => {
  await saveEmergencyContact({ name: "Fixture", phone: "+5491100000000", relationship: "Prueba" });
  await sendDeparturePlanSms({ trailId: 7, contactPhone: "+5491100000000", expectedReturnAt: new Date(startedAt + 3600000).toISOString(), messageBody: "Fixture" }, async () => false);
  await ensureRouteSession(7, startedAt);
  await saveRouteTrackingPoint({ trailId: 7, startedAt, latitude: -32, longitude: -69, accuracyMeters: 5, speedKmh: 3,
    distanceDeltaMeters: 8, recordedAt: startedAt + 3000, simulated: false });
  await pauseRouteSession(7, startedAt);
  await enqueue("trail_report", { trailId: 7, issue_summary: "Barro", observed_at: new Date(startedAt).toISOString() });
  await saveOfflineTrailMap(trail);
  fixture.close();
  try {
    const child = require("node:child_process").spawnSync(process.execPath,
      [require("node:path").resolve("testing/functional/persistence-reader.cjs"), require("node:path").basename(require("node:path").dirname(fixture.filename))], { encoding: "utf8", timeout: 30000 });
    expect({ exit: child.status, error: child.error?.message, stderr: child.status ? child.stderr : undefined }).toEqual({ exit: 0 });
    const recovered = JSON.parse(child.stdout);
    expect(recovered.session).toMatchObject({ user_id: 901, trail_id: 7, state: "paused", started_at: startedAt });
    expect(recovered.summary).toMatchObject({ points: 1, distanceMeters: 8 });
    expect(recovered.queued).toHaveLength(1);
    expect(recovered.queued[0].status).toBe("pending");
    expect(JSON.parse(recovered.queued[0].payload_json).issue_summary).toBe("Barro");
    expect(recovered.maps).toEqual([{ status: "disponible" }]);
    expect(recovered.otherAccount).toBeNull();
  } finally { fixture.reopen(); }
});

test("MF06 offline report remains pending until connectivity and API acknowledgement", async () => {
  const id = await enqueue("trail_report", { trailId: 7, issue_summary: "Barro", severity: "Media", trail_state: "Precaución" });
  expect(await runSync()).toEqual({ processed: 0, failed: 0 });
  expect(api.createTrailReport).not.toHaveBeenCalled();
  expect((await getPendingOperations()).find(item => item.id === id)?.status).toBe("pending");
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: true, isInternetReachable: true });
  (api.createTrailReport as jest.Mock).mockRejectedValueOnce(new Error("Connection lost"));
  expect(await runSync()).toEqual({ processed: 0, failed: 1 });
  expect((await getPendingOperations()).find(item => item.id === id)?.status).toBe("failed");
  await db.runAsync("UPDATE pending_operations SET next_attempt_at = 0 WHERE id = ?", [id]);
  (api.createTrailReport as jest.Mock).mockResolvedValueOnce({ id: 501 });
  expect(await runSync()).toEqual({ processed: 1, failed: 0 });
  expect(await db.getFirstAsync("SELECT status, server_id FROM pending_operations WHERE id = ?", [id])).toMatchObject({ status: "synced", server_id: 501 });
});

test("MF10 ENOSPC cannot advertise a downloaded map as usable", async () => {
  (tiles.downloadOfflineTilesForTrail as jest.Mock).mockRejectedValueOnce(Object.assign(new Error("ENOSPC: no space left on device"), { code: "ENOSPC" }));
  await expect(saveOfflineTrailMap(trail)).rejects.toThrow("ENOSPC");
  expect((await getOfflineMapByTrailId(7))?.status).toBe("incompleto");
  expect(await getVerifiedOfflineMapByTrailId(7)).toBeNull();
});

test("MF14 failed AI request leaves verified offline navigation and GPS persistence usable", async () => {
  await saveExperienceProfile({});
  await saveOfflineTrailMap(trail);
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: true, isInternetReachable: true });
  (api.recommendTrail as jest.Mock).mockRejectedValueOnce(new Error("AI provider unavailable"));
  await expect(findRecommendedTrail({ destination: "Fixture", trailTypes: ["lagos"], duration: "1-2", difficulty: "facil" })).rejects.toThrow("AI provider unavailable");
  expect((await getVerifiedOfflineMapByTrailId(7))?.trail?.route_coordinates).toBe(trail.route_coordinates);
  await saveRouteTrackingPoint({ trailId: 7, startedAt, latitude: -32, longitude: -69, accuracyMeters: 5, speedKmh: 3,
    distanceDeltaMeters: 8, recordedAt: startedAt + 3000, simulated: false });
  expect((await getRouteTrackingSummary(7, startedAt)).distanceMeters).toBe(8);
});
