import * as SQLite from "expo-sqlite";
import { AuthSession } from "../types";

const db = SQLite.openDatabaseSync("trekking.db");

const initAuthSessionTable = async () => {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS auth_session (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      token TEXT NOT NULL,
      user_json TEXT NOT NULL
    );
  `);
};

export const saveAuthSession = async (session: AuthSession) => {
  await initAuthSessionTable();
  await db.runAsync(
    `INSERT OR REPLACE INTO auth_session (id, token, user_json)
     VALUES (1, ?, ?)`,
    [session.token, JSON.stringify(session.user)]
  );
};

export const getAuthSession = async (): Promise<AuthSession | null> => {
  await initAuthSessionTable();

  const row = await db.getFirstAsync<{ token: string; user_json: string }>(
    "SELECT token, user_json FROM auth_session WHERE id = 1"
  );

  if (!row) {
    return null;
  }

  return {
    token: row.token,
    user: JSON.parse(row.user_json),
  };
};

export const clearAuthSession = async () => {
  await initAuthSessionTable();
  await db.runAsync("DELETE FROM auth_session WHERE id = 1");
};
