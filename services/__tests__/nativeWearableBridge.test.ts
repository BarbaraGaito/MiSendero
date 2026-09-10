jest.mock("@kingstinct/react-native-healthkit", () => ({ getMostRecentQuantitySample: jest.fn() }));
import { Platform } from "react-native";
import { getNativeWearableBridge } from "../nativeWearableBridge";
import { getMostRecentQuantitySample } from "@kingstinct/react-native-healthkit";
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
