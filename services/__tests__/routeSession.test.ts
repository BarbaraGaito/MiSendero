jest.mock("expo-sms", () => ({ isAvailableAsync: jest.fn().mockResolvedValue(true), sendSMSAsync: jest.fn().mockResolvedValue({ result: "sent" }) }));

import { db, initDB } from "../../database/database";
import { saveAuthSession } from "../authSession";
import { activeRouteSeconds, ensureRouteSession, finishRouteSession, getActiveRouteSession, getRouteSession, getSimulatedRouteTrackingSummary, pauseRouteSession, resumeRouteSession, saveSimulatedRouteTrackingPoint } from "../routeSession";
import { getOrCreatePausedSession, getOrCreateCompletedSession } from "../../database/sessionsRepository";
import { saveEmergencyContact } from "../emergencyContact";
import { getDepartureMessage, sendDeparturePlanSms } from "../departureMessages";
import { saveTestingLocationMode } from "../testingMode";

const sendPlan = async (trailId: number) => {
  await saveEmergencyContact({ name: "Contacto", phone: "+5491112345678", relationship: "Familia" });
  await sendDeparturePlanSms({ trailId, contactPhone: "+5491112345678", expectedReturnAt: new Date(Date.now() + 3600000).toISOString(), messageBody: "Plan de regreso" }, async () => false);
};

const login = (id: number) => saveAuthSession({ token: `test-${id}`, user: { id, name: "Test", email: `${id}@example.test` } });
const startTestingMode = async (id: number) => {
  await saveAuthSession({ token: `test-${id}`, user: { id, name: "Test", email: `${id}@example.test`, role: "admin" } });
  await saveTestingLocationMode(true);
};
beforeAll(() => initDB());
beforeEach(async () => {
  await login(21);
  await saveTestingLocationMode(false);
  await getActiveRouteSession();
  await db.runAsync("DELETE FROM route_runtime");
  await db.runAsync("DELETE FROM sessions");
  await db.runAsync("DELETE FROM departure_messages");
});
afterEach(() => jest.restoreAllMocks());

test("pause/resume preserves identity and excludes multiple pauses from active time", async () => {
  const now = jest.spyOn(Date, "now").mockReturnValue(100000);
  await sendPlan(2);
  await ensureRouteSession(2, 100000);
  now.mockReturnValue(160000);
  await pauseRouteSession(2, 100000);
  now.mockReturnValue(220000);
  await pauseRouteSession(2, 100000); // duplicate must not reset pause start
  expect(activeRouteSeconds((await getRouteSession(2, 100000))!)).toBe(60);
  await resumeRouteSession(2, 100000);
  now.mockReturnValue(280000);
  await pauseRouteSession(2, 100000);
  now.mockReturnValue(340000);
  const done = await finishRouteSession(2, 100000);
  expect(activeRouteSeconds(done!)).toBe(120);
  await resumeRouteSession(2, 100000); // completed is terminal
  expect((await getRouteSession(2, 100000))?.state).toBe("completed");
  expect(await getActiveRouteSession()).toBeNull();
});

test("accounts cannot read or modify another active route", async () => {
  await sendPlan(3);
  await ensureRouteSession(3, 10000);
  await login(22);
  expect(await getActiveRouteSession()).toBeNull();
  await pauseRouteSession(3, 10000);
  await login(21);
  expect((await getRouteSession(3, 10000))?.state).toBe("running");
  await expect(ensureRouteSession(4, 20000)).rejects.toThrow("recorrido abierto");
});

test("an older periodic save cannot reopen a completed activity", async () => {
  await getOrCreatePausedSession({ trailId: 3, startedAt: 10000, duration: 20, distance: 100 });
  const completed = await getOrCreateCompletedSession({ trailId: 3, startedAt: 10000, endedAt: 50000, duration: 40, distance: 200, completionStatus: "ended_early" });
  const stale = await getOrCreatePausedSession({ trailId: 3, startedAt: 10000, duration: 25, distance: 120 });
  expect(stale.ended_at).toBe(completed.session.ended_at);
  expect(stale.distance).toBe(200);
});

test("a testing-location session lives only in memory and is never persisted", async () => {
  const now = jest.spyOn(Date, "now").mockReturnValue(500000);
  await sendPlan(6);
  await startTestingMode(21);
  expect((await ensureRouteSession(6, 500000, true))?.simulated).toBe(1);
  expect(await getActiveRouteSession()).toMatchObject({ trail_id: 6, started_at: 500000, state: "running" });
  saveSimulatedRouteTrackingPoint({ trailId: 6, startedAt: 500000, latitude: -41.1, longitude: -71.1,
    accuracyMeters: 0, speedKmh: 4, distanceDeltaMeters: 25, recordedAt: 503000, simulated: true });
  expect(getSimulatedRouteTrackingSummary(6, 500000)).toMatchObject({ points: 1, distanceMeters: 25 });
  await login(22);
  expect(await getActiveRouteSession()).toBeNull();
  await login(21);
  now.mockReturnValue(560000);
  await pauseRouteSession(6, 500000);
  now.mockReturnValue(620000);
  await resumeRouteSession(6, 500000);
  now.mockReturnValue(680000);
  expect(activeRouteSeconds((await finishRouteSession(6, 500000))!)).toBe(120);
  expect(await getActiveRouteSession()).toBeNull();
  const count = async (table: string) => (await db.getFirstAsync<{ count: number }>(`SELECT COUNT(*) AS count FROM ${table}`))?.count;
  expect(await count("route_runtime")).toBe(0);
  expect(await count("route_tracking_points")).toBe(0);
  expect(await count("sessions")).toBe(0);
  expect(await getDepartureMessage(6)).not.toBeNull(); // a test run does not consume the real plan
});
