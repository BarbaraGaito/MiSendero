import { db, initDB } from "../../database/database";
import { saveAuthSession, clearAuthSession } from "../authSession";
import { enqueueUnique, getPendingOperations, getEmergencyOperation, runSync, discardExhaustedOperations } from "../syncQueue";
jest.mock("expo-network", () => ({ getNetworkStateAsync: jest.fn().mockResolvedValue({ isConnected: true, isInternetReachable: true }) }));
jest.mock("../api", () => ({ createEmergencyAlert: jest.fn(), getTrailReports: jest.fn().mockResolvedValue([]) }));
import { createEmergencyAlert } from "../api";
const login = (id: number) => saveAuthSession({ token: `token-${id}`, user: { id, name: "Test", email: `${id}@example.test` } });
beforeEach(async () => { await initDB(); await login(1); await db.runAsync("DELETE FROM pending_operations"); jest.clearAllMocks(); });

test("ownerless and other-account SOS are never sent with the current token", async () => {
  await clearAuthSession();
  const guest = await enqueueUnique("emergency_alert", { client_event_id: "guest" }, "guest");
  await login(1);
  await enqueueUnique("emergency_alert", { client_event_id: "one" }, "one");
  await login(2);
  expect(await getEmergencyOperation(guest)).toBeNull();
  expect(await getPendingOperations()).toEqual([]);
  expect(await runSync()).toEqual({ processed: 0, failed: 0 });
  expect(createEmergencyAlert).not.toHaveBeenCalled();
});

test("concurrent sync calls share one dispatch", async () => {
  (createEmergencyAlert as jest.Mock).mockResolvedValue({ id: 99 });
  await enqueueUnique("emergency_alert", { client_event_id: "one" }, "one");
  await Promise.all([runSync(), runSync(), runSync()]);
  expect(createEmergencyAlert).toHaveBeenCalledTimes(1);
});

test("429 respects Retry-After without exhausting automatic retry attempts", async () => {
  (createEmergencyAlert as jest.Mock).mockRejectedValue(Object.assign(new Error("quota fixture"),{status:429,retryAfterMs:120000}));
  const id=await enqueueUnique("emergency_alert",{client_event_id:"quota-fixture"},"quota-fixture");
  const before=Date.now();
  expect(await runSync()).toEqual({processed:0,failed:1});
  const row=await db.getFirstAsync<{retry_count:number;next_attempt_at:number}>("SELECT retry_count,next_attempt_at FROM pending_operations WHERE id = ?",[id]);
  expect(row?.retry_count).toBe(0);expect(row!.next_attempt_at).toBeGreaterThanOrEqual(before+120000);
  await runSync();expect(createEmergencyAlert).toHaveBeenCalledTimes(1);
});

test("SOS retries with backoff beyond five failures and cannot be bulk discarded", async () => {
  (createEmergencyAlert as jest.Mock).mockRejectedValue(new Error("unreachable"));
  const id = await enqueueUnique("emergency_alert", { client_event_id: "one" }, "one");
  await runSync();
  await runSync();
  expect(createEmergencyAlert).toHaveBeenCalledTimes(1);
  await db.runAsync("UPDATE pending_operations SET retry_count = 9, next_attempt_at = 0 WHERE id = ?", [id]);
  expect(await discardExhaustedOperations()).toBe(0);
  await runSync();
  expect((await getEmergencyOperation(id))?.retryCount).toBe(10);
});

test("recovers a stale in-flight SOS after a process interruption", async () => {
  (createEmergencyAlert as jest.Mock).mockResolvedValue({ id: 5 });
  const id = await enqueueUnique("emergency_alert", { client_event_id: "same-event" }, "same");
  await db.runAsync("UPDATE pending_operations SET status = 'syncing', updated_at = ? WHERE id = ?", [Date.now() - 70000, id]);
  await runSync();
  expect((await getEmergencyOperation(id))?.status).toBe("synced");
  expect(createEmergencyAlert).toHaveBeenCalledWith({ client_event_id: "same-event" }, "token-1");
});
