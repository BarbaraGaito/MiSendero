import { db, initDB } from "../database/database";
import { getAuthSession } from "./authSession";
import { DepartureMessageRequiredError, getDepartureMessage, initDepartureMessages } from "./departureMessages";
import type { RouteTrackingSummary } from "./routeTracking";
import { isTestingLocationActive } from "./testingMode";
import { RouteTrackingPoint } from "../types";

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
// Testing-location sessions live only in memory: neither the session nor its
// synthetic points are persisted, listed as activity or queued for sync.
let simulatedRoute: RouteSessionState | null = null;
let simulatedPoints: RouteTrackingPoint[] = [];
const findSimulatedRoute = (userId: number | null, trailId?: number, startedAt?: number) =>
  simulatedRoute && simulatedRoute.user_id === userId &&
  (trailId === undefined || (simulatedRoute.trail_id === trailId && simulatedRoute.started_at === startedAt))
    ? simulatedRoute : null;
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
  const userId = await owner();
  const simulated = findSimulatedRoute(userId, trailId, startedAt);
  if (simulated) return { ...simulated };
  return db.getFirstAsync<RouteSessionState>(
    "SELECT * FROM route_runtime WHERE user_id = ? AND trail_id = ? AND started_at = ?",
    [userId, trailId, startedAt]
  );
};
export const getActiveRouteSession = async () => {
  await init();
  const userId = await owner();
  const simulated = findSimulatedRoute(userId);
  if (simulated && simulated.state !== "completed") return { ...simulated };
  return db.getFirstAsync<RouteSessionState>(
    "SELECT * FROM route_runtime WHERE user_id = ? AND state != 'completed' ORDER BY started_at DESC LIMIT 1",
    [userId]
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
  if (simulated) {
    // A test run never requires, reads or consumes a real departure plan, so it
    // may only start while testing-location mode is verified for this account.
    if (!await isTestingLocationActive()) throw new Error("El modo prueba no está activo. Volvé a iniciar el recorrido.");
    simulatedRoute = { user_id: userId, trail_id: trailId, started_at: startedAt, state: "running",
      paused_at: null, paused_ms: 0, ended_at: null, simulated: 1 };
    simulatedPoints = [];
    notify();
    return { ...simulatedRoute };
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
  const userId = await owner();
  const simulated = findSimulatedRoute(userId, trailId, startedAt);
  if (simulated) {
    if (simulated.state === "running") simulatedRoute = { ...simulated, state: "paused", paused_at: Date.now() };
  } else {
    await db.runAsync("UPDATE route_runtime SET state = 'paused', paused_at = ? WHERE user_id = ? AND trail_id = ? AND started_at = ? AND state = 'running'",
      [Date.now(), userId, trailId, startedAt]);
  }
  notify();
};
export const resumeRouteSession = async (trailId: number, startedAt: number) => {
  await init();
  const userId = await owner();
  const simulated = findSimulatedRoute(userId, trailId, startedAt);
  if (simulated) {
    if (simulated.state === "paused") {
      simulatedRoute = { ...simulated, state: "running", paused_at: null,
        paused_ms: simulated.paused_ms + Math.max(0, Date.now() - (simulated.paused_at ?? Date.now())) };
    }
  } else {
    await db.runAsync("UPDATE route_runtime SET paused_ms = paused_ms + MAX(0, ? - paused_at), paused_at = NULL, state = 'running' WHERE user_id = ? AND trail_id = ? AND started_at = ? AND state = 'paused'",
      [Date.now(), userId, trailId, startedAt]);
  }
  notify();
};
export const finishRouteSession = async (trailId: number, startedAt: number) => {
  await init();
  const userId = await owner();
  const simulated = findSimulatedRoute(userId, trailId, startedAt);
  if (simulated) {
    if (simulated.state !== "completed") simulatedRoute = { ...simulated, state: "completed", ended_at: Date.now() };
  } else {
    await db.runAsync("UPDATE route_runtime SET state = 'completed', ended_at = ? WHERE user_id = ? AND trail_id = ? AND started_at = ? AND state != 'completed'",
      [Date.now(), userId, trailId, startedAt]);
  }
  notify();
  return getRouteSession(trailId, startedAt);
};

export const saveSimulatedRouteTrackingPoint = (point: RouteTrackingPoint) => {
  if (simulatedRoute?.trail_id !== point.trailId || simulatedRoute.started_at !== point.startedAt) return;
  simulatedPoints.push({ ...point, simulated: true });
};
export const getSimulatedRouteTrackingSummary = (trailId: number, startedAt: number): RouteTrackingSummary => {
  const points = simulatedRoute?.trail_id === trailId && simulatedRoute.started_at === startedAt ? simulatedPoints : [];
  const lastPoint = points[points.length - 1] ?? null;
  return {
    points: points.length,
    distanceMeters: points.reduce((total, point) => total + point.distanceDeltaMeters, 0),
    startedAt,
    lastRecordedAt: lastPoint?.recordedAt ?? null,
    lastPoint,
  };
};
