jest.mock("expo-sms", () => ({ isAvailableAsync: jest.fn().mockResolvedValue(true), sendSMSAsync: jest.fn().mockResolvedValue({ result: "sent" }) }));
jest.mock("expo-network", () => ({ getNetworkStateAsync: jest.fn().mockResolvedValue({ isConnected: true, isInternetReachable: true }) }));
let mockUuid = 0;
jest.mock("expo-crypto", () => ({ randomUUID: () => `00000000-0000-4000-8000-${String(++mockUuid).padStart(12, "0")}` }));
let mockParams: Record<string, string> = {};
jest.mock("expo-router", () => ({
  router: { push: jest.fn(), replace: jest.fn(), setParams: jest.fn(), back: jest.fn(), canGoBack: () => true },
  useLocalSearchParams: () => mockParams,
  useFocusEffect: (effect: () => void | (() => void)) => require("react").useEffect(effect, [effect]),
}));
jest.mock("@expo/vector-icons", () => ({ Ionicons: () => null }));
jest.mock("react-native-safe-area-context", () => ({
  SafeAreaView: require("react-native").View,
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("../deviceLocation", () => ({ getCurrentDeviceLocation: jest.fn().mockResolvedValue(null) }));
jest.mock("../trailRepository", () => ({ getTrailById: jest.fn().mockResolvedValue(null) }));
jest.mock("../api", () => ({
  ...jest.requireActual("../api"),
  createEmergencyAlert: jest.fn().mockResolvedValue({ id: 501 }),
}));

import React from "react";
import * as SMS from "expo-sms";
import * as Network from "expo-network";
import { router } from "expo-router";
import { db, initDB } from "../../database/database";
import { saveAuthSession } from "../authSession";
import { saveEmergencyContact } from "../emergencyContact";
import { sendDeparturePlanSms } from "../departureMessages";
import { ensureRouteSession, finishRouteSession, getActiveRouteSession } from "../routeSession";
import { getTestingLocationMode, saveTestingLocationMode } from "../testingMode";
import { sendEmergencyAlert, sendEmergencySms, SimulatedEmergencyError } from "../emergencyAlerts";
import { createEmergencyAlert } from "../api";
import ConfirmSosScreen from "../../mobile/screens/ConfirmSosScreen";
import { PrimaryButton } from "../../mobile/components/MiSenderoUI";

const renderer = require("react-test-renderer");
type Screen = ReturnType<typeof renderer.create>;

const phone = "+5491112345678";
const fetchMock = jest.fn(() => Promise.reject(new Error("network disabled in tests")));
const login = async (id: number, role: "admin" | "user") => {
  await saveAuthSession({ token: `test-${id}`, user: { id, name: "Test", email: `${id}@example.test`, role } });
  await saveEmergencyContact({ name: "Contacto", phone, relationship: "Familia" }); // contacts are per account
};
const sendPlan = (trailId: number) => sendDeparturePlanSms({
  trailId, contactPhone: phone, expectedReturnAt: new Date(Date.now() + 3600000).toISOString(), messageBody: "Plan de regreso",
}, async () => false);
const queued = async () => (await db.getFirstAsync<{ count: number }>("SELECT COUNT(*) AS count FROM pending_operations"))?.count;
const flush = (ms = 10) => renderer.act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });
const textOf = (screen: Screen) => JSON.stringify(screen.toJSON());
const labels = (screen: Screen) => screen.root.findAllByType(PrimaryButton).map((button: { props: { label: string } }) => button.props.label);
const waitFor = async (check: () => boolean) => {
  for (let attempt = 0; attempt < 100 && !check(); attempt += 1) await flush();
  expect(check()).toBe(true);
};
const render = async (params: Record<string, string>) => {
  mockParams = params;
  let screen: Screen;
  await renderer.act(async () => { screen = renderer.create(<ConfirmSosScreen />); });
  await flush();
  return screen!;
};
const press = async (screen: Screen, label: string) => {
  const button = screen.root.findAllByType(PrimaryButton).find((item: { props: { label: string } }) => item.props.label === label);
  expect(button).toBeDefined();
  await renderer.act(async () => { await button.props.onPress(); });
  await flush();
};
const expectNothingSent = async () => {
  await flush(50);
  expect(SMS.sendSMSAsync).not.toHaveBeenCalled();
  expect(createEmergencyAlert).not.toHaveBeenCalled();
  expect(fetchMock).not.toHaveBeenCalled();
  expect(await queued()).toBe(0);
};

beforeAll(() => initDB());
beforeEach(async () => {
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: true, isInternetReachable: true });
  global.fetch = fetchMock as unknown as typeof fetch;
  await login(60, "user");
  await saveTestingLocationMode(false);
  await getActiveRouteSession(); // creates the route tables
  await db.runAsync("DELETE FROM pending_operations");
  await db.runAsync("DELETE FROM route_runtime");
  await db.runAsync("DELETE FROM departure_messages");
  jest.clearAllMocks();
  (SMS.sendSMSAsync as jest.Mock).mockReset().mockResolvedValue({ result: "sent" });
});

