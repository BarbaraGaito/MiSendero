jest.mock("../api", () => ({ getTripPlans: jest.fn() }));
import { getTripPlans } from "../api";
import { saveAuthSession, clearAuthSession } from "../authSession";
import { db, initDB } from "../../database/database";
import { getSavedTripPlans, saveTripPlanLocally, refreshTripPlans } from "../tripPlans";
const plan = { id: 1, user_id: 31, trail_id: 7, status: "active" } as any;
beforeEach(async () => { jest.clearAllMocks(); await initDB(); await db.execAsync("CREATE TABLE IF NOT EXISTS saved_trip_plans (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, trail_id INTEGER NOT NULL, plan_json TEXT NOT NULL); DELETE FROM saved_trip_plans;"); await saveAuthSession({ token: "token", user: { id: 31, name: "Ana", email: "ana@example.test" } }); });
test("offline trip cache enforces account and trail ownership and replaces server-confirmed status", async () => {
  await saveTripPlanLocally(plan); await saveTripPlanLocally({ ...plan, id: 2, user_id: 99 }); await saveTripPlanLocally({ ...plan, id: 3, trail_id: 8 });
  expect(await getSavedTripPlans(7)).toEqual([plan]); await saveTripPlanLocally({ ...plan, status: "checked_in" }); expect(await getSavedTripPlans(7)).toEqual([{ ...plan, status: "checked_in" }]);
  await clearAuthSession(); expect(await getSavedTripPlans(7)).toEqual([]); expect(await refreshTripPlans(7)).toEqual([]); expect(getTripPlans).not.toHaveBeenCalled();
});
test("refresh retains local plans on network failure and persists only the authenticated server response", async () => {
  await saveTripPlanLocally(plan); (getTripPlans as jest.Mock).mockRejectedValueOnce(new Error("offline")); await expect(refreshTripPlans(7)).rejects.toThrow("offline"); expect(await getSavedTripPlans(7)).toEqual([plan]);
  (getTripPlans as jest.Mock).mockResolvedValue([{ ...plan, status: "cancelled" }, { ...plan, id: 2, trail_id: 8 }]); expect(await refreshTripPlans(7)).toEqual([{ ...plan, status: "cancelled" }]); expect(await getSavedTripPlans(7)).toEqual([{ ...plan, status: "cancelled" }]);
});
