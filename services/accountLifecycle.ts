import { db } from "../database/connection";

const init = () => db.execAsync(`CREATE TABLE IF NOT EXISTS account_deletion_state (
  user_id INTEGER PRIMARY KEY, requested_at INTEGER NOT NULL
)`);

export const markAccountDeletion = async (userId: number) => {
  await init();
  await db.runAsync("INSERT OR IGNORE INTO account_deletion_state (user_id, requested_at) VALUES (?, ?)", [userId, Date.now()]);
};
export const isAccountDeletionPending = async (userId: number) => {
  await init();
  return !!(await db.getFirstAsync("SELECT user_id FROM account_deletion_state WHERE user_id = ?", [userId]));
};
export const cancelLocalAccountDeletion = async (userId: number) => {
  await init();
  await db.runAsync("DELETE FROM account_deletion_state WHERE user_id = ?", [userId]);
};

// Fixed names only. Optional stores may not have been created on this installation.
export const eraseLocalAccountData = async (userId: number) => {
  await markAccountDeletion(userId);
  const stores: Record<string, string> = {
    pending_operations: "user_id", sessions: "user_id", route_tracking_points: "user_id",
    route_runtime: "user_id", wearable_metric_samples: "user_id", wearable_connections: "user_id",
    fatigue_checkins: "user_id", field_model_assessments: "user_id",
    emergency_contacts: "user_id", saved_trip_plans: "user_id", departure_messages: "user_id",
    user_favorite_trails: "user_id", offline_maps: "user_id", privacy_decision_events: "user_id",
    user_privacy_preferences: "id", user_app_preferences: "id", user_experience_profile: "id",
    hidden_reports: "user_id",
  };
  for (const [table, column] of Object.entries(stores)) {
    const exists = await db.getFirstAsync("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", [table]);
    if (exists) await db.runAsync(`DELETE FROM ${table} WHERE ${column} = ?`, [userId]);
  }
  // Unowned stores from old versions cannot safely be attributed to an account.
  for (const table of ["emergency_contact", "experience_profile", "app_preferences", "legal_acceptance", "heart_rate_logs", "testing_location_mode"]) {
    const exists = await db.getFirstAsync("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", [table]);
    if (exists) await db.runAsync(`DELETE FROM ${table}`);
  }
};
