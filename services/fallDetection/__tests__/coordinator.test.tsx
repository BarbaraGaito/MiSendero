import "../../../testing/mobileSetup";
jest.mock("../fallEvents", () => ({
  getFallSettings: jest.fn(), subscribeFallSettings: jest.fn(() => jest.fn()),
  closeStalePendingFallEvents: jest.fn().mockResolvedValue(undefined), purgeOldFallEvents: jest.fn().mockResolvedValue(undefined),
}));
jest.mock("../../routeSession", () => ({ getActiveRouteSession: jest.fn(), subscribeRouteSession: jest.fn(() => jest.fn()) }));
jest.mock("../monitor", () => ({ fallMonitor: { start: jest.fn().mockResolvedValue({}), stop: jest.fn(), onAlarm: jest.fn() } }));
import { router } from "expo-router";
import { getActiveRouteSession } from "../../routeSession";
import { getFallSettings } from "../fallEvents";
import { fallMonitor } from "../monitor";
import { FallDetectionCoordinator } from "../FallDetectionCoordinator";
import { act, flush, mount } from "../../../testing/mobileHarness";

const running = { user_id: 1, trail_id: 7, started_at: 1700000000000, state: "running" };
let alarm: (value: unknown) => void;
const tick = async () => act(async () => { jest.advanceTimersByTime(2000); await flush(); });
beforeEach(() => {
  jest.useFakeTimers();
  (getFallSettings as jest.Mock).mockResolvedValue({ enabled: true, limitationsAcknowledgedAt: 5 });
  (getActiveRouteSession as jest.Mock).mockResolvedValue(running);
  (fallMonitor.onAlarm as jest.Mock).mockImplementation((callback) => { alarm = callback; return jest.fn(); });
});
afterEach(() => jest.useRealTimers());

test("the sensor starts only with the switch on, the limits acknowledged and a running activity", async () => {
  await mount(FallDetectionCoordinator);
  expect(fallMonitor.start).toHaveBeenCalledWith({ trailId: 7, startedAt: 1700000000000 });
  expect(fallMonitor.start).toHaveBeenCalledTimes(1);
  await tick();
  expect(fallMonitor.start).toHaveBeenCalledTimes(1);                      // unchanged: no restart
});

test("it stays off without consent, without an activity, when paused, or when the preference is unreadable", async () => {
  (getFallSettings as jest.Mock).mockResolvedValue({ enabled: false, limitationsAcknowledgedAt: null });
  await mount(FallDetectionCoordinator);
  expect(fallMonitor.start).not.toHaveBeenCalled();
  (getFallSettings as jest.Mock).mockResolvedValue({ enabled: true, limitationsAcknowledgedAt: null });
  await tick();
  expect(fallMonitor.start).not.toHaveBeenCalled();                        // switch on but limits never acknowledged
  (getFallSettings as jest.Mock).mockResolvedValue({ enabled: true, limitationsAcknowledgedAt: 5 });
  await tick();
  expect(fallMonitor.start).toHaveBeenCalledTimes(1);
  (getActiveRouteSession as jest.Mock).mockResolvedValue({ ...running, state: "paused" });
  await tick();
  expect(fallMonitor.stop).toHaveBeenCalled();
  (getActiveRouteSession as jest.Mock).mockResolvedValue(running);
  await tick();
  expect(fallMonitor.start).toHaveBeenCalledTimes(2);
  (getFallSettings as jest.Mock).mockRejectedValue(new Error("storage"));
  (fallMonitor.stop as jest.Mock).mockClear();
  await tick();
  expect(fallMonitor.stop).toHaveBeenCalledTimes(1);
});

test("an alarm opens the assistance screen with the activity, and unmounting releases everything", async () => {
  const tree = await mount(FallDetectionCoordinator);
  await act(async () => { alarm({ eventId: "e1", context: { trailId: 7, startedAt: 1700000000000 } }); await flush(); });
  expect(router.push).toHaveBeenCalledWith({ pathname: "/caida-detectada", params: { eventId: "e1", id: "7", startedAt: "1700000000000" } });
  await act(async () => tree.unmount());
  expect(fallMonitor.stop).toHaveBeenCalled();
});
