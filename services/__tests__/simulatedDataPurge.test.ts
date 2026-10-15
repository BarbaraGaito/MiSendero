jest.mock("expo-sms", () => ({ isAvailableAsync: jest.fn(), sendSMSAsync: jest.fn() }));

import { db, initDB, purgeSimulatedData } from "../../database/database";
import { saveAuthSession } from "../authSession";
import { getActiveRouteSession } from "../routeSession";

const rows = <T,>(sql: string) => db.getAllAsync<T>(sql);

beforeAll(async () => {
  await initDB();
  await saveAuthSession({ token: "test-51", user: { id: 51, name: "Test", email: "51@example.test" } });
  await getActiveRouteSession(); // creates route_runtime
});

test("removes simulator data persisted by older versions and keeps real data", async () => {
  await db.runAsync(
    `INSERT INTO wearable_metric_samples (user_id, provider, heart_rate_bpm, recorded_at, created_at)
     VALUES (51, 'development_simulator', 190, 1, 1), (51, 'apple_healthkit', 80, 2, 2)`
  );
  await db.runAsync(
    `INSERT INTO wearable_connections (user_id, provider, linked, permissions_granted, updated_at)
     VALUES (51, 'development_simulator', 1, 1, 1), (52, 'apple_healthkit', 1, 1, 1)`
  );
  // Session 1: simulated (flagged route_runtime). Session 2: simulated (synthetic points). Session 3: real.
  await db.runAsync(
    `INSERT INTO sessions (id, user_id, started_at, ended_at, duration, distance, avg_fatigue, trail_id, completion_status)
     VALUES (1, 51, 1000, 2000, 60, 500, 'bajo', 7, 'completed'), (2, 51, 3000, 4000, 60, 500, 'bajo', 7, 'completed'),
            (3, 51, 5000, 6000, 60, 500, 'bajo', 7, 'completed')`
  );
  await db.runAsync(
    `INSERT INTO route_runtime (user_id, trail_id, started_at, state, simulated) VALUES
     (51, 7, 1000, 'completed', 1), (51, 7, 5000, 'completed', 0)`
  );
  await db.runAsync(
    `INSERT INTO route_tracking_points (user_id, trail_id, started_at, latitude, longitude, distance_delta_meters, recorded_at, simulated, created_at)
     VALUES (51, 7, 3000, -41, -71, 10, 3100, 1, 3100), (51, 7, 5000, -41, -71, 10, 5100, 0, 5100)`
  );
  await db.runAsync(
    `INSERT INTO pending_operations (entity_type, payload_json, dedupe_key, user_id, status, created_at, updated_at) VALUES
     ('activity', '{}', '51:activity:local-session-1', 51, 'pending', 1, 1),
     ('activity', '{}', '51:activity:local-session-2', 51, 'failed', 1, 1),
     ('activity', '{}', '51:activity:local-session-3', 51, 'pending', 1, 1)`
  );

  await db.execAsync("CREATE TABLE IF NOT EXISTS heart_rate_logs (id INTEGER PRIMARY KEY, hr INTEGER)");

  await purgeSimulatedData();

  expect(await rows("SELECT provider FROM wearable_metric_samples")).toEqual([{ provider: "apple_healthkit" }]);
  expect(await rows("SELECT provider FROM wearable_connections")).toEqual([{ provider: "apple_healthkit" }]);
  expect(await rows("SELECT id, avg_fatigue FROM sessions")).toEqual([{ id: 3, avg_fatigue: null }]);
  expect(await rows("SELECT name FROM sqlite_master WHERE name = 'heart_rate_logs'")).toEqual([]);
  expect(await rows("SELECT dedupe_key FROM pending_operations")).toEqual([{ dedupe_key: "51:activity:local-session-3" }]);
  expect(await rows("SELECT simulated FROM route_tracking_points")).toEqual([{ simulated: 0 }]);
  expect(await rows("SELECT simulated FROM route_runtime")).toEqual([{ simulated: 0 }]);
});
