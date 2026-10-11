import * as SMS from "expo-sms";
import { db, initDB } from "../database/database";
import { getAuthSession } from "./authSession";
import { getEmergencyContact } from "./emergencyContact";

export interface DepartureMessage {
  id: number;
  user_id: number;
  trail_id: number;
  contact_phone: string;
  expected_return_at: number;
  message_body: string;
  confirmation: "system_sent" | "user_confirmed";
  sent_at: number;
  used_started_at: number | null;
  invalidated_at: number | null;
}

export class DepartureMessageRequiredError extends Error {
  constructor() {
    super("Envia el plan de regreso a tu contacto de emergencia antes de iniciar este recorrido.");
    this.name = "DepartureMessageRequiredError";
  }
}

export const normalizeContactPhone = (phone: string) => phone.replace(/[^+\d]/g, "");

export const initDepartureMessages = async () => {
  await initDB();
  await db.execAsync(`CREATE TABLE IF NOT EXISTS departure_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    trail_id INTEGER NOT NULL,
    contact_phone TEXT NOT NULL,
    expected_return_at INTEGER NOT NULL,
    message_body TEXT NOT NULL,
    confirmation TEXT NOT NULL CHECK (confirmation IN ('system_sent', 'user_confirmed')),
    sent_at INTEGER NOT NULL,
    used_started_at INTEGER,
    invalidated_at INTEGER
  )`);
};

export const getDepartureMessage = async (trailId: number): Promise<DepartureMessage | null> => {
  await initDepartureMessages();
  const session = await getAuthSession();
  const contact = await getEmergencyContact();
  if (!session || !contact?.phone) return null;
  return db.getFirstAsync<DepartureMessage>(
    `SELECT * FROM departure_messages WHERE user_id = ? AND trail_id = ?
     AND contact_phone = ? AND expected_return_at > ? AND sent_at <= ?
     AND used_started_at IS NULL AND invalidated_at IS NULL ORDER BY id DESC LIMIT 1`,
    [session.user.id, trailId, normalizeContactPhone(contact.phone), Date.now(), Date.now()]
  );
};

export const invalidateDepartureMessage = async (trailId: number) => {
  await initDepartureMessages();
  const userId = (await getAuthSession())?.user.id;
  if (!userId) return;
  await db.runAsync(
    "UPDATE departure_messages SET invalidated_at = ? WHERE user_id = ? AND trail_id = ? AND used_started_at IS NULL AND invalidated_at IS NULL",
    [Date.now(), userId, trailId]
  );
};

export const sendDeparturePlanSms = async (draft: {
  trailId: number;
  contactPhone: string;
  expectedReturnAt: string;
  messageBody: string;
}, confirmUnknown: () => Promise<boolean>) => {
  const userId = (await getAuthSession())?.user.id;
  if (!userId) throw new Error("Inicia sesion antes de enviar el plan de regreso.");
  if (!Number.isInteger(draft.trailId) || draft.trailId <= 0 || !draft.messageBody.trim()) {
    throw new Error("Prepara un plan con un sendero valido antes de enviar el SMS.");
  }
  const expectedReturnAt = Date.parse(draft.expectedReturnAt);
  if (!Number.isFinite(expectedReturnAt) || expectedReturnAt <= Date.now()) {
    throw new Error("La hora de regreso ya paso. Prepara un nuevo plan antes de salir.");
  }
  const phone = normalizeContactPhone(draft.contactPhone);
  const matchesContact = async () => {
    const contact = await getEmergencyContact();
    return contact && normalizeContactPhone(contact.phone) === phone;
  };
  if (!phone || !await matchesContact()) throw new Error("El contacto cambio. Actualiza el plan y volve a enviarlo.");
  if (!await SMS.isAvailableAsync()) throw new Error("Necesitas un telefono con SMS para enviar el plan e iniciar el recorrido.");
  const result = await SMS.sendSMSAsync([draft.contactPhone], draft.messageBody);
  if (result.result === "cancelled") return { status: "cancelled" as const, message: null };
  if (result.result !== "sent" && !(result.result === "unknown" && await confirmUnknown())) {
    return { status: "unconfirmed" as const, message: null };
  }
  if ((await getAuthSession())?.user.id !== userId || !await matchesContact()) {
    throw new Error("La cuenta o el contacto cambio mientras se enviaba el plan. Volve a enviarlo.");
  }
  if (expectedReturnAt <= Date.now()) throw new Error("La hora de regreso ya paso. Envia un plan actualizado.");
  await initDepartureMessages();
  await invalidateDepartureMessage(draft.trailId);
  const saved = await db.runAsync(
    `INSERT INTO departure_messages (user_id, trail_id, contact_phone, expected_return_at, message_body, confirmation, sent_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
    [userId, draft.trailId, phone, expectedReturnAt, draft.messageBody,
      result.result === "sent" ? "system_sent" : "user_confirmed", Date.now()]
  );
  const message = await db.getFirstAsync<DepartureMessage>("SELECT * FROM departure_messages WHERE id = ?", [saved.lastInsertRowId]);
  return { status: "confirmed" as const, message };
};
