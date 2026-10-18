import "../../../testing/mobileSetup";
jest.mock("expo-sms", () => ({ isAvailableAsync: jest.fn() }));
jest.mock("../../../services/emergencyContact", () => ({ getEmergencyContact: jest.fn() }));
jest.mock("../../../services/emergencyAlerts", () => ({
  ...jest.requireActual("../../../services/emergencyAlerts"),
  getEmergencyTestReason: jest.fn(), getEmergencyLocation: jest.fn(),
  sendEmergencySms: jest.fn(), sendEmergencyAlert: jest.fn(),
}));
jest.mock("../../../services/trailMessages", () => ({ ...jest.requireActual("../../../services/trailMessages"), getTrailForMessage: jest.fn() }));
jest.mock("../../../services/syncQueue", () => ({ getEmergencyOperation: jest.fn(), runSync: jest.fn() }));
import { Alert } from "react-native";
import * as SMS from "expo-sms";
import { router, useLocalSearchParams } from "expo-router";
import { mount, press, text, act, flush } from "../../../testing/mobileHarness";
import { trail } from "../../../testing/fixtures";
import { getEmergencyContact } from "../../../services/emergencyContact";
import { getEmergencyLocation, getEmergencyTestReason, sendEmergencySms, sendEmergencyAlert } from "../../../services/emergencyAlerts";
import { getTrailForMessage } from "../../../services/trailMessages";
import { getEmergencyOperation } from "../../../services/syncQueue";
import ConfirmSos from "../ConfirmSosScreen";

const person = { name: "Contacto", phone: "+5491112345678", relationship: "Familia" };
const location = { latitude: -41.05, longitude: -71.07, timestamp: Date.now() };
beforeEach(() => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "7", startedAt: "1791626400000", sendSms: "1" });
  (SMS.isAvailableAsync as jest.Mock).mockResolvedValue(true);
  (getEmergencyContact as jest.Mock).mockResolvedValue(person);
  (getEmergencyLocation as jest.Mock).mockResolvedValue(location);
  (getEmergencyTestReason as jest.Mock).mockResolvedValue(null);
  (getTrailForMessage as jest.Mock).mockResolvedValue(trail);
  (sendEmergencySms as jest.Mock).mockResolvedValue({ result: "sent" });
  (getEmergencyOperation as jest.Mock).mockResolvedValue(null);
});

test("the explicit route SOS opens one SMS with the contact, real trail and last known coordinates", async () => {
  const tree = await mount(ConfirmSos);
  expect(sendEmergencySms).toHaveBeenCalledTimes(1);
  const [phone, message, context] = (sendEmergencySms as jest.Mock).mock.calls[0];
  expect(phone).toBe(person.phone);
  expect(message).toContain(`Sendero: ${trail.name}`);
  expect(message).toContain("SOS MiSendero. Necesito asistencia.");
  expect(message).toContain("https://maps.google.com/?q=-41.05,-71.07");
  expect(context).toMatchObject({ trailId: 7, startedAt: 1791626400000, simulated: false });
  expect(router.setParams).toHaveBeenCalledWith({ sendSms: "0" });
  expect(sendEmergencyAlert).not.toHaveBeenCalled(); // SMS needs no backend acknowledgement.
  expect(text(tree)).toContain("Esto no confirma que tu contacto lo recibió");
  await act(async () => tree.update(<ConfirmSos />));
  expect(sendEmergencySms).toHaveBeenCalledTimes(1);
});

test("opening the SOS screen normally waits for a tap on Enviar SOS por SMS", async () => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "7" });
  const tree = await mount(ConfirmSos);
  expect(sendEmergencySms).not.toHaveBeenCalled();
  await press(tree, "Enviar SOS por SMS");
  expect(sendEmergencySms).toHaveBeenCalledTimes(1);
});

test("SMS remains available without GPS or catalogue metadata", async () => {
  (getEmergencyLocation as jest.Mock).mockResolvedValue({ latitude: null, longitude: null, timestamp: Date.now() });
  (getTrailForMessage as jest.Mock).mockResolvedValue(null);
  await mount(ConfirmSos);
  expect(sendEmergencySms).toHaveBeenCalledWith(person.phone, expect.stringContaining("Ubicación no disponible"), expect.any(Object));
  expect(sendEmergencyAlert).not.toHaveBeenCalled();
});

test("a saved SOS does not freeze the location used in a new SMS", async () => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "7", operationId: "42", sendSms: "1" });
  (getEmergencyOperation as jest.Mock).mockResolvedValue({ status: "pending", payload: { message_body: "SOS anterior" } });
  const tree = await mount(ConfirmSos);
  expect(sendEmergencySms).toHaveBeenCalledWith(person.phone, expect.stringContaining("-41.05000, -71.07000"), expect.any(Object));
  expect(text(tree)).not.toContain("SOS anterior");
});

test.each([
  ["cancelled", "SMS cancelado. No se confirmó el envío"],
  ["unknown", "Verificá allí el estado del SMS"],
])("a %s result never claims a confirmed send or delivery", async (result, expected) => {
  (sendEmergencySms as jest.Mock).mockResolvedValue({ result });
  const tree = await mount(ConfirmSos);
  expect(text(tree)).toContain(expected);
  expect(text(tree)).not.toContain("El teléfono indicó que enviaste");
});

test("missing contact opens contact settings instead of sending to an unknown destination", async () => {
  (getEmergencyContact as jest.Mock).mockResolvedValue(null);
  await mount(ConfirmSos);
  expect(router.push).toHaveBeenCalledWith("/contacto-seguridad");
  expect(sendEmergencySms).not.toHaveBeenCalled();
});

test("a device without SMS keeps the call option available and does not attempt sending", async () => {
  jest.spyOn(Alert, "alert").mockImplementation(() => {});
  (SMS.isAvailableAsync as jest.Mock).mockResolvedValue(false);
  const tree = await mount(ConfirmSos);
  expect(Alert.alert).toHaveBeenCalledWith("SMS no disponible en este dispositivo", expect.any(String));
  expect(text(tree)).toContain("Llamar al contacto");
  expect(sendEmergencySms).not.toHaveBeenCalled();
});

test("a failed SMS can be retried manually without reopening automatically", async () => {
  (sendEmergencySms as jest.Mock).mockRejectedValueOnce(new Error("native failure"));
  const tree = await mount(ConfirmSos);
  expect(text(tree)).toContain("No pudimos abrir Mensajes");
  await press(tree, "Enviar SOS por SMS");
  expect(sendEmergencySms).toHaveBeenCalledTimes(2);
  expect(text(tree)).toContain("El teléfono indicó que enviaste el SMS");
});

test("rapid repeat taps open only one native composer", async () => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "7" });
  let finish!: (result: { result: string }) => void;
  (sendEmergencySms as jest.Mock).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const tree = await mount(ConfirmSos);
  const button = tree.root.findAll((node: any) => node.props.label === "Enviar SOS por SMS")[0];
  await act(async () => {
    void button.props.onPress(); void button.props.onPress(); await flush();
  });
  expect(sendEmergencySms).toHaveBeenCalledTimes(1);
  await act(async () => { finish({ result: "sent" }); await flush(); });
});
