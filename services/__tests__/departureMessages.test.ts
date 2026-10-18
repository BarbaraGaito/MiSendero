jest.mock("expo-sms", () => ({ isAvailableAsync: jest.fn(), sendSMSAsync: jest.fn() }));
jest.mock("../authSession", () => ({ getAuthSession: jest.fn() }));


import * as SMS from "expo-sms";
import { db } from "../../database/database";
import { getAuthSession } from "../authSession";
import { saveEmergencyContact } from "../emergencyContact";
import { DepartureMessageRequiredError, getDepartureMessage, invalidateDepartureMessage, sendDeparturePlanSms } from "../departureMessages";
import { ensureRouteSession, finishRouteSession, getActiveRouteSession, getRouteSession, pauseRouteSession } from "../routeSession";

const phone = "+54 9 11 1234-5678";
const login = (id: number) => (getAuthSession as jest.Mock).mockResolvedValue({ user: { id } });
const contact = (value = phone) => saveEmergencyContact({ name: "Contacto", phone: value, relationship: "Familia" });
const send = (confirmation = async () => false, trailId = 7) => sendDeparturePlanSms({
  trailId, contactPhone: phone, expectedReturnAt: new Date(Date.now() + 3600000).toISOString(), messageBody: "Voy a Confluencia. Regreso en una hora.",
}, confirmation);

beforeEach(async () => {
  jest.clearAllMocks();
  jest.spyOn(Date, "now").mockReturnValue(100000);
  login(21);
  (SMS.isAvailableAsync as jest.Mock).mockResolvedValue(true);
  (SMS.sendSMSAsync as jest.Mock).mockResolvedValue({ result: "sent" });
  await getActiveRouteSession();
  await db.runAsync("DELETE FROM route_runtime");
  await db.runAsync("DELETE FROM departure_messages");
  await db.runAsync("DELETE FROM emergency_contacts");
  await contact();
});
afterEach(() => jest.restoreAllMocks());

test("saving a contact alone never unlocks a route; a simulated route needs verified testing mode", async () => {
  await expect(ensureRouteSession(7, 100000)).rejects.toBeInstanceOf(DepartureMessageRequiredError);
  await expect(ensureRouteSession(7, 100000, true)).rejects.toThrow("modo prueba no está activo");
  expect(await getActiveRouteSession()).toBeNull();
});

test("a cancelled composer cannot authorize departure", async () => {
  (SMS.sendSMSAsync as jest.Mock).mockResolvedValue({ result: "cancelled" });
  const confirm = jest.fn().mockResolvedValue(true);
  expect((await send(confirm)).status).toBe("cancelled");
  expect(confirm).not.toHaveBeenCalled();
  expect(await getDepartureMessage(7)).toBeNull();
});

test("unknown SMS results require explicit confirmation after the composer returns", async () => {
  (SMS.sendSMSAsync as jest.Mock).mockResolvedValue({ result: "unknown" });
  expect((await send()).status).toBe("unconfirmed");
  await expect(ensureRouteSession(7, 100000)).rejects.toThrow(DepartureMessageRequiredError);
  const confirm = jest.fn(async () => { expect(SMS.sendSMSAsync).toHaveBeenCalled(); return true; });
  expect((await send(confirm)).message?.confirmation).toBe("user_confirmed");
  expect(confirm).toHaveBeenCalledTimes(1);
  expect((await ensureRouteSession(7, 100000))?.state).toBe("running");
});

test("system-confirmed sending persists proof tied to the actual contact and route", async () => {
  const confirm = jest.fn();
  const result = await send(confirm);
  expect(confirm).not.toHaveBeenCalled();
  expect(result.message?.confirmation).toBe("system_sent");
  expect(result.message?.contact_phone).toBe("+5491112345678");
  expect(await getDepartureMessage(8)).toBeNull();
  await expect(ensureRouteSession(8, 100000)).rejects.toThrow(DepartureMessageRequiredError);
  login(22);
  await contact();
  expect(await getDepartureMessage(7)).toBeNull();
  login(21);
  await contact("+5491199999999");
  expect(await getDepartureMessage(7)).toBeNull();
});

test("a receipt is consumed atomically once; resume remains allowed but a later trip needs a new SMS", async () => {
  await send();
  await ensureRouteSession(7, 100000);
  expect(await getDepartureMessage(7)).toBeNull();
  await pauseRouteSession(7, 100000);
  expect((await ensureRouteSession(7, 100000))?.state).toBe("paused");
  await finishRouteSession(7, 100000);
  await expect(ensureRouteSession(7, 200000)).rejects.toThrow(DepartureMessageRequiredError);
  expect((await getRouteSession(7, 100000))?.state).toBe("completed");
});

test("concurrent starts cannot reuse one receipt", async () => {
  await send();
  const results = await Promise.allSettled([ensureRouteSession(7, 100000), ensureRouteSession(7, 100001)]);
  expect(results.filter((result) => result.status === "fulfilled")).toHaveLength(1);
  expect((await db.getAllAsync("SELECT * FROM route_runtime"))).toHaveLength(1);
});

test("an expired or edited plan cannot authorize departure", async () => {
  await send();
  jest.spyOn(Date, "now").mockReturnValue(3700000);
  expect(await getDepartureMessage(7)).toBeNull();
  await expect(ensureRouteSession(7, 3700000)).rejects.toThrow(DepartureMessageRequiredError);
  await send();
  await invalidateDepartureMessage(7);
  expect(await getDepartureMessage(7)).toBeNull();
});

test("no SMS support or a send error leaves departure blocked", async () => {
  (SMS.isAvailableAsync as jest.Mock).mockResolvedValue(false);
  await expect(send()).rejects.toThrow("telefono con SMS");
  expect(SMS.sendSMSAsync).not.toHaveBeenCalled();
  (SMS.isAvailableAsync as jest.Mock).mockResolvedValue(true);
  (SMS.sendSMSAsync as jest.Mock).mockRejectedValue(new Error("SMS error"));
  await expect(send()).rejects.toThrow("SMS error");
  expect(await getDepartureMessage(7)).toBeNull();
});

test("changing contact or account in the composer cannot record a valid receipt", async () => {
  (SMS.sendSMSAsync as jest.Mock).mockImplementation(async () => { await contact("+5491199999999"); return { result: "sent" }; });
  await expect(send()).rejects.toThrow("contacto cambio");
  expect(await getDepartureMessage(7)).toBeNull();
  await contact();
  (SMS.sendSMSAsync as jest.Mock).mockImplementation(async () => { login(22); return { result: "sent" }; });
  await expect(send()).rejects.toThrow("cuenta o el contacto cambio");
});

test("legacy running sessions can be resumed without inventing an SMS receipt", async () => {
  await db.runAsync("INSERT INTO route_runtime (user_id, trail_id, started_at, state) VALUES (?, ?, ?, ?)", [21, 7, 100000, "running"]);
  expect((await ensureRouteSession(7, 100000))?.state).toBe("running");
  expect(await getDepartureMessage(7)).toBeNull();
});
