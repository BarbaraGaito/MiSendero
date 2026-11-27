jest.mock("@kingstinct/react-native-healthkit", () => ({ getMostRecentQuantitySample: jest.fn(), queryQuantitySamples: jest.fn() }));
jest.mock("react-native-health-connect", () => ({ initialize: jest.fn(), readRecords: jest.fn() }));
import { Platform } from "react-native";
import { getNativeWearableBridge, readNativeFieldSamples } from "../nativeWearableBridge";
import { getMostRecentQuantitySample, queryQuantitySamples } from "@kingstinct/react-native-healthkit";
import { initialize, readRecords } from "react-native-health-connect";
const os = Platform.OS;
beforeEach(() => { Platform.OS = "ios"; });
afterEach(() => { Platform.OS = os; jest.clearAllMocks(); });

test("HealthKit honors the start of the outing instead of using an earlier pulse", async () => {
  const now = Date.now();
  (getMostRecentQuantitySample as jest.Mock).mockImplementation(async (type: string) => ({
    quantity: type.includes("HeartRate") ? 100 : 5,
    endDate: new Date(type.includes("HeartRate") ? now - 600000 : now),
  }));
  expect(await getNativeWearableBridge().readLatestSample({ startAt: now - 60000, requireHeartRate: true })).toBeNull();
});
test("a new oxygen/step reading cannot make an old pulse look current", async () => {
  const now = Date.now();
  (getMostRecentQuantitySample as jest.Mock).mockImplementation(async (type: string) => ({
    quantity: type.includes("HeartRate") ? 100 : 98,
    endDate: new Date(type.includes("HeartRate") ? now - 240000 : now),
  }));
  const result = await getNativeWearableBridge().readLatestSample({ startAt: now - 600000 });
  expect(result?.recordedAt).toBe(now - 240000);
  expect(result?.oxygenSaturation).toBeNull();
  expect(result?.speedKmh).toBeNull();
});

test("field windows preserve HealthKit units and per-reading timestamps, rejecting truncated reads", async () => {
  const now = Date.now();
  (queryQuantitySamples as jest.Mock).mockImplementation(async (type: string) => [{ quantity: type.includes("HeartRate") ? 120 : 97, endDate: new Date(now) }]);
  expect(await readNativeFieldSamples(now-60000,now)).toMatchObject({ provider: "apple_healthkit", heartRate: [{ value: 120, recordedAt: now }], oxygen: [{ value: 97, recordedAt: now }] });
  expect(queryQuantitySamples).toHaveBeenCalledWith("HKQuantityTypeIdentifierOxygenSaturation", expect.objectContaining({ unit: "%", limit: 10000 }));
  (queryQuantitySamples as jest.Mock).mockResolvedValue(Array(10000).fill({ quantity: 120, endDate: new Date(now) }));
  expect(await readNativeFieldSamples(now-60000,now)).toBeNull();
  (queryQuantitySamples as jest.Mock).mockRejectedValue(new Error("denied"));
  expect(await readNativeFieldSamples(now-60000,now)).toBeNull();
  expect(await readNativeFieldSamples(now-300001,now)).toBeNull();
  expect(await readNativeFieldSamples(now,now)).toBeNull();
});

test("Health Connect retains samples and refuses incomplete pages, unavailable providers or denied reads", async () => {
  Platform.OS = "android";
  const now = Date.now(), time = new Date(now).toISOString();
  (initialize as jest.Mock).mockResolvedValue(true);
  (readRecords as jest.Mock).mockImplementation(async (type: string) => ({ records: type === "HeartRate" ? [{ samples: [{ beatsPerMinute: 118, time }] }] : [{ percentage: 96, time }] }));
  expect(await readNativeFieldSamples(now-60000,now)).toMatchObject({ provider: "android_health_connect", heartRate: [{ value: 118, recordedAt: now }], oxygen: [{ value: 96, recordedAt: now }] });
  (readRecords as jest.Mock).mockResolvedValue({ records: [], pageToken: "more" });
  expect(await readNativeFieldSamples(now-60000,now)).toBeNull();
  (readRecords as jest.Mock).mockRejectedValue(new Error("denied"));
  expect(await readNativeFieldSamples(now-60000,now)).toBeNull();
  (initialize as jest.Mock).mockResolvedValue(false);
  expect(await readNativeFieldSamples(now-60000,now)).toBeNull();
  Platform.OS = "web";
  expect(await readNativeFieldSamples(now-60000,now)).toBeNull();
});
