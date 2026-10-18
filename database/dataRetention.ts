import { db, withWriteTransaction } from "./connection";
const DAY = 86400000;
const tables = ["wearable_metric_samples", "route_tracking_points", "pending_operations"] as const;
// Nullable migration preserves historical rows. Only subsequent INSERTs opt in.
export const installRetentionPolicy = async () => {
  for (const table of tables) {
    const columns = await db.getAllAsync<{name:string}>(`PRAGMA table_info(${table})`);
    if (!columns.some(column => column.name === "retention_eligible_at"))
      await db.execAsync(`ALTER TABLE ${table} ADD COLUMN retention_eligible_at INTEGER`);
    await db.execAsync(`CREATE TRIGGER IF NOT EXISTS retention_new_${table} AFTER INSERT ON ${table}
      WHEN NEW.retention_eligible_at IS NULL BEGIN
      UPDATE ${table} SET retention_eligible_at = NEW.created_at WHERE id = NEW.id; END`);
  }
};
export const applyLocalRetention = async (now = Date.now()) => withWriteTransaction(async tx => {
  if (!Number.isFinite(now)) throw new Error("Invalid retention clock");
  const health = await tx.runAsync(`DELETE FROM wearable_metric_samples
    WHERE retention_eligible_at IS NOT NULL AND retention_eligible_at <= ? AND created_at <= ?`, [now-7*DAY,now-7*DAY]);
  const points = await tx.runAsync(`DELETE FROM route_tracking_points
    WHERE retention_eligible_at IS NOT NULL AND retention_eligible_at <= ? AND created_at <= ?
    AND EXISTS (SELECT 1 FROM sessions s WHERE s.user_id IS route_tracking_points.user_id
      AND s.trail_id = route_tracking_points.trail_id AND s.started_at = route_tracking_points.started_at
      AND s.ended_at IS NOT NULL AND s.completion_status != 'paused')`, [now-90*DAY,now-90*DAY]);
  // Keep dedupe key, server ID and terminal state: never re-create a confirmed event.
  const payloads = await tx.runAsync(`UPDATE pending_operations SET payload_json = '{}', last_error = NULL
    WHERE retention_eligible_at IS NOT NULL AND retention_eligible_at <= ? AND updated_at <= ?
    AND status IN ('synced','abandoned') AND payload_json != '{}'`, [now-7*DAY,now-7*DAY]);
  const cache = await tx.getFirstAsync<{name:string}>("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'saved_trip_plans'");
  if (cache) {
    const rows = await tx.getAllAsync<{id:number;user_id:number;plan_json:string}>("SELECT * FROM saved_trip_plans");
    for (const row of rows) {
      let plan; try { plan = JSON.parse(row.plan_json); } catch { continue; }
      if (["checked_in","cancelled"].includes(plan.status) && !["pending","processing"].includes(plan.notification_status) && plan.retention_eligible_at && plan.closed_at
          && Date.parse(plan.retention_eligible_at) <= now-30*DAY && Date.parse(plan.closed_at) <= now-30*DAY)
        await tx.runAsync("DELETE FROM saved_trip_plans WHERE id = ? AND user_id = ?",[row.id,row.user_id]);
    }
  }
  return { health: health.changes, points: points.changes, payloads: payloads.changes };
});
