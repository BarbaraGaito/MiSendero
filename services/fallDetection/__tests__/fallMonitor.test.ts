import { AppState, Vibration } from "react-native";
import parity from "../../../testing/fixtures/fall-detection/parity.json";
import { initDB } from "../../../database/database";
import { saveAuthSession } from "../../authSession";
import { answerFallEvent, getFallEvent } from "../fallEvents";
import { FallMonitor, requestSensorPermission } from "../monitor";

jest.mock("expo-sensors", () => {
  const listeners: Array<(sample: unknown) => void> = [];
  return { Accelerometer: {
    __listeners: listeners,
    isAvailableAsync: jest.fn(), getPermissionsAsync: jest.fn(), requestPermissionsAsync: jest.fn(), setUpdateInterval: jest.fn(),
    addListener: jest.fn((callback: (sample: unknown) => void) => {
      listeners.push(callback);
      return { remove: jest.fn(() => { listeners.splice(listeners.indexOf(callback), 1); }) };
    }),
  } };
});
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { Accelerometer } = require("expo-sensors") as { Accelerometer: Record<string, jest.Mock> & { __listeners: Array<(s: unknown) => void> } };

const fall = parity.segments.find((s) => s.activity === "FallingBack")!;
let clock = 1_000_000;
const now = () => clock;
const emit = (xyz: number[], startSeconds: number) => {
  const listener = Accelerometer.__listeners[0];
  for (let i = 0; i < xyz.length / 3; i++) {
    clock += 20;
    listener({ x: xyz[3 * i], y: xyz[3 * i + 1], z: xyz[3 * i + 2], timestamp: startSeconds + i * 0.02 });
  }
};
const flushPromises = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };

beforeAll(async () => { await initDB(); await saveAuthSession({ token: "t", user: { id: 4711, name: "Test", email: "t@example.test" } }); });
beforeEach(() => {
  jest.useFakeTimers();
  clock = 1_000_000;
  Accelerometer.__listeners.length = 0;
  Accelerometer.isAvailableAsync.mockResolvedValue(true);
  Accelerometer.getPermissionsAsync.mockResolvedValue({ status: "granted", canAskAgain: true });
  jest.spyOn(Vibration, "vibrate").mockImplementation(() => undefined);
});
afterEach(() => { jest.useRealTimers(); });

test("an unavailable accelerometer is reported, no listener is registered", async () => {
  Accelerometer.isAvailableAsync.mockResolvedValue(false);
  const monitor = new FallMonitor();
  const snapshot = await monitor.start({ trailId: 1, startedAt: 1 }, { now });
  expect(snapshot).toMatchObject({ state: "unavailable", sensorAvailable: false });
  expect(snapshot.reason).toMatch(/acelerómetro/);
  expect(Accelerometer.addListener).not.toHaveBeenCalled();
  expect(jest.getTimerCount()).toBe(0);
});

test("a denied motion permission leaves the monitor unavailable and only asks when the user asked", async () => {
  Accelerometer.getPermissionsAsync.mockResolvedValue({ status: "denied", canAskAgain: true });
  Accelerometer.requestPermissionsAsync.mockResolvedValue({ status: "denied", canAskAgain: false });
  const monitor = new FallMonitor();
  expect((await monitor.start({ trailId: 1, startedAt: 1 }, { now })).state).toBe("unavailable");
  expect(Accelerometer.requestPermissionsAsync).not.toHaveBeenCalled();
  expect((await monitor.start({ trailId: 1, startedAt: 2 }, { now, requestPermission: true })).reason).toMatch(/permiso/);
  expect(Accelerometer.requestPermissionsAsync).toHaveBeenCalledTimes(1);
  await expect(requestSensorPermission()).resolves.toEqual({ granted: false, available: true });
});

