import * as SQLite from "expo-sqlite";
import * as SecureStore from "expo-secure-store";
import { AuthSession } from "../types";

const db = SQLite.openDatabaseSync("trekking.db");
const AUTH_TOKEN_KEY = "misendero.auth.token";
const SECURE_TOKEN_SENTINEL = "__secure_store__";

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
  const canUseSecureStore = await SecureStore.isAvailableAsync().catch(() => false);
  const tokenForSqlite = canUseSecureStore ? SECURE_TOKEN_SENTINEL : session.token;

  if (canUseSecureStore) {
    await SecureStore.setItemAsync(AUTH_TOKEN_KEY, session.token);
  }

  await db.runAsync(
    `INSERT OR REPLACE INTO auth_session (id, token, user_json)
     VALUES (1, ?, ?)`,
    [tokenForSqlite, JSON.stringify(session.user)]
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

  const canUseSecureStore = await SecureStore.isAvailableAsync().catch(() => false);
  const secureToken = canUseSecureStore
    ? await SecureStore.getItemAsync(AUTH_TOKEN_KEY).catch(() => null)
    : null;
  const token = secureToken || row.token;

  if (!token || token === SECURE_TOKEN_SENTINEL) return null;

  if (canUseSecureStore && row.token !== SECURE_TOKEN_SENTINEL) {
    await SecureStore.setItemAsync(AUTH_TOKEN_KEY, row.token);
    await db.runAsync("UPDATE auth_session SET token = ? WHERE id = 1", [
      SECURE_TOKEN_SENTINEL,
    ]);
  }

  return {
    token,
    user: JSON.parse(row.user_json),
  };
};

export const clearAuthSession = async () => {
  await initAuthSessionTable();
  await SecureStore.deleteItemAsync(AUTH_TOKEN_KEY).catch(() => null);
  await db.runAsync("DELETE FROM auth_session WHERE id = 1");
};
