jest.mock("expo-sms", () => ({ isAvailableAsync: jest.fn(), sendSMSAsync: jest.fn() }));
jest.mock("../authSession", () => ({ getAuthSession: jest.fn() }));
jest.mock("../emergencyContact", () => ({ getEmergencyContact: jest.fn() }));
jest.mock("../testingMode", () => ({ isTestingLocationActive: jest.fn() }));
jest.mock("../routeSession", () => ({ getRouteSession: jest.fn() }));
jest.mock("../trailRepository", () => ({ getTrailById: jest.fn() }));
import * as SMS from "expo-sms";
import { getAuthSession } from "../authSession";
import { getEmergencyContact } from "../emergencyContact";
import { isTestingLocationActive } from "../testingMode";
import { getRouteSession } from "../routeSession";
import { getTrailById } from "../trailRepository";
import { CompletionContactRequiredError, sendRouteCompletionSms } from "../completionMessages";
import { trail } from "../../testing/fixtures";

const context = { trailId: 7, startedAt: 1791626400000, simulated: false };
const contact = { name: "Contacto", phone: "+5491112345678", relationship: "Familia" };
beforeEach(() => {
  jest.clearAllMocks();
  (SMS.isAvailableAsync as jest.Mock).mockResolvedValue(true);
  (SMS.sendSMSAsync as jest.Mock).mockResolvedValue({ result: "sent" });
  (getAuthSession as jest.Mock).mockResolvedValue({ user: { id: 31 } });
  (getEmergencyContact as jest.Mock).mockResolvedValue(contact);
  (isTestingLocationActive as jest.Mock).mockResolvedValue(false);
  (getRouteSession as jest.Mock).mockResolvedValue({ simulated: false, state: "completed" });
  (getTrailById as jest.Mock).mockResolvedValue(trail);
});

test("prepares a completion SMS with the real trail and the saved emergency contact", async () => {
  const result = await sendRouteCompletionSms(context);
  expect(SMS.sendSMSAsync).toHaveBeenCalledWith([contact.phone], expect.stringContaining(`terminé mi recorrido en el sendero ${trail.name}`));
  expect(result.message).toContain(trail.location);
  expect(result.message).not.toMatch(/estoy a salvo|llegué a casa|completé el sendero/i);
});

test.each(["sent", "cancelled", "unknown"])("preserves the native %s result without asserting delivery", async result => {
  (SMS.sendSMSAsync as jest.Mock).mockResolvedValue({ result });
  expect((await sendRouteCompletionSms(context)).result).toBe(result);
});

test("unavailable catalogue metadata does not block the SMS or invent a trail name", async () => {
  (getTrailById as jest.Mock).mockRejectedValue(new Error("sin Internet"));
  const result = await sendRouteCompletionSms(context);
  expect(result.message).toContain("terminé mi recorrido de trekking");
  expect(result.message).not.toContain(trail.name);
  expect(SMS.sendSMSAsync).toHaveBeenCalledTimes(1);
});

test.each(["context", "testing-mode", "route"])("a simulated %s cannot send to a real contact", async source => {
  if (source === "testing-mode") (isTestingLocationActive as jest.Mock).mockResolvedValue(true);
  if (source === "route") (getRouteSession as jest.Mock).mockResolvedValue({ simulated: true });
  await expect(sendRouteCompletionSms({ ...context, simulated: source === "context" })).rejects.toThrow("recorridos de prueba");
  expect(SMS.sendSMSAsync).not.toHaveBeenCalled();
});

test("a missing contact is an actionable error, never an unspecified recipient", async () => {
  (getEmergencyContact as jest.Mock).mockResolvedValue(null);
  await expect(sendRouteCompletionSms(context)).rejects.toBeInstanceOf(CompletionContactRequiredError);
  expect(SMS.sendSMSAsync).not.toHaveBeenCalled();
});

test("devices without SMS keep the failure explicit", async () => {
  (SMS.isAvailableAsync as jest.Mock).mockResolvedValue(false);
  await expect(sendRouteCompletionSms(context)).rejects.toThrow("no permite enviar SMS");
  expect(SMS.sendSMSAsync).not.toHaveBeenCalled();
});

test.each(["account", "contact"])("a changed %s cannot redirect the prepared notice", async changed => {
  if (changed === "account") (getAuthSession as jest.Mock).mockResolvedValueOnce({ user: { id: 31 } }).mockResolvedValue({ user: { id: 32 } });
  else (getEmergencyContact as jest.Mock).mockResolvedValueOnce(contact).mockResolvedValue({ ...contact, phone: "+5491187654321" });
  await expect(sendRouteCompletionSms(context)).rejects.toThrow("cuenta o el contacto cambió");
  expect(SMS.sendSMSAsync).not.toHaveBeenCalled();
});
