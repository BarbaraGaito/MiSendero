const { query } = require("./db");

const isNotificationChannelConfigured = () => {
  try {
    return new URL(process.env.ALERT_WEBHOOK_URL).protocol === "https:" && !!process.env.ALERT_WEBHOOK_TOKEN;
  } catch { return false; }
};

// The receiver must durably deduplicate Idempotency-Key before forwarding to
// SMS/push. HTTP acceptance is deliberately never represented as delivery.
const sendTripNotification = async (plan, notificationId) => {
  if (!isNotificationChannelConfigured()) throw new Error("notification-channel-unavailable");
  const response = await fetch(process.env.ALERT_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${process.env.ALERT_WEBHOOK_TOKEN}`, "Idempotency-Key": `trip-overdue-${notificationId}` },
    signal: AbortSignal.timeout(10000),
    body: JSON.stringify({
      event: "trip_return_unconfirmed", notification_id: `trip-overdue-${notificationId}`,
      contact: { name: plan.contact_name, phone: plan.contact_phone },
      expected_return_at: plan.expected_return_at, grace_minutes: plan.grace_minutes,
      message: `${plan.user_name} no confirmó el regreso de ${plan.trail_name || "su salida"} en MiSendero. Hora prevista: ${new Date(plan.expected_return_at).toISOString()}; margen: ${plan.grace_minutes} min. Puede estar sin señal. Esto no confirma un accidente. Intentá contactarlo y seguí el acuerdo previo de la salida.`,
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
    const result = await query(`SELECT p.*, u.name AS user_name, t.name AS trail_name FROM trip_plans p JOIN users u ON u.id = p.user_id LEFT JOIN trails t ON t.id = p.trail_id WHERE p.id = $1`, [job.plan_id]);
    const plan = result.rows[0];
    if (!plan || !["active", "overdue"].includes(plan.status)) {
      await query("UPDATE trip_notifications SET status = 'cancelled', lease_until = NULL WHERE id = $1", [job.id]);
      continue;
    }
    await query("UPDATE trip_plans SET status = 'overdue' WHERE id = $1 AND status = 'active'", [plan.id]);
    try {
      await send(plan, job.id);
      await query("UPDATE trip_notifications SET status = 'accepted', accepted_at = $2, lease_until = NULL, last_error = NULL WHERE id = $1", [job.id, timestamp]);
      accepted++;
    } catch {
      const retryAt = new Date(now.getTime() + Math.min(900000, 30000 * 2 ** Math.min(job.attempts - 1, 5))).toISOString();
      await query("UPDATE trip_notifications SET status = 'pending', lease_until = NULL, next_attempt_at = $2, last_error = 'channel-unavailable' WHERE id = $1", [job.id, retryAt]);
    }
  }
  return { accepted };
}
module.exports = { isNotificationChannelConfigured, processTripNotifications };
