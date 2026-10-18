import { db, initDB, recoverActivityOutbox } from "../database";
import { getOrCreateCompletedSession, getOrCreatePausedSession } from "../sessionsRepository";
import { saveAuthSession } from "../../services/authSession";
const input = { trailId: 7, startedAt: 1792231200000, endedAt: 1792231260000, duration: 60, distance: 100 };
beforeAll(async () => {
  await initDB();
  await saveAuthSession({ token: "durability", user: { id: 771, name: "Fixture", email: "fixture@example.test" } });
  await db.execAsync(`CREATE TABLE IF NOT EXISTS route_runtime (
    user_id INTEGER, trail_id INTEGER, started_at INTEGER, state TEXT, ended_at INTEGER, simulated INTEGER)`);
});
beforeEach(async () => {
  await db.execAsync("DROP TRIGGER IF EXISTS reject_outbox; DELETE FROM pending_operations; DELETE FROM sessions; DELETE FROM sqlite_sequence WHERE name = 'sessions'; DELETE FROM route_runtime;");
  await db.runAsync("INSERT INTO route_runtime VALUES (?, ?, ?, 'running', NULL, 0)", [771, 7, input.startedAt]);
});
test("failure to persist the outbox rolls back session and runtime, then retry commits both", async () => {
  await db.execAsync(`CREATE TRIGGER reject_outbox BEFORE INSERT ON pending_operations
    BEGIN SELECT RAISE(ABORT, 'outbox disk failure'); END;`);
  await expect(getOrCreateCompletedSession(input)).rejects.toThrow("outbox disk failure");
  expect(await db.getAllAsync("SELECT * FROM sessions")).toHaveLength(0);
  expect(await db.getFirstAsync("SELECT state FROM route_runtime")).toEqual({ state: "running" });
  await db.execAsync("DROP TRIGGER reject_outbox");
  const result = await getOrCreateCompletedSession(input);
  const outbox = await db.getAllAsync<{ payload_json: string }>("SELECT payload_json FROM pending_operations");
  expect(outbox).toHaveLength(1);
  expect(JSON.parse(outbox[0].payload_json).client_session_id).toBe(result.session.client_session_id);
  expect(await db.getFirstAsync("SELECT state FROM route_runtime")).toEqual({ state: "completed" });
});
test("two simultaneous completions reuse one UUID and one operation", async () => {
  const results = await Promise.all([getOrCreateCompletedSession(input), getOrCreateCompletedSession(input)]);
  expect(results[0].session.client_session_id).toMatch(/^[a-f0-9-]{36}$/);
  expect(results[1].session.client_session_id).toBe(results[0].session.client_session_id);
  expect(await db.getAllAsync("SELECT * FROM sessions")).toHaveLength(1);
  expect(await db.getAllAsync("SELECT * FROM pending_operations")).toHaveLength(1);
});
test("reused SQLite row ID does not reuse activity identity; pause retains its UUID", async () => {
  const a = await getOrCreateCompletedSession(input);
  await db.execAsync("DELETE FROM sessions; DELETE FROM sqlite_sequence WHERE name = 'sessions'");
  const paused = await getOrCreatePausedSession({ ...input, startedAt: input.startedAt + 100000 });
  expect(paused.id).toBe(a.session.id);
  const b = await getOrCreateCompletedSession({ ...input, startedAt: paused.started_at, endedAt: input.endedAt + 100000 });
  expect(b.session.client_session_id).toBe(paused.client_session_id);
  expect(b.session.client_session_id).not.toBe(a.session.client_session_id);
  expect(await db.getAllAsync("SELECT * FROM pending_operations")).toHaveLength(2);
});

test("legacy rows missing an outbox are recovered; possibly acknowledged identities remain unchanged", async () => {
  for (const [offset, status] of [[0, null], [1, "pending"], [2, "failed"], [3, "synced"]] as const) {
    const row = await db.runAsync(`INSERT INTO sessions (user_id, trail_id, started_at, ended_at, duration, distance)
      VALUES (771, 7, ?, ?, 60, 100)`, [input.startedAt + offset, input.endedAt + offset]);
    if (status) await db.runAsync(`INSERT INTO pending_operations (entity_type, user_id, payload_json, dedupe_key, status, retry_count, created_at, updated_at)
      VALUES ('activity', 771, ?, ?, ?, ?, 1, 1)`,
      [JSON.stringify({ client_session_id: `local-session-${row.lastInsertRowId}` }), `771:activity:local-session-${row.lastInsertRowId}`, status, status === "failed" ? 1 : 0]);
  }
  await recoverActivityOutbox(); await recoverActivityOutbox();
  const sessions = await db.getAllAsync<{ id: number; client_session_id: string }>("SELECT * FROM sessions ORDER BY id");
  expect(sessions.slice(0, 2).every(row => /^[a-f0-9-]{36}$/.test(row.client_session_id))).toBe(true);
  expect(sessions[2].client_session_id).toBe(`local-session-${sessions[2].id}`);
  expect(sessions[3].client_session_id).toBe(`local-session-${sessions[3].id}`);
  expect(await db.getAllAsync("SELECT * FROM pending_operations")).toHaveLength(4);
});
