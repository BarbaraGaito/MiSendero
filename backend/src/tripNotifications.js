const { query, getPool } = require("./db");

const isNotificationChannelConfigured = () => {
  try {
    return new URL(process.env.ALERT_WEBHOOK_URL).protocol === "https:" && !!process.env.ALERT_WEBHOOK_TOKEN;
  } catch { return false; }
};

// One SMS segment: at most 160 characters of the GSM-7 alphabet, so accents
// are stripped (they would switch the whole message to 70-character UCS-2).
const SMS_SEGMENT = 160;
const gsmText = (value, max) => String(value || "").normalize("NFD").replace(/[̀-ͯ]/g, "")
  .replace(/[^A-Za-z0-9 .,()'-]/g, "").replace(/\s+/g, " ").trim().slice(0, max).trim();
const buildOverdueMessage = (plan) => {
  const time = new Intl.DateTimeFormat("es-AR", { timeZone: "America/Argentina/Buenos_Aires", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .format(new Date(plan.expected_return_at));
  const name = gsmText(plan.user_name, 18) || "Tu contacto";
  const text = (trail) => `MiSendero: ${name} no confirmo su regreso de ${trail}. Hora prevista ${time} (+${plan.grace_minutes} min). ` +
    "Puede estar sin senal; no confirma un accidente.";
  // The trail name takes whatever room the fixed text leaves in the segment.
  return text(gsmText(plan.trail_name, SMS_SEGMENT - text("").length) || "su salida");
};

// The receiver must durably deduplicate Idempotency-Key before forwarding to
// SMS/push. HTTP acceptance is deliberately never represented as delivery.
const sendTripNotification = async (plan, notificationId) => {
  if (!isNotificationChannelConfigured()) throw new Error("notification-channel-unavailable");
  const response = await fetch(process.env.ALERT_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.ALERT_WEBHOOK_TOKEN}`, "Idempotency-Key": `trip-overdue-${notificationId}` },
    signal: AbortSignal.timeout(10000),
    redirect: "error",
    body: JSON.stringify({
      event: "trip_return_unconfirmed", notification_id: `trip-overdue-${notificationId}`,
      contact: { name: plan.contact_name, phone: plan.contact_phone },
      expected_return_at: plan.expected_return_at, grace_minutes: plan.grace_minutes,
      message: buildOverdueMessage(plan),
    }),
  });
  if (!response.ok) throw new Error(`notification-channel-http-${response.status}`);
};

let inFlight = null;
const processTripNotifications = (options = {}) => {
  if (inFlight) return inFlight;
  inFlight = processDue(options).finally(() => { inFlight = null; });
  return inFlight;
};
async function processDue({ now = new Date(), send = sendTripNotification } = {}) {
  const timestamp = now.toISOString();
  // Reconcile after crashes, including a crash between plan and job insertion.
  const plans = await query("SELECT id, expected_return_at, grace_minutes FROM trip_plans WHERE status IN ('active', 'overdue')");
  for (const plan of plans.rows) {
    const due = new Date(new Date(plan.expected_return_at).getTime() + plan.grace_minutes * 60000).toISOString();
    await query(`INSERT INTO trip_notifications (plan_id, due_at, next_attempt_at) VALUES ($1, $2, $2) ON CONFLICT (plan_id) DO NOTHING`, [plan.id, due]);
  }
  const candidates = await query(`SELECT id FROM trip_notifications WHERE status IN ('pending', 'processing') AND next_attempt_at <= $1 AND (lease_until IS NULL OR lease_until < $1) ORDER BY due_at LIMIT 50`, [timestamp]);
  let accepted = 0;
  for (const item of candidates.rows) {
    const claim = await query(`UPDATE trip_notifications SET status = 'processing', lease_until = $2, attempts = attempts + 1 WHERE id = $1 AND status IN ('pending', 'processing') AND (lease_until IS NULL OR lease_until < $3) RETURNING *`,
      [item.id, new Date(now.getTime() + 60000).toISOString(), timestamp]);
    const job = claim.rows[0];
    if (!job) continue;
    await query("UPDATE trip_plans SET status = 'overdue' WHERE id = $1 AND status = 'active'",[job.plan_id]);
    try {
      const state = await sendUnderAccountLock(job, send, timestamp);
      if (state === "cancelled") await query("UPDATE trip_notifications SET status = 'cancelled', lease_until = NULL WHERE id = $1", [job.id]);
      if (state === "accepted") accepted++;
    } catch {
      const retryAt = new Date(now.getTime() + Math.min(900000, 30000 * 2 ** Math.min(job.attempts - 1, 5))).toISOString();
      await query("UPDATE trip_notifications SET status = 'pending', lease_until = NULL, next_attempt_at = $2, last_error = 'channel-unavailable' WHERE id = $1", [job.id, retryAt]);
    }
  }
  return { accepted };
}
// Share the account lock used by account deletion, then lock plan and job in
// cascade order. The bounded send completes before a concurrent deletion can
// commit. Messages accepted by a receiver still cannot be withdrawn afterwards.
async function sendUnderAccountLock(claim, send, timestamp) {
  const client = await (await getPool()).connect();
  try {
    await client.query("BEGIN");
    const owner=(await client.query("SELECT user_id FROM trip_plans WHERE id = $1",[claim.plan_id])).rows[0];
    if (!owner) {await client.query("COMMIT");return "cancelled";}
    const user=(await client.query("SELECT id, name FROM users WHERE id = $1 FOR UPDATE",[owner.user_id])).rows[0];
    const plan=(await client.query("SELECT * FROM trip_plans WHERE id = $1 FOR UPDATE",[claim.plan_id])).rows[0];
    if (!user || !plan || !["active","overdue"].includes(plan.status)) {await client.query("COMMIT");return "cancelled";}
    const job=(await client.query("SELECT status, lease_until FROM trip_notifications WHERE id = $1 FOR UPDATE",[claim.id])).rows[0];
    if (!job || job.status !== "processing" || new Date(job.lease_until).getTime() !== new Date(claim.lease_until).getTime()) {await client.query("COMMIT");return "stale";}
    const trail=plan.trail_id ? (await client.query("SELECT name FROM trails WHERE id = $1",[plan.trail_id])).rows[0] : null;
    await client.query("UPDATE trip_plans SET status = 'overdue' WHERE id = $1 AND status = 'active'",[plan.id]);
    await send({...plan,user_name:user.name,trail_name:trail?.name},claim.id);
    await client.query("UPDATE trip_notifications SET status = 'accepted', accepted_at = $2, lease_until = NULL, last_error = NULL WHERE id = $1",[claim.id,timestamp]);
    await client.query("COMMIT");return "accepted";
  } catch (error) {await client.query("ROLLBACK");throw error;}
  finally {client.release();}
}
module.exports = { buildOverdueMessage, isNotificationChannelConfigured, processTripNotifications };
