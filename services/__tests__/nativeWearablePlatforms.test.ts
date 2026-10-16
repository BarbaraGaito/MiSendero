jest.mock("react-native-health-connect", () => ({ getSdkStatus: jest.fn(), initialize: jest.fn(), requestPermission: jest.fn(), readRecords: jest.fn(), SdkAvailabilityStatus: { SDK_AVAILABLE: 3 } }));
jest.mock("@kingstinct/react-native-healthkit", () => ({ isHealthDataAvailableAsync: jest.fn(), requestAuthorization: jest.fn(), configureBackgroundTypes: jest.fn(), getMostRecentQuantitySample: jest.fn(), UpdateFrequency: { hourly: 1 } }));
import { Platform } from "react-native";
import * as connect from "react-native-health-connect";
import * as kit from "@kingstinct/react-native-healthkit";
import { getNativeWearableBridge } from "../nativeWearableBridge";
const os = Platform.OS, now = Date.UTC(2026, 9, 16, 10), iso = (delta = 0) => new Date(now + delta).toISOString();
beforeEach(() => {
  jest.resetAllMocks(); jest.useFakeTimers({ now }); Platform.OS = "android";
  (connect.getSdkStatus as jest.Mock).mockResolvedValue(3); (connect.initialize as jest.Mock).mockResolvedValue(true);
  (connect.requestPermission as jest.Mock).mockResolvedValue([{ accessType: "read", recordType: "HeartRate" }]);
  (connect.readRecords as jest.Mock).mockResolvedValue({ records: [] });
});
afterEach(() => { Platform.OS = os; jest.useRealTimers(); });
test("Android availability and authorization fail closed when the SDK, initialization or pulse permission is missing", async () => {
  const bridge = getNativeWearableBridge(); expect(await bridge.isAvailable()).toBe(true); expect(await bridge.requestPermissions()).toBe(true);
  (connect.getSdkStatus as jest.Mock).mockResolvedValue(1); expect(await bridge.isAvailable()).toBe(false);
  (connect.initialize as jest.Mock).mockResolvedValue(false); expect(await bridge.requestPermissions()).toBe(false); expect(await bridge.readLatestSample()).toBeNull();
  (connect.initialize as jest.Mock).mockRejectedValue(new Error("native")); expect(await bridge.isAvailable()).toBe(false); expect(await bridge.requestPermissions()).toBe(false); expect(await bridge.readLatestSample()).toBeNull();
  (connect.initialize as jest.Mock).mockResolvedValue(true); (connect.requestPermission as jest.Mock).mockResolvedValue([{ accessType: "write", recordType: "HeartRate" }]); expect(await bridge.requestPermissions()).toBe(false);
});
test("Android selects the newest pulse, sums steps and energy and discards temporally unrelated readings", async () => {
  (connect.readRecords as jest.Mock).mockImplementation(async (type: string) => ({ records: {
    HeartRate: [{ samples: [{ beatsPerMinute: 70, time: iso(-90000) }, { beatsPerMinute: 105, time: iso() }] }],
    Steps: [{ count: 10.6, endTime: iso() }, { count: 20, endTime: iso() }],
    ActiveCaloriesBurned: [{ energy: { inKilocalories: 1.25 }, endTime: iso() }, { energy: { inKilocalories: 2.2 }, endTime: iso() }],
    Speed: [{ samples: [{ speed: { inKilometersPerHour: 2 }, time: iso(-90000) }, { speed: { inKilometersPerHour: 4.44 }, time: iso() }] }],
    OxygenSaturation: [{ percentage: 90, time: iso(-120000) }, { percentage: 98.25, time: iso(-90000) }],
  }[type] ?? [] }));
  const bridge = getNativeWearableBridge(); expect(await bridge.readLatestSample({ startAt: now - 300000, endAt: now, requireHeartRate: true })).toEqual({ provider: "android_health_connect", heartRateBpm: 105, steps: 31, activeEnergyKcal: 3.5, speedKmh: 4.4, oxygenSaturation: null, recordedAt: now });
  expect(connect.readRecords).toHaveBeenCalledWith("HeartRate", expect.objectContaining({ timeRangeFilter: { operator: "between", startTime: iso(-300000), endTime: iso() } }));
});
test("missing or failed Android reads do not fabricate a pulse; oxygen-only samples retain their actual timestamp", async () => {
  const bridge = getNativeWearableBridge(); expect(await bridge.readLatestSample()).toBeNull(); (connect.readRecords as jest.Mock).mockRejectedValue(new Error("read")); expect(await bridge.readLatestSample()).toBeNull();
  (connect.readRecords as jest.Mock).mockImplementation(async (type: string) => ({ records: type === "OxygenSaturation" ? [{ percentage: 98.2, time: iso() }] : [] }));
  expect(await bridge.readLatestSample({ requireHeartRate: true })).toBeNull(); expect(await bridge.readLatestSample()).toMatchObject({ heartRateBpm: null, oxygenSaturation: 98.2, recordedAt: now });
});
test("iOS authorization enables only declared background types and availability errors stay unavailable", async () => {
  Platform.OS = "ios"; const bridge = getNativeWearableBridge(); (kit.isHealthDataAvailableAsync as jest.Mock).mockResolvedValue(true); (kit.requestAuthorization as jest.Mock).mockResolvedValue(true); (kit.configureBackgroundTypes as jest.Mock).mockResolvedValue(undefined);
  expect(await bridge.isAvailable()).toBe(true); expect(await bridge.requestPermissions()).toBe(true); expect(kit.configureBackgroundTypes).toHaveBeenCalledWith(expect.arrayContaining(["HKQuantityTypeIdentifierHeartRate"]), 1);
  (kit.isHealthDataAvailableAsync as jest.Mock).mockRejectedValue(new Error("native")); (kit.requestAuthorization as jest.Mock).mockRejectedValue(new Error("denied")); expect(await bridge.isAvailable()).toBe(false); expect(await bridge.requestPermissions()).toBe(false);
  (kit.getMostRecentQuantitySample as jest.Mock).mockRejectedValue(new Error("no data")); expect(await bridge.readLatestSample()).toBeNull();
});
test("iOS converts measured walking speed and rounds steps while preserving the pulse timestamp", async () => {
  Platform.OS = "ios"; (kit.getMostRecentQuantitySample as jest.Mock).mockImplementation(async (type: string) => ({ quantity: type.includes("WalkingSpeed") ? 1.25 : type.includes("StepCount") ? 12.6 : 95, endDate: new Date(now) }));
  expect(await getNativeWearableBridge().readLatestSample({ requireHeartRate: true })).toMatchObject({ steps: 13, speedKmh: 4.5, recordedAt: now, heartRateBpm: 95 });
});
test("unsupported platforms cannot authorize or manufacture native health data", async () => {
  Platform.OS = "web"; const bridge = getNativeWearableBridge(); expect(await bridge.isAvailable()).toBe(false); expect(await bridge.requestPermissions()).toBe(false); expect(await bridge.readLatestSample()).toBeNull();
});
