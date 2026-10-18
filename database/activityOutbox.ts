import type { SessionRow } from "../types";
import type { SqlExecutor } from "./connection";
export const persistActivityOutbox = async (tx: SqlExecutor, row: SessionRow) => {
  if (!row.user_id || !row.trail_id || row.ended_at == null || row.completion_status === "paused") return;
  if (!row.client_session_id) throw new Error("activity-identity-missing");
  const deletions = await tx.getFirstAsync("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'account_deletion_state'");
  if (deletions && await tx.getFirstAsync("SELECT user_id FROM account_deletion_state WHERE user_id = ?", [row.user_id])) return;
  const payload = {
    client_session_id: row.client_session_id, trail_id: row.trail_id,
    started_at: new Date(row.started_at).toISOString(), ended_at: new Date(row.ended_at).toISOString(),
    distance_km: Number(((row.distance ?? 0) / 1000).toFixed(2)),
    duration_minutes: Math.round((row.duration ?? 0) / 60), completion_status: row.completion_status,
    route_progress_meters: row.route_progress_meters, route_total_meters: row.route_total_meters,
    ended_latitude: row.ended_latitude, ended_longitude: row.ended_longitude,
  };
  await tx.runAsync(`INSERT OR IGNORE INTO pending_operations
    (entity_type, payload_json, dedupe_key, user_id, status, created_at, updated_at)
    VALUES ('activity', ?, ?, ?, 'pending', ?, ?)`,
    [JSON.stringify(payload), `${row.user_id}:activity:${row.client_session_id}`, row.user_id, Date.now(), Date.now()]);
  const runtime = await tx.getFirstAsync("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'route_runtime'");
  if (runtime) await tx.runAsync(`UPDATE route_runtime SET state = 'completed', ended_at = ?
    WHERE user_id = ? AND trail_id = ? AND started_at = ? AND simulated = 0`,
    [row.ended_at, row.user_id, row.trail_id, row.started_at]);
};
