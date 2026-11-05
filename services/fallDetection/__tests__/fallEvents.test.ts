import { db, initDB } from "../../../database/database";
import { saveAuthSession } from "../../authSession";
import { eraseLocalAccountData } from "../../accountLifecycle";
import {
  answerFallEvent, closeStalePendingFallEvents, FALL_EVENT_RETENTION_DAYS, FallEventInput, getFallEvent, getFallSettings,
  listFallEvents, purgeOldFallEvents, saveFallEvent, saveFallSettings, subscribeFallSettings,
} from "../fallEvents";

const login = (id: number) => saveAuthSession({ token: `t-${id}`, user: { id, name: "Test", email: `${id}@example.test` } });
const event = (id: string, extra: Partial<FallEventInput> = {}): FallEventInput => ({
  id, detectedAt: Date.now(), trailId: 3, startedAt: 111, modelId: "m", modelVersion: "1-exp", score: 0.93, peakG: 2.7, ...extra });
beforeAll(() => initDB());

test("an event stores only what the spec lists, answers once, and is local to its account", async () => {
  await login(501);
  await saveFallEvent(event("a1"));
  await saveFallEvent(event("a1", { score: 0.1 }));                       // duplicate id is ignored
  expect(await getFallEvent("a1")).toMatchObject({ score: 0.93, userResponse: "pending", action: "none", latitude: null });
  expect(await answerFallEvent("a1", "help", "sos_opened", { latitude: -41.1, longitude: -71.3, recordedAt: 1234 })).toBe(true);
  expect(await answerFallEvent("a1", "ok", "dismissed")).toBe(false);
  expect(await getFallEvent("a1")).toMatchObject({ userResponse: "help", action: "sos_opened", latitude: -41.1, locationRecordedAt: 1234 });
  await login(502);
  expect(await getFallEvent("a1")).toBeNull();
  expect(await listFallEvents()).toEqual([]);
  expect(Object.keys((await db.getFirstAsync<Record<string, unknown>>("SELECT * FROM fall_detection_events LIMIT 1"))!).sort()).toEqual(
    ["action", "classification", "created_at", "detected_at", "id", "latitude", "location_recorded_at", "longitude", "model_id",
      "model_version", "peak_g", "responded_at", "score", "started_at", "trail_id", "user_id", "user_response"]);
});

test("events never enter the sync queue", async () => {
  await login(503);
  await saveFallEvent(event("q1"));
  const queued = await db.getFirstAsync<{ n: number }>("SELECT COUNT(*) AS n FROM pending_operations WHERE payload_json LIKE '%q1%'");
  expect(queued?.n).toBe(0);
});

test("a restart closes pending events as 'unanswered', never as 'ok'", async () => {
  await login(504);
  await saveFallEvent(event("s1"));
  await closeStalePendingFallEvents();
  expect(await getFallEvent("s1")).toMatchObject({ userResponse: "unanswered", action: "none" });
});

test("the preference is per account and defaults to off", async () => {
  await login(505);
  expect(await getFallSettings()).toEqual({ enabled: false, limitationsAcknowledgedAt: null });
  const listener = jest.fn();
  const off = subscribeFallSettings(listener);
  await saveFallSettings({ enabled: true, limitationsAcknowledgedAt: 99 });
  expect(listener).toHaveBeenCalledTimes(1);
  off();
  expect(await getFallSettings()).toEqual({ enabled: true, limitationsAcknowledgedAt: 99 });
  await login(506);
  expect(await getFallSettings()).toEqual({ enabled: false, limitationsAcknowledgedAt: null });
});

test("events older than the retention period are purged, recent ones stay", async () => {
  await login(507);
  await saveFallEvent(event("old"));
  await db.runAsync("UPDATE fall_detection_events SET created_at = ? WHERE id = 'old'", [Date.now() - (FALL_EVENT_RETENTION_DAYS + 1) * 86400000]);
  await saveFallEvent(event("new"));
  await purgeOldFallEvents();
  expect(await getFallEvent("old")).toBeNull();
  expect(await getFallEvent("new")).not.toBeNull();
});

test("deleting the account erases events and the preference", async () => {
  await login(508);
  await saveFallEvent(event("d1"));
  await saveFallSettings({ enabled: true, limitationsAcknowledgedAt: 1 });
  await eraseLocalAccountData(508);
  expect(await getFallEvent("d1")).toBeNull();
  expect(await getFallSettings()).toEqual({ enabled: false, limitationsAcknowledgedAt: null });
});
