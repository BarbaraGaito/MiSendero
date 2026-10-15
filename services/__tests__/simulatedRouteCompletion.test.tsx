jest.mock("expo-sms", () => ({ isAvailableAsync: jest.fn().mockResolvedValue(true), sendSMSAsync: jest.fn().mockResolvedValue({ result: "sent" }) }));
jest.mock("expo-network", () => ({ getNetworkStateAsync: jest.fn().mockResolvedValue({ isConnected: false }) }));
let mockParams: Record<string, string> = {};
jest.mock("expo-router", () => ({
  router: { push: jest.fn(), replace: jest.fn() },
  useLocalSearchParams: () => mockParams,
}));
jest.mock("@expo/vector-icons", () => ({ Ionicons: () => null }));
jest.mock("react-native-safe-area-context", () => ({
  SafeAreaView: require("react-native").View,
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

import React from "react";
import { db, initDB } from "../../database/database";
import { saveAuthSession } from "../authSession";
import { saveEmergencyContact } from "../emergencyContact";
import { sendDeparturePlanSms } from "../departureMessages";
import { ensureRouteSession, getActiveRouteSession, getRouteSession } from "../routeSession";
import { saveTestingLocationMode } from "../testingMode";
import RouteCompletedScreen from "../../mobile/screens/RouteCompletedScreen";

const renderer = require("react-test-renderer");

const sendPlan = async (trailId: number) => {
  await saveEmergencyContact({ name: "Contacto", phone: "+5491112345678", relationship: "Familia" });
  await sendDeparturePlanSms({ trailId, contactPhone: "+5491112345678", expectedReturnAt: new Date(Date.now() + 3600000).toISOString(), messageBody: "Plan de regreso" }, async () => false);
};
const count = async (sql: string) => (await db.getFirstAsync<{ count: number }>(sql))?.count;
const pendingActivities = () => count("SELECT COUNT(*) AS count FROM pending_operations WHERE entity_type = 'activity'");

const finishFromScreen = async (trailId: number, startedAt: number) => {
  mockParams = { id: String(trailId), startedAt: String(startedAt), traveledMeters: "1200", routeProgressMeters: "1200", totalMeters: "5000" };
  let screen: ReturnType<typeof renderer.create>;
  await renderer.act(async () => {
    screen = renderer.create(<RouteCompletedScreen />);
  });
  for (let attempt = 0; attempt < 100 && JSON.stringify(screen!.toJSON()).includes("Cargando resumen"); attempt += 1) {
    await renderer.act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
  }
  const text = JSON.stringify(screen!.toJSON());
  await renderer.act(async () => screen!.unmount());
  return text;
};

beforeAll(() => initDB());
beforeEach(async () => {
  await saveAuthSession({ token: "test-41", user: { id: 41, name: "Test", email: "41@example.test" } });
  await getActiveRouteSession();
  await db.runAsync("DELETE FROM route_runtime");
  await db.runAsync("DELETE FROM sessions");
  await db.runAsync("DELETE FROM departure_messages");
  await db.runAsync("DELETE FROM pending_operations");
  await saveTestingLocationMode(false);
});

test("a completed simulated session is shown as simulated but never stored nor queued as activity", async () => {
  const startedAt = Date.now() - 60000;
  // Testing-location mode (admin only): a test run needs no departure plan.
  await saveAuthSession({ token: "test-41", user: { id: 41, name: "Test", email: "41@example.test", role: "admin" } });
  await saveTestingLocationMode(true);
  await ensureRouteSession(8, startedAt, true);

  const text = await finishFromScreen(8, startedAt);

  expect(text).toContain("Recorrido simulado");
  expect((await getRouteSession(8, startedAt))?.state).toBe("completed");
  expect(await pendingActivities()).toBe(0);
  expect(await count("SELECT COUNT(*) AS count FROM sessions")).toBe(0);
  expect(await count("SELECT COUNT(*) AS count FROM route_runtime")).toBe(0);
});

test("a completed real session is still stored and queued for sync", async () => {
  const startedAt = Date.now() - 60000;
  await sendPlan(9);
  await ensureRouteSession(9, startedAt, false);

  const text = await finishFromScreen(9, startedAt);

  expect(text).not.toContain("Recorrido simulado");
  expect(await pendingActivities()).toBe(1);
  expect(await count("SELECT COUNT(*) AS count FROM sessions")).toBe(1);
});
