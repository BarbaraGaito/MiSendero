import { initDB } from "../../database/database";
import { saveAuthSession } from "../authSession";

jest.mock("expo-network", () => ({
  getNetworkStateAsync: jest.fn(),
}));

jest.mock("../api", () => ({
  createTrailReport: jest.fn(),
  createActivity: jest.fn(),
  createEmergencyAlert: jest.fn(),
  getTrailReports: jest.fn().mockResolvedValue([]),
}));

import * as Network from "expo-network";
import * as api from "../api";
import {
  discardExhaustedOperations,
  enqueue,
  getPendingOperations,
  getSyncSummary,
  MAX_RETRY_ATTEMPTS,
  runSync,
} from "../syncQueue";

const online = () =>
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({
    isConnected: true,
    isInternetReachable: true,
  });

const offline = () =>
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({
    isConnected: false,
    isInternetReachable: false,
  });

beforeAll(async () => {
  await initDB();
  await saveAuthSession({
    token: "test-token",
    user: { id: 1, name: "Test", email: "test@misendero.app" },
  });
});

beforeEach(() => {
  jest.clearAllMocks();
});

describe("syncQueue", () => {
  test("enqueue stores an operation as pending", async () => {
    const id = await enqueue("trail_report", { trailId: 1, issue_summary: "Barro" });
    const pending = await getPendingOperations();

    expect(pending.some((operation) => operation.id === id && operation.status === "pending")).toBe(
      true
    );
  });

  test("runSync does nothing while offline", async () => {
    offline();
    await enqueue("activity", { trail_id: 1, started_at: new Date().toISOString() });

    const result = await runSync();

    expect(result).toEqual({ processed: 0, failed: 0 });
    expect(api.createActivity).not.toHaveBeenCalled();
  });

  test("runSync marks an operation as synced on success", async () => {
    online();
    (api.createTrailReport as jest.Mock).mockResolvedValue({ id: 555 });

    const id = await enqueue("trail_report", {
      trailId: 2,
      issue_summary: "Sendero cortado",
      severity: "Alta",
      trail_state: "No transitable",
    });

    const result = await runSync();

    expect(result.processed).toBeGreaterThanOrEqual(1);
    expect(api.createTrailReport).toHaveBeenCalledWith(
      2,
      expect.objectContaining({ issue_summary: "Sendero cortado" }),
      "test-token"
    );

    const pendingAfter = await getPendingOperations();
    expect(pendingAfter.some((operation) => operation.id === id)).toBe(false);
  });

  test("runSync marks an operation as failed and keeps it queued for retry", async () => {
    online();
    (api.createEmergencyAlert as jest.Mock).mockRejectedValue(new Error("500"));

    const id = await enqueue("emergency_alert", { latitude: -41.1, longitude: -71.1 });
    const result = await runSync();

    expect(result.failed).toBeGreaterThanOrEqual(1);

    const pendingAfter = await getPendingOperations();
    const failedOperation = pendingAfter.find((operation) => operation.id === id);

    expect(failedOperation?.status).toBe("failed");
    expect(failedOperation?.retryCount).toBe(1);
  });

  test("getSyncSummary reflects counts across statuses", async () => {
    const summary = await getSyncSummary();

    expect(summary.synced).toBeGreaterThanOrEqual(1);
    expect(summary.failed).toBeGreaterThanOrEqual(1);
  });

  test("stops retrying an operation after MAX_RETRY_ATTEMPTS and lets it be discarded", async () => {
    online();
    (api.createActivity as jest.Mock).mockRejectedValue(new Error("boom"));

    const id = await enqueue("activity", {
      trail_id: 9,
      started_at: new Date().toISOString(),
    });

    for (let attempt = 0; attempt < MAX_RETRY_ATTEMPTS; attempt += 1) {
      await runSync();
    }

    const beforeExtraAttempt = await getPendingOperations();
    expect(beforeExtraAttempt.find((operation) => operation.id === id)?.retryCount).toBe(
      MAX_RETRY_ATTEMPTS
    );

    await runSync();

    const afterExtraAttempt = await getPendingOperations();
    const trackedOperation = afterExtraAttempt.find((operation) => operation.id === id);
    // Once at the cap, further runSync() calls must not touch this operation again.
    expect(trackedOperation?.retryCount).toBe(MAX_RETRY_ATTEMPTS);
    expect(trackedOperation?.status).toBe("failed");

    const summary = await getSyncSummary();
    expect(summary.exhausted).toBeGreaterThanOrEqual(1);

    const discarded = await discardExhaustedOperations();
    expect(discarded).toBeGreaterThanOrEqual(1);

    const afterDiscard = await getPendingOperations();
    expect(afterDiscard.some((operation) => operation.id === id)).toBe(false);
  });
});
