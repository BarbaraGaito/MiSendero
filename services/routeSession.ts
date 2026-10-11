import { db, initDB } from "../database/database";
import { getAuthSession } from "./authSession";
import { DepartureMessageRequiredError, getDepartureMessage, initDepartureMessages } from "./departureMessages";

export interface RouteSessionState {
  user_id: number;
  trail_id: number;
  started_at: number;
  state: "running" | "paused" | "completed";
  paused_at: number | null;
  paused_ms: number;
  ended_at: number | null;
  simulated: number;
}
const listeners = new Set<() => void>();
export const subscribeRouteSession = (listener: () => void) => {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
};
const notify = () => listeners.forEach((listener) => listener());
const owner = async () => (await getAuthSession())?.user.id ?? null;
const init = async () => {
  await initDB();
  await initDepartureMessages();
  await db.execAsync(`CREATE TABLE IF NOT EXISTS route_runtime (
    user_id INTEGER NOT NULL, trail_id INTEGER NOT NULL, started_at INTEGER NOT NULL,
    state TEXT NOT NULL, paused_at INTEGER, paused_ms INTEGER NOT NULL DEFAULT 0,
    ended_at INTEGER, simulated INTEGER NOT NULL DEFAULT 0, departure_message_id INTEGER,
    PRIMARY KEY (user_id, trail_id, started_at)
  )`);
  const columns = await db.getAllAsync<{ name: string }>("PRAGMA table_info(route_runtime)");
  if (!columns.some((column) => column.name === "departure_message_id")) {
    try {
      await db.execAsync("ALTER TABLE route_runtime ADD COLUMN departure_message_id INTEGER");
    } catch (error) {
      if (!(error instanceof Error && error.message.toLowerCase().includes("duplicate column"))) throw error;
    }
  }
  await db.execAsync(`
    CREATE UNIQUE INDEX IF NOT EXISTS idx_route_departure_message ON route_runtime (departure_message_id)
    WHERE departure_message_id IS NOT NULL;
    CREATE TRIGGER IF NOT EXISTS consume_route_departure_message AFTER INSERT ON route_runtime
    WHEN NEW.departure_message_id IS NOT NULL
    BEGIN
      UPDATE departure_messages SET used_started_at = NEW.started_at WHERE id = NEW.departure_message_id;
    END;
  `);
};

export const getRouteSession = async (trailId: number, startedAt: number) => {
  await init();
  return db.getFirstAsync<RouteSessionState>(
    "SELECT * FROM route_runtime WHERE user_id = ? AND trail_id = ? AND started_at = ?",
    [await owner(), trailId, startedAt]
  );
};
export const getActiveRouteSession = async () => {
  await init();
  return db.getFirstAsync<RouteSessionState>(
    "SELECT * FROM route_runtime WHERE user_id = ? AND state != 'completed' ORDER BY started_at DESC LIMIT 1",
    [await owner()]
  );
};
export const ensureRouteSession = async (trailId: number, startedAt: number, simulated = false) => {
  await init();
  const userId = await owner();
  if (!userId) throw new Error("Iniciá sesión para registrar el recorrido.");
  const existing = await getRouteSession(trailId, startedAt);
  if (existing) return existing;
  const active = await getActiveRouteSession();
  if (active && (active.trail_id !== trailId || active.started_at !== startedAt)) {
    throw new Error("Ya tenés un recorrido abierto. Retomalo o finalizalo antes de empezar otro.");
  }
  const message = await getDepartureMessage(trailId);
  if (!message || message.user_id !== userId) throw new DepartureMessageRequiredError();
  const now = Date.now();
  const inserted = await db.runAsync(
    `INSERT OR IGNORE INTO route_runtime (user_id, trail_id, started_at, state, simulated, departure_message_id)
     SELECT ?, ?, ?, 'running', ?, id FROM departure_messages
     WHERE id = ? AND user_id = ? AND trail_id = ? AND contact_phone = ?
       AND used_started_at IS NULL AND invalidated_at IS NULL
       AND expected_return_at > ? AND sent_at <= ?
       AND NOT EXISTS (SELECT 1 FROM route_runtime WHERE user_id = ? AND state != 'completed')`,
    [userId, trailId, startedAt, simulated ? 1 : 0, message.id, userId, trailId, message.contact_phone, now, now, userId]
  );
  if (!inserted.changes) {
    const concurrent = await getRouteSession(trailId, startedAt);
    if (concurrent) return concurrent;
    throw new DepartureMessageRequiredError();
  }
  notify();
  return getRouteSession(trailId, startedAt);
};
export const activeRouteSeconds = (route: RouteSessionState, now = Date.now()) =>
  Math.max(0, Math.floor(((route.ended_at ?? now) - route.started_at - route.paused_ms -
    (route.paused_at === null ? 0 : (route.ended_at ?? now) - route.paused_at)) / 1000));

export const pauseRouteSession = async (trailId: number, startedAt: number) => {
  await init();
  await db.runAsync("UPDATE route_runtime SET state = 'paused', paused_at = ? WHERE user_id = ? AND trail_id = ? AND started_at = ? AND state = 'running'",
    [Date.now(), await owner(), trailId, startedAt]);
  notify();
};
export const resumeRouteSession = async (trailId: number, startedAt: number) => {
  await init();
  await db.runAsync("UPDATE route_runtime SET paused_ms = paused_ms + MAX(0, ? - paused_at), paused_at = NULL, state = 'running' WHERE user_id = ? AND trail_id = ? AND started_at = ? AND state = 'paused'",
    [Date.now(), await owner(), trailId, startedAt]);
  notify();
};
export const finishRouteSession = async (trailId: number, startedAt: number) => {
  await init();
  await db.runAsync("UPDATE route_runtime SET state = 'completed', ended_at = ? WHERE user_id = ? AND trail_id = ? AND started_at = ? AND state != 'completed'",
    [Date.now(), await owner(), trailId, startedAt]);
  notify();
  return getRouteSession(trailId, startedAt);
};
