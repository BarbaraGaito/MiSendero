import { initDB } from "../../database/database";
import {
  getRouteTrackingSummary,
  saveRouteTrackingPoint,
} from "../routeTracking";

describe("routeTracking", () => {
  beforeAll(async () => {
    await initDB();
  });

  test("stores GPS points and summarizes real distance", async () => {
    const startedAt = Date.now();

    await saveRouteTrackingPoint({
      trailId: 7,
      startedAt,
      latitude: -41.1,
      longitude: -71.1,
      accuracyMeters: 8,
      speedKmh: 4.2,
      distanceDeltaMeters: 0,
      recordedAt: startedAt,
      simulated: false,
    });
    await saveRouteTrackingPoint({
      trailId: 7,
      startedAt,
      latitude: -41.1005,
      longitude: -71.1005,
      accuracyMeters: 7,
      speedKmh: 4.4,
      distanceDeltaMeters: 70,
      recordedAt: startedAt + 10_000,
      simulated: false,
    });

    const summary = await getRouteTrackingSummary(7, startedAt);

    expect(summary.points).toBe(2);
    expect(summary.distanceMeters).toBe(70);
    expect(summary.lastPoint?.latitude).toBe(-41.1005);
    expect(summary.lastPoint?.simulated).toBe(false);
  });
});
