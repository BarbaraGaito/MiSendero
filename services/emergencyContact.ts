import { db } from "../database/connection";
import { EmergencyContact } from "../types";
import { getAuthSession } from "./authSession";


const initEmergencyContactTable = async () => {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS emergency_contacts (
      user_id INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      phone TEXT NOT NULL,
      relationship TEXT NOT NULL,
      updated_at INTEGER NOT NULL
    );
  `);
};

const getCurrentUserId = async () => {
  const session = await getAuthSession();

  return session?.user.id ?? null;
};

export const getEmergencyContact = async (): Promise<EmergencyContact | null> => {
  await initEmergencyContactTable();

  const userId = await getCurrentUserId();

  if (!userId) return null;

  const row = await db.getFirstAsync<EmergencyContact>(
    `
      SELECT
        user_id AS id,
        name,
        phone,
        relationship,
        updated_at
      FROM emergency_contacts
      WHERE user_id = ?
    `,
    [userId]
  );

  return row ?? null;
};

export const hasEmergencyContact = async () => {
  const contact = await getEmergencyContact();

  return Boolean(contact?.name && contact?.phone && contact?.relationship);
};

export const saveEmergencyContact = async (
  contact: Pick<EmergencyContact, "name" | "phone" | "relationship">
) => {
  await initEmergencyContactTable();

  const userId = await getCurrentUserId();

  if (!userId) {
    throw new Error("Sesion requerida para guardar el contacto de emergencia.");
  }

  const normalizedContact = {
    id: userId,
    name: contact.name.trim(),
    phone: contact.phone.trim(),
    relationship: contact.relationship.trim(),
    updated_at: Date.now(),
  };

  await db.runAsync(
    `
      INSERT OR REPLACE INTO emergency_contacts (
        user_id,
        name,
        phone,
        relationship,
        updated_at
      )
      VALUES (?, ?, ?, ?, ?)
    `,
    [
      userId,
      normalizedContact.name,
      normalizedContact.phone,
      normalizedContact.relationship,
      normalizedContact.updated_at,
    ]
  );

  return normalizedContact;
};