test("samples flow, the real state and rate are reported, and a fall asks the user once", async () => {
  const monitor = new FallMonitor();
  const alarms: Array<{ eventId: string }> = [];
  monitor.onAlarm((alarm) => alarms.push(alarm));
  const first = await monitor.start({ trailId: 9, startedAt: 123 }, { now });
  expect(first.state).toBe("starting");
  expect(first.model?.status).toBe("experimental");
  expect(Accelerometer.setUpdateInterval).toHaveBeenCalledWith(20);
  await monitor.start({ trailId: 9, startedAt: 123 }, { now });          // same activity: no second listener
  expect(Accelerometer.__listeners).toHaveLength(1);

  emit(fall.xyz, 10);
  for (let i = 0; i < 3; i++) { clock += 1000; jest.advanceTimersByTime(1000); }
  await flushPromises();
  expect(alarms).toHaveLength(1);
  expect(Vibration.vibrate).toHaveBeenCalledTimes(1);
  expect(monitor.getSnapshot().pendingEventId).toBe(alarms[0].eventId);
  const stored = await getFallEvent(alarms[0].eventId);
  expect(stored).toMatchObject({ userResponse: "pending", action: "none", trailId: 9, startedAt: 123, classification: "possible_fall" });
  expect(stored?.modelVersion).toMatch(/exp/);
  expect(stored?.score).toBeGreaterThan(0.2);

  // While the assistance question is open nothing else is raised, even for another impact.
  emit(fall.xyz, 100);
  expect(alarms).toHaveLength(1);
  expect(await answerFallEvent(alarms[0].eventId, "ok", "dismissed")).toBe(true);
  expect(await answerFallEvent(alarms[0].eventId, "help", "sos_opened")).toBe(false);   // first answer wins
  monitor.clearPending(alarms[0].eventId);
  emit(fall.xyz, 200);                                                    // > 30 s of stream time later
  await flushPromises();
  expect(alarms).toHaveLength(2);
  monitor.stop();
});

test("no samples means 'interrupted' (with the background reason) and recovery is reported", async () => {
  const monitor = new FallMonitor();
  const appListeners: Array<(state: string) => void> = [];
  jest.spyOn(AppState, "addEventListener").mockImplementation(((_: string, handler: (state: string) => void) => {
    appListeners.push(handler); return { remove: jest.fn() };
  }) as never);
  await monitor.start({ trailId: 1, startedAt: 5 }, { now });
  const quiet = new Array(300).fill(0).flatMap(() => [0, 0, 1]);          // 6 s of a phone lying still
  emit(quiet, 0);
  clock += 1000; jest.advanceTimersByTime(1000);
  expect(monitor.getSnapshot().state).toBe("monitoring");
  expect(monitor.getSnapshot().measuredRateHz).toBeGreaterThan(45);
  expect(monitor.getSnapshot().monitoredMs).toBeGreaterThan(0);

  appListeners[0]("background");
  for (let i = 0; i < 4; i++) { clock += 1000; jest.advanceTimersByTime(1000); }
  expect(monitor.getSnapshot()).toMatchObject({ state: "interrupted", appState: "background" });
  expect(monitor.getSnapshot().reason).toMatch(/segundo plano/);
  expect(monitor.getSnapshot().interruptedMs).toBeGreaterThanOrEqual(2000);

  appListeners[0]("active");
  emit(quiet, 50);
  clock += 1000; jest.advanceTimersByTime(1000);
  expect(monitor.getSnapshot().state).toBe("monitoring");
  expect(monitor.getSnapshot().counters?.interruptions).toBe(1);          // the gap discarded the buffer
  monitor.stop();
});

test("stop releases the subscription and the watchdog and returns to off", async () => {
  const monitor = new FallMonitor();
  await monitor.start({ trailId: 1, startedAt: 6 }, { now });
  const subscription = Accelerometer.addListener.mock.results[0].value as { remove: jest.Mock };
  expect(jest.getTimerCount()).toBe(1);
  monitor.stop();
  expect(subscription.remove).toHaveBeenCalled();
  expect(jest.getTimerCount()).toBe(0);
  expect(Accelerometer.__listeners).toHaveLength(0);
  expect(monitor.getSnapshot()).toMatchObject({ state: "off", pendingEventId: null });
});

test("a slow phone is reported as degraded and its doubtful windows are discarded", async () => {
  const monitor = new FallMonitor();
  await monitor.start({ trailId: 1, startedAt: 7 }, { now });
  const listener = Accelerometer.__listeners[0];
  for (let i = 0; i < 150; i++) { clock += 50; listener({ x: 0, y: 0, z: 1, timestamp: i * 0.05 }); }   // 20 Hz
  clock += 0; jest.advanceTimersByTime(1000);
  expect(monitor.getSnapshot().state).toBe("degraded_rate");
  expect(monitor.getSnapshot().measuredRateHz).toBeLessThan(40);
  monitor.stop();
});
