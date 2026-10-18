jest.mock("expo-sms", () => ({ isAvailableAsync: jest.fn().mockResolvedValue(true), sendSMSAsync: jest.fn().mockResolvedValue({ result: "sent" }) }));
// Instrumented native component initialization can exceed Jest's default budget.
// This is a runner timeout, not a product latency assertion.
jest.setTimeout(30000);
jest.mock("expo-battery", () => ({ getBatteryLevelAsync: jest.fn().mockResolvedValue(0.9) }));
jest.mock("expo-router", () => ({
  router: { push: jest.fn(), replace: jest.fn(), back: jest.fn() },
  useLocalSearchParams: () => ({ id: "9" }),
  useFocusEffect: (effect: () => void | (() => void)) => require("react").useEffect(effect, [effect]),
}));
jest.mock("@expo/vector-icons", () => ({ Ionicons: () => null }));
jest.mock("react-native-safe-area-context", () => ({
  SafeAreaView: require("react-native").View,
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
let mockTestingLocation = false;
jest.mock("../../hooks/useDeviceLocation", () => ({
  useDeviceLocation: () => ({ location: null, isLoading: false, permissionDenied: false, error: null, isTestingLocation: mockTestingLocation }),
}));
jest.mock("../../../services/offlineMaps", () => ({ getVerifiedOfflineMapByTrailId: jest.fn().mockResolvedValue(null) }));
jest.mock("../../../services/trailRepository", () => ({
  getTrailById: jest.fn().mockResolvedValue({ id: 9, name: "Sendero de prueba", route_coordinates: "[[-41.1,-71.4],[-41.2,-71.5]]", center_lat: -41.1, center_lng: -71.4, national_park: null }),
}));
jest.mock("../../../services/api", () => ({
  ...jest.requireActual("../../../services/api"),
  createTripPlan: jest.fn(),
  getTripPlans: jest.fn().mockResolvedValue([]),
}));

import React from "react";
import * as SMS from "expo-sms";
import * as Battery from "expo-battery";
import { router } from "expo-router";
import TrailStart from "../TrailStart";
import { PrimaryButton } from "../../components/MiSenderoUI";
import { db, initDB } from "../../../database/database";
import { saveAuthSession } from "../../../services/authSession";
import { saveEmergencyContact } from "../../../services/emergencyContact";
import { createTripPlan } from "../../../services/api";
import { DepartureMessageRequiredError, sendDeparturePlanSms } from "../../../services/departureMessages";
import { ensureRouteSession, finishRouteSession, getActiveRouteSession } from "../../../services/routeSession";
import { saveTestingLocationMode } from "../../../services/testingMode";

const renderer = require("react-test-renderer");
type Screen = ReturnType<typeof renderer.create>;
const mountedScreens = new Set<Screen>();

const phone = "+5491112345678";
const fetchMock = jest.fn(() => Promise.reject(new Error("network disabled in tests")));
const login = async (id: number, role: "admin" | "user") => {
  await saveAuthSession({ token: `test-${id}`, user: { id, name: "Test", email: `${id}@example.test`, role } });
  await saveEmergencyContact({ name: "Contacto", phone, relationship: "Familia" });
};
const count = async (table: string) => (await db.getFirstAsync<{ count: number }>(`SELECT COUNT(*) AS count FROM ${table}`))?.count;
const flush = () => renderer.act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
const textOf = (screen: Screen) => JSON.stringify(screen.toJSON());
const buttons = (screen: Screen) => screen.root.findAllByType(PrimaryButton) as Array<{ props: { label: string; onPress?: () => void } }>;
const render = async () => {
  let screen: Screen;
  await renderer.act(async () => { screen = renderer.create(<TrailStart />); mountedScreens.add(screen); });
  for (let attempt = 0; attempt < 100 && buttons(screen!).some((button) => button.props.label === "Verificando salida"); attempt += 1) await flush();
  return screen!;
};
const press = async (screen: Screen, label: string) => {
  const button = buttons(screen).find((item) => item.props.label === label);
  expect(button).toBeDefined();
  await renderer.act(async () => { button!.props.onPress?.(); });
  for (let attempt = 0; attempt < 20; attempt += 1) await flush();
};

beforeAll(() => initDB());
afterEach(async () => {
  await renderer.act(async () => {
    for (const screen of mountedScreens) screen.unmount();
    mountedScreens.clear();
  });
}, 30000);
beforeEach(async () => {
  mockTestingLocation = false;
  (Battery.getBatteryLevelAsync as jest.Mock).mockResolvedValue(0.9);
  global.fetch = fetchMock as unknown as typeof fetch;
  await login(70, "user");
  await saveTestingLocationMode(false);
  await getActiveRouteSession(); // creates the route tables
  await db.runAsync("DELETE FROM route_runtime");
  await db.runAsync("DELETE FROM departure_messages");
  await db.runAsync("DELETE FROM pending_operations");
  jest.clearAllMocks();
});

test.each([
  [0.15, "Batería: 15%"],
  [-1, "Batería: no disponible"],
  [null, "Batería: no disponible"],
])("MF11 battery reading %s is explicit and preserves the route preparation screen", async (level, expected) => {
  if (level === null) (Battery.getBatteryLevelAsync as jest.Mock).mockRejectedValueOnce(new Error("Battery unavailable"));
  else (Battery.getBatteryLevelAsync as jest.Mock).mockResolvedValueOnce(level);
  const screen = await render();
  try {
    expect(textOf(screen)).toContain(expected);
    expect(buttons(screen).some(button => button.props.label === "Enviar plan antes de salir")).toBe(true);
    expect(await getActiveRouteSession()).toBeNull();
    expect(SMS.sendSMSAsync).not.toHaveBeenCalled();
  } finally { await renderer.act(async () => screen.unmount()); }
});

test("testing-mode start needs no departure plan and sends, registers or queues none", async () => {
  await login(71, "admin");
  await saveTestingLocationMode(true);
  mockTestingLocation = true;

  const screen = await render();
  expect(textOf(screen)).toContain("Modo prueba: no se envía plan de salida");
  expect(buttons(screen).map((button) => button.props.label)).not.toContain("Enviar plan de regreso por SMS");
  await press(screen, "Comenzar prueba");
  await renderer.act(async () => screen.unmount());

  const route = await getActiveRouteSession();
  expect(route).toMatchObject({ trail_id: 9, simulated: 1, state: "running" });
  expect(router.push).toHaveBeenCalledWith({ pathname: "/route-map", params: { active: "1", id: "9", startedAt: String(route!.started_at) } });
  expect(router.push).not.toHaveBeenCalledWith(expect.objectContaining({ pathname: "/plan-salida" }));
  // Defence in depth: a real plan cannot be sent for a test either.
  await expect(sendDeparturePlanSms({ trailId: 9, contactPhone: phone, expectedReturnAt: new Date(Date.now() + 3600000).toISOString(), messageBody: "Plan" }, async () => true))
    .rejects.toThrow("Modo prueba: no se envía plan de salida");
  expect(SMS.sendSMSAsync).not.toHaveBeenCalled();
  expect(createTripPlan).not.toHaveBeenCalled();
  expect(fetchMock).not.toHaveBeenCalled();
  expect(await count("departure_messages")).toBe(0);
  expect(await count("pending_operations")).toBe(0);
  expect(await count("route_runtime")).toBe(0);
  await finishRouteSession(9, route!.started_at);
});

test("control: a real start still requires the departure plan", async () => {
  await login(72, "user");
  mockTestingLocation = false;

  const screen = await render();
  expect(textOf(screen)).not.toContain("Modo prueba");
  await press(screen, "Enviar plan antes de salir");
  await renderer.act(async () => screen.unmount());

  expect(router.push).toHaveBeenCalledWith({ pathname: "/plan-salida", params: { id: "9" } });
  expect(await getActiveRouteSession()).toBeNull();
  await expect(ensureRouteSession(9, Date.now(), false)).rejects.toBeInstanceOf(DepartureMessageRequiredError);
  // Asking for a simulated route without verified testing mode cannot bypass the plan.
  await expect(ensureRouteSession(9, Date.now(), true)).rejects.toThrow("modo prueba no está activo");
  expect(await getActiveRouteSession()).toBeNull();
});