test.each([
  ["cancelled", "SMS cancelado."],
  ["sent", "Esto no confirma que tu contacto lo recibió."],
])("MF12 offline SOS with SMS result %s never confirms remote registration or delivery", async (smsResult, expectedMessage) => {
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: false, isInternetReachable: false });
  (SMS.sendSMSAsync as jest.Mock).mockResolvedValueOnce({ result: smsResult });
  const screen = await render({});
  try {
    await press(screen, "Guardar pedido SOS");
    await waitFor(() => textOf(screen).includes("SOS guardado en este teléfono"));
    expect(createEmergencyAlert).not.toHaveBeenCalled();
    expect(await db.getFirstAsync("SELECT status FROM pending_operations")).toMatchObject({ status: "pending" });
    expect(textOf(screen)).toContain("Entrega al contacto: sin confirmación en MiSendero.");
    expect(textOf(screen)).not.toContain("SOS registrado en el servidor");
    await press(screen, "Enviar SOS por SMS");
    expect(textOf(screen)).toContain(expectedMessage);
    expect(textOf(screen)).toContain("Entrega al contacto: sin confirmación en MiSendero.");
    expect(createEmergencyAlert).not.toHaveBeenCalled();
  } finally { await renderer.act(async () => screen.unmount()); }
}, 20000);

test("a SOS raised by simulated wearable data shows a test confirmation and sends, queues and stores nothing", async () => {
  await login(61, "user");
  const startedAt = Date.now() - 60000;
  await sendPlan(5);
  await ensureRouteSession(5, startedAt, false); // a real route: only the alert data is simulated
  jest.clearAllMocks();

  const screen = await render({ id: "5", startedAt: String(startedAt), simulated: "1", sendSms: "1" });
  expect(textOf(screen)).toContain("Modo prueba: el SOS no se envía");
  expect(labels(screen)).not.toContain("Enviar SOS por SMS");
  await press(screen, "Probar pedido SOS (no se envía)");
  expect(textOf(screen)).toContain("Prueba completada");

  // Defence in depth: the sending layer refuses the same request.
  await expect(sendEmergencyAlert({ trailId: 5, startedAt, simulated: true })).rejects.toBeInstanceOf(SimulatedEmergencyError);
  await expect(sendEmergencySms(phone, "SOS", { trailId: 5, startedAt, simulated: true })).rejects.toBeInstanceOf(SimulatedEmergencyError);
  await expectNothingSent();
  await renderer.act(async () => screen.unmount());
  await finishRouteSession(5, startedAt);
});

test("in a testing-location route a manual SOS is a test, even after testing mode is switched off", async () => {
  await login(62, "admin");
  await saveTestingLocationMode(true);
  const startedAt = Date.now() - 60000;
  await ensureRouteSession(6, startedAt, true);

  const screen = await render({ id: "6", startedAt: String(startedAt), sendSms: "1" });
  await waitFor(() => textOf(screen).includes("Modo prueba: el SOS no se envía"));
  expect(textOf(screen)).toContain("tenés que salir del modo prueba");
  expect(labels(screen)).not.toContain("Enviar SOS por SMS");
  await press(screen, "Probar pedido SOS (no se envía)");
  expect(textOf(screen)).toContain("Prueba completada");
  await renderer.act(async () => screen.unmount());

  await expect(sendEmergencyAlert({ trailId: 6, startedAt })).rejects.toMatchObject({ reason: "testing_location" });
  await saveTestingLocationMode(false);
  // The route itself is still a simulation: its data never becomes a real SOS.
  await expect(sendEmergencyAlert({ trailId: 6, startedAt })).rejects.toBeInstanceOf(SimulatedEmergencyError);
  await expect(sendEmergencySms(phone, "SOS", { trailId: 6, startedAt })).rejects.toBeInstanceOf(SimulatedEmergencyError);
  await expectNothingSent();
  await finishRouteSession(6, startedAt);
});

test("a real emergency during a test leaves testing mode and opens a real SOS without the simulated route", async () => {
  await login(64, "admin");
  await saveTestingLocationMode(true);
  const startedAt = Date.now() - 60000;
  await ensureRouteSession(8, startedAt, true);

  const testScreen = await render({ id: "8", startedAt: String(startedAt) });
  await waitFor(() => textOf(testScreen).includes("Modo prueba: el SOS no se envía"));
  await press(testScreen, "Emergencia real: salir del modo prueba");
  await renderer.act(async () => testScreen.unmount());
  expect((await getTestingLocationMode()).enabled).toBe(false);
  expect(router.replace).toHaveBeenCalledWith("/confirmar-sos");
  await expectNothingSent();

  const realScreen = await render({});
  expect(textOf(realScreen)).not.toContain("Modo prueba");
  await press(realScreen, "Guardar pedido SOS");
  expect(await queued()).toBe(1);
  await renderer.act(async () => realScreen.unmount());
  await finishRouteSession(8, startedAt);
});

test("control: a manual SOS in a real route with real data is still saved, synced and prepared as SMS", async () => {
  await login(63, "user");
  const startedAt = Date.now() - 60000;
  await sendPlan(7);
  await ensureRouteSession(7, startedAt, false);
  jest.clearAllMocks();

  const screen = await render({ id: "7", startedAt: String(startedAt), sendSms: "1" });
  expect(textOf(screen)).not.toContain("Modo prueba");
  await waitFor(() => (SMS.sendSMSAsync as jest.Mock).mock.calls.length === 1);
  await press(screen, "Guardar pedido SOS");
  expect(await queued()).toBe(1);
  await waitFor(() => (createEmergencyAlert as jest.Mock).mock.calls.length === 1);
  expect((createEmergencyAlert as jest.Mock).mock.calls[0][0]).toMatchObject({ trail_id: 7 });

  expect(SMS.sendSMSAsync).toHaveBeenCalledWith([phone], expect.stringContaining("SOS MiSendero"));
  await renderer.act(async () => screen.unmount());
  await finishRouteSession(7, startedAt);
});
