import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";
import { revokeSession, ApiError } from "./api";
import { clearAuthSession } from "./authSession";
import { captureAccountContext, assertAccountContext } from "./accountContext";

const PENDING_KEY = "misendero.pending-revocations.v1";
type Pending = { token: string; queuedAt: number };
let inFlight: Promise<void> | null = null;
const readPending = async (): Promise<Pending[]> => {
  if (Platform.OS === "web") return [];
  const raw = await SecureStore.getItemAsync(PENDING_KEY);
  if (!raw) return [];
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed) || parsed.some(v => typeof v?.token !== "string" || !Number.isFinite(v.queuedAt))) throw new Error("No pudimos recuperar la revocación pendiente. Reintentá con el equipo desbloqueado.");
  return parsed;
};
const writePending = async (items: Pending[]) => {
  if (items.length) await SecureStore.setItemAsync(PENDING_KEY, JSON.stringify(items), { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY });
  else await SecureStore.deleteItemAsync(PENDING_KEY);
};
const revoke = async (token: string) => {
  try { await revokeSession(token); }
  catch (error) {
    // Expired/revoked/deleted tokens already have no access.
    if (!(error instanceof ApiError && error.status === 401)) throw error;
  }
};
export const flushPendingRevocations = () => inFlight ??= (async () => {
  const pending = await readPending();
  // Preserve concurrently added records: logout waits for this flush before enqueue.
  for (const item of pending) {
    if (Date.now() - item.queuedAt < 8 * 86400000) await revoke(item.token);
    await writePending((await readPending()).filter(v => v.token !== item.token));
  }
})().finally(() => { inFlight = null; });

export const logoutSession = async () => {
  const context = await captureAccountContext();
  let remoteRevoked = !context.token;
  let pendingError: Error | null = null;
  if (context.token) {
    try { await revoke(context.token); remoteRevoked = true; }
    catch {
      try {
        await inFlight?.catch(() => undefined);
        if (Platform.OS === "web" || !await SecureStore.isAvailableAsync()) throw new Error("no-keystore");
        const pending = await readPending();
        if (!pending.some(v => v.token === context.token)) {
          if (pending.length >= 8) throw new Error("pending-limit");
          await writePending([...pending, { token: context.token, queuedAt: Date.now() }]);
        }
      } catch { pendingError = new Error("La sesión local se cerró. No se pudo confirmar ni guardar la revocación remota; la credencial podría seguir vigente hasta vencer. Reintentá con conexión."); }
    }
  }
  assertAccountContext(context);
  await clearAuthSession();
  if (pendingError) throw pendingError;
  return { remoteRevoked };
};
