import { db, initDB } from "../database/database";
import { getAuthSession } from "./authSession";
import { getTripPlans, TripPlanRecord } from "./api";

const init = async () => {
  await initDB();
  await db.execAsync("CREATE TABLE IF NOT EXISTS saved_trip_plans (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, trail_id INTEGER NOT NULL, plan_json TEXT NOT NULL)");
};
export const saveTripPlanLocally = async (plan: TripPlanRecord) => {
  await init();
  const user = (await getAuthSession())?.user.id;
  if (user !== plan.user_id) return;
  await db.runAsync("INSERT OR REPLACE INTO saved_trip_plans (id, user_id, trail_id, plan_json) VALUES (?, ?, ?, ?)",
    [plan.id, user, plan.trail_id, JSON.stringify(plan)]);
};
export const getSavedTripPlans = async (trailId: number) => {
  await init();
  const user = (await getAuthSession())?.user.id ?? null;
  const rows = await db.getAllAsync<{ plan_json: string }>("SELECT plan_json FROM saved_trip_plans WHERE user_id = ? AND trail_id = ? ORDER BY id DESC", [user, trailId]);
  return rows.map((row) => JSON.parse(row.plan_json) as TripPlanRecord);
};
export const refreshTripPlans = async (trailId: number) => {
  const session = await getAuthSession();
  if (!session) return [];
  const plans = await getTripPlans(session.token);
  for (const plan of plans) await saveTripPlanLocally(plan);
  return plans.filter((plan) => plan.trail_id === trailId);
};
