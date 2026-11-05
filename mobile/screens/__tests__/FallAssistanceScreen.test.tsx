import "../../../testing/mobileSetup";
jest.mock("../../../services/fallDetection/fallEvents", () => ({ getFallEvent: jest.fn(), answerFallEvent: jest.fn().mockResolvedValue(true) }));
jest.mock("../../../services/fallDetection/monitor", () => ({ fallMonitor: { clearPending: jest.fn() } }));
jest.mock("../../../services/routeTracking", () => ({ getLastRouteTrackingPoint: jest.fn() }));
jest.mock("expo-sms", () => ({ sendSMSAsync: jest.fn(), isAvailableAsync: jest.fn() }));
jest.mock("../../../services/emergencyAlerts", () => ({ sendEmergencyAlert: jest.fn(), sendEmergencySms: jest.fn() }));
import { Linking, Vibration } from "react-native";
import * as SMS from "expo-sms";
import { router, useLocalSearchParams } from "expo-router";
import { answerFallEvent, getFallEvent } from "../../../services/fallDetection/fallEvents";
import { fallMonitor } from "../../../services/fallDetection/monitor";
import { getLastRouteTrackingPoint } from "../../../services/routeTracking";
import { sendEmergencyAlert, sendEmergencySms } from "../../../services/emergencyAlerts";
import { act, mount, press, text } from "../../../testing/mobileHarness";
import FallAssistanceScreen, { FALL_ASSISTANCE_MESSAGE } from "../FallAssistanceScreen";

beforeEach(() => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ eventId: "e1", id: "7", startedAt: "1791626400000" });
  (getFallEvent as jest.Mock).mockResolvedValue({ id: "e1", detectedAt: 1791626500000 });
  (answerFallEvent as jest.Mock).mockResolvedValue(true);
  jest.spyOn(Vibration, "cancel").mockImplementation(() => undefined);
  jest.spyOn(Linking, "openURL").mockResolvedValue(true as never);
});

const nothingWasSent = () => {
  expect(sendEmergencyAlert).not.toHaveBeenCalled();
  expect(sendEmergencySms).not.toHaveBeenCalled();
  expect(SMS.sendSMSAsync).not.toHaveBeenCalled();
  expect(Linking.openURL).not.toHaveBeenCalled();
};

test("shows the required message, the experimental warning and that nothing is sent automatically", async () => {
  const tree = await mount(FallAssistanceScreen);
  expect(text(tree)).toContain(FALL_ASSISTANCE_MESSAGE);
  expect(FALL_ASSISTANCE_MESSAGE).toBe("MiSendero detectó un movimiento compatible con una caída. ¿Necesitás ayuda?");
  expect(text(tree)).toContain("no llama ni envía mensajes por su cuenta");
  expect(text(tree)).toContain("no asumimos que estás inconsciente");
  expect(text(tree)).toContain("experimental");
  nothingWasSent();
});

test("Estoy bien records the confirmation, releases the monitor and sends nothing", async () => {
  const tree = await mount(FallAssistanceScreen);
  await press(tree, "Estoy bien");
  expect(answerFallEvent).toHaveBeenCalledWith("e1", "ok", "dismissed");
  expect(fallMonitor.clearPending).toHaveBeenCalledWith("e1");
  expect(router.back).toHaveBeenCalled();
  nothingWasSent();
  await act(async () => tree.unmount());
  expect(answerFallEvent).toHaveBeenCalledTimes(1);                         // unmounting after answering adds nothing
});

test("Solicitar ayuda only opens the existing SOS screen, with the last real GPS fix", async () => {
  (getLastRouteTrackingPoint as jest.Mock).mockResolvedValue({ latitude: -41.1, longitude: -71.3, recordedAt: 1791626000000, simulated: false });
  const tree = await mount(FallAssistanceScreen);
  await press(tree, "Solicitar ayuda");
  expect(answerFallEvent).toHaveBeenCalledWith("e1", "help", "sos_opened", { latitude: -41.1, longitude: -71.3, recordedAt: 1791626000000 });
  expect(router.replace).toHaveBeenCalledWith({ pathname: "/confirmar-sos", params: { id: "7", startedAt: "1791626400000", origen: "caida" } });
  expect((router.replace as jest.Mock).mock.calls[0][0].params.sendSms).toBeUndefined();   // no automatic SMS
  nothingWasSent();
});

test("a simulated GPS point is never stored with the event, and a log failure never blocks the SOS", async () => {
  (getLastRouteTrackingPoint as jest.Mock).mockResolvedValue({ latitude: 1, longitude: 2, recordedAt: 3, simulated: true });
  (answerFallEvent as jest.Mock).mockRejectedValue(new Error("db"));
  const tree = await mount(FallAssistanceScreen);
  await press(tree, "Solicitar ayuda");
  expect(router.replace).toHaveBeenCalled();
  expect((answerFallEvent as jest.Mock).mock.calls[0][3]).toBeNull();
});

test("leaving without answering is stored as unanswered, not as fine", async () => {
  const tree = await mount(FallAssistanceScreen);
  await act(async () => tree.unmount());
  expect(answerFallEvent).toHaveBeenCalledWith("e1", "unanswered", "none");
  expect(fallMonitor.clearPending).toHaveBeenCalledWith("e1");
  expect(Vibration.cancel).toHaveBeenCalled();
});
