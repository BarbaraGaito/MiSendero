import { db } from "../database/connection";
import * as SecureStore from "expo-secure-store";
import { AuthSession } from "../types";
import { isAccountDeletionPending } from "./accountLifecycle";
import { invalidateSessionContext } from "./sessionEpoch";

const AUTH_TOKEN_KEY = "misendero.auth.token";
const SECURE_TOKEN_SENTINEL = "__secure_store__";
// Web and platforms without a secure keystore use a session held in memory only.
let volatileSession: AuthSession | null = null;
let transitions = 0;
let mutations: Promise<unknown> = Promise.resolve();
const mutateSession = async (operation: () => Promise<void>) => {
  invalidateSessionContext();
  transitions += 1;
  const result = mutations.then(operation, operation);
  mutations = result.catch(() => undefined);
  try { await result; } finally { transitions -= 1; }
};

const initAuthSessionTable = async () => {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS auth_session (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      token TEXT NOT NULL,
      user_json TEXT NOT NULL
    );
  `);
};

export const saveAuthSession = async (session: AuthSession, options: { deletionRetryLogin?: boolean } = {}) => mutateSession(async () => {
  if (!options.deletionRetryLogin && await isAccountDeletionPending(session.user.id)) throw new Error("La cuenta tiene una baja pendiente. Completá la eliminación desde Perfil.");
  await initAuthSessionTable();
  const canUseSecureStore = await SecureStore.isAvailableAsync().catch(() => false);
  if (canUseSecureStore) {
    await SecureStore.setItemAsync(AUTH_TOKEN_KEY, session.token, { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY });
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
});

export const getAuthSession = async (): Promise<AuthSession | null> => {
  if (transitions) return null;
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

export const clearAuthSession = async () => mutateSession(async () => {
  volatileSession = null;
  await initAuthSessionTable();
  await db.runAsync("DELETE FROM auth_session WHERE id = 1");
  if (!(await SecureStore.isAvailableAsync().catch(() => false))) return;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try { await SecureStore.deleteItemAsync(AUTH_TOKEN_KEY); return; }
    catch { /* Retry transient keystore failures, then report actionable state. */ }
  }
  throw new Error("La sesión local se cerró, pero no pudimos borrar la credencial del dispositivo. Volvé a intentar cerrar sesión cuando el equipo esté desbloqueado.");
});
