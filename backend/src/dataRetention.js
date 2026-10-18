const { getPool } = require("./db");
const DAY = 86400000;
let inFlight;
const applyRemoteRetention = (options = {}) => inFlight ||= purge(options).finally(() => { inFlight = null; });
async function purge({ now = new Date() } = {}) {
  if (!Number.isFinite(now.getTime())) throw new Error("Invalid retention clock");
  const client = await (await getPool()).connect();
  try {
    await client.query("BEGIN");
    const limit = new Date(now.getTime()-30*DAY).toISOString();
    const sos = await client.query(`UPDATE emergency_alerts SET latitude=NULL, longitude=NULL, trail_id=NULL,
      contact_name=NULL,contact_phone=NULL,message_body=NULL,last_known_at=NULL,device_battery_percent=NULL,
      retention_purged_at=$1 WHERE retention_eligible_at IS NOT NULL AND retention_eligible_at <= $2
      AND created_at <= $2 AND retention_purged_at IS NULL AND status='registered'`,[now.toISOString(),limit]);
    // Lock closed plans before inspecting jobs, matching the notification worker's plan lock.
    const plans = await client.query(`SELECT id FROM trip_plans WHERE retention_eligible_at IS NOT NULL
      AND retention_eligible_at <= $1 AND closed_at <= $1 AND status IN ('checked_in','cancelled')
      AND retention_purged_at IS NULL FOR UPDATE`,[limit]);
    let closed = 0;
    for (const plan of plans.rows) {
      const jobs = await client.query("SELECT status FROM trip_notifications WHERE plan_id=$1",[plan.id]);
      if (jobs.rows.some(job => ["pending","processing"].includes(job.status))) continue;
      await client.query("DELETE FROM trip_notifications WHERE plan_id=$1",[plan.id]);
      await client.query(`UPDATE trip_plans SET contact_name='',contact_phone='',trail_id=NULL,
        retention_purged_at=$2 WHERE id=$1`,[plan.id,now.toISOString()]); closed++;
    }
    await client.query("DELETE FROM auth_revocations WHERE expires_at <= $1",[now.toISOString()]);
    await client.query("DELETE FROM api_write_budgets WHERE window_start < $1",[new Date(now.getTime()-2*DAY).toISOString()]);
    await client.query("COMMIT");
    return { sos: sos.rowCount, plans: closed };
  } catch (error) { await client.query("ROLLBACK"); throw error; }
  finally { client.release(); }
}
module.exports = { applyRemoteRetention };
