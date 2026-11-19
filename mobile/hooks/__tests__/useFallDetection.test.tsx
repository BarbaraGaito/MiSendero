import "../../../testing/mobileSetup";
jest.mock("expo-sensors", () => ({
  Accelerometer: { isAvailableAsync: jest.fn(), setUpdateInterval: jest.fn(), addListener: jest.fn() },
}));
import { Accelerometer } from "expo-sensors";
import { useFallDetection } from "../useFallDetection";
import { mount, act, flush } from "../../../testing/mobileHarness";
import { FALL_SETTLE_MS, FALL_STILL_MS } from "../../../services/fallDetection";

const onFall = jest.fn();
const remove = jest.fn();
let listener: (sample: { x: number; y: number; z: number }) => void;
function Probe({ enabled }: { enabled: boolean }) { useFallDetection(enabled, onFall); return null; }
beforeEach(() => {
  jest.useFakeTimers({ now: 0 });
  onFall.mockReset(); remove.mockReset();
  (Accelerometer.isAvailableAsync as jest.Mock).mockResolvedValue(true);
  (Accelerometer.addListener as jest.Mock).mockImplementation((callback) => { listener = callback; return { remove }; });
});
afterEach(() => { jest.useRealTimers(); });

test("the accelerometer is only read while enabled and is released on unmount", async () => {
  await mount(Probe, { enabled: false });
  expect(Accelerometer.addListener).not.toHaveBeenCalled();
  const tree = await mount(Probe, { enabled: true });
  expect(Accelerometer.setUpdateInterval).toHaveBeenCalledWith(50);
  await act(async () => { tree.unmount(); await flush(); });
  expect(remove).toHaveBeenCalledTimes(1);
});

test("an impact followed by stillness calls back once", async () => {
  await mount(Probe, { enabled: true });
  await act(async () => {
    listener({ x: 2, y: 1.5, z: 1.5 });
    jest.setSystemTime(FALL_SETTLE_MS); listener({ x: 0, y: 0, z: 1 });
    jest.setSystemTime(FALL_SETTLE_MS + FALL_STILL_MS); listener({ x: 0, y: 0, z: 1 });
    await flush();
  });
  expect(onFall).toHaveBeenCalledTimes(1);
});

test("a phone without accelerometer never subscribes", async () => {
  (Accelerometer.isAvailableAsync as jest.Mock).mockResolvedValue(false);
  await mount(Probe, { enabled: true });
  expect(Accelerometer.addListener).not.toHaveBeenCalled();
});
