import { db } from "../database/connection";
import * as SecureStore from "expo-secure-store";
import { AuthSession } from "../types";
import { isAccountDeletionPending } from "./accountLifecycle";

const AUTH_TOKEN_KEY = "misendero.auth.token";
const SECURE_TOKEN_SENTINEL = "__secure_store__";
// Web and platforms without a secure keystore use a session held in memory only.
let volatileSession: AuthSession | null = null;

const initAuthSessionTable = async () => {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS auth_session (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      token TEXT NOT NULL,
      user_json TEXT NOT NULL
    );
  `);
};

export const saveAuthSession = async (session: AuthSession, options: { deletionRetryLogin?: boolean } = {}) => {
  if (!options.deletionRetryLogin && await isAccountDeletionPending(session.user.id)) throw new Error("La cuenta tiene una baja pendiente. Completá la eliminación desde Perfil.");
  await initAuthSessionTable();
  const canUseSecureStore = await SecureStore.isAvailableAsync().catch(() => false);
  if (canUseSecureStore) {
    await SecureStore.setItemAsync(AUTH_TOKEN_KEY, session.token);
  } else {
    await db.runAsync("DELETE FROM auth_session WHERE id = 1");
    volatileSession = session;
    return;
  }

  await db.runAsync(
    `INSERT OR REPLACE INTO auth_session (id, token, user_json)
     VALUES (1, ?, ?)`,
    [SECURE_TOKEN_SENTINEL, JSON.stringify(session.user)]
  );
  volatileSession = null;
};

export const getAuthSession = async (): Promise<AuthSession | null> => {
  await initAuthSessionTable();

  const row = await db.getFirstAsync<{ token: string; user_json: string }>(
    "SELECT token, user_json FROM auth_session WHERE id = 1"
  );

  if (!row) return volatileSession;

  // Discard legacy plaintext tokens; require a fresh login instead of copying them.
  if (row.token !== SECURE_TOKEN_SENTINEL) {
    await clearAuthSession();
    return null;
  }

  const canUseSecureStore = await SecureStore.isAvailableAsync().catch(() => false);
  const secureToken = canUseSecureStore
    ? await SecureStore.getItemAsync(AUTH_TOKEN_KEY).catch(() => null)
    : null;
  const token = secureToken;

  if (!token || token === SECURE_TOKEN_SENTINEL) return null;

  return {
    token,
    user: JSON.parse(row.user_json),
  };
};

export const clearAuthSession = async () => {
  volatileSession = null;
  await initAuthSessionTable();
  await SecureStore.deleteItemAsync(AUTH_TOKEN_KEY).catch(() => null);
  await db.runAsync("DELETE FROM auth_session WHERE id = 1");
};
