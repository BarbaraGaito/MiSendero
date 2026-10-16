import "../../../testing/mobileSetup";
jest.mock("../../../services/deviceLocation", () => ({ getCurrentDeviceLocation: jest.fn(), watchDeviceLocation: jest.fn() }));
jest.mock("../../../services/authSession", () => ({ getAuthSession: jest.fn() }));
jest.mock("../../../services/testingMode", () => ({ getTestingLocationMode: jest.fn() }));
import { getCurrentDeviceLocation, watchDeviceLocation } from "../../../services/deviceLocation";
import { getAuthSession } from "../../../services/authSession";
import { getTestingLocationMode } from "../../../services/testingMode";
import { useDeviceLocation } from "../useDeviceLocation";
import { mount, act, flush } from "../../../testing/mobileHarness";
let state: ReturnType<typeof useDeviceLocation>;
function Probe({ watch = true, simulated }: { watch?: boolean; simulated?: [number, number] }) { state = useDeviceLocation(watch, simulated); return null; }
beforeEach(() => {
  (getAuthSession as jest.Mock).mockResolvedValue({ user: { id: 1, role: "user" } });
  (getTestingLocationMode as jest.Mock).mockResolvedValue({ enabled: false });
  (getCurrentDeviceLocation as jest.Mock).mockResolvedValue({ coordinate: [1, 2], accuracy: 5, timestamp: 1700000000000 });
  (watchDeviceLocation as jest.Mock).mockResolvedValue({ remove: jest.fn() });
});
test("permission denial is visible and does not create a watcher", async () => {
  (getCurrentDeviceLocation as jest.Mock).mockResolvedValue(null); await mount(Probe);
  expect(state!).toMatchObject({ permissionDenied: true, isLoading: false, location: null }); expect(watchDeviceLocation).not.toHaveBeenCalled();
});
test("GPS updates replace current measured location and cleanup removes the subscription", async () => {
  let update: any; const remove = jest.fn(); (watchDeviceLocation as jest.Mock).mockImplementation(async (callback) => { update = callback; return { remove }; });
  const tree = await mount(Probe); expect(state!.location?.coordinate).toEqual([1, 2]);
  await act(async () => update({ coordinate: [3, 4], accuracy: 6, timestamp: 1700000003000 })); expect(state!.location?.coordinate).toEqual([3, 4]);
  await act(async () => tree.unmount()); expect(remove).toHaveBeenCalledTimes(1);
});
test("only an administrator in testing mode can use simulated coordinates", async () => {
  (getTestingLocationMode as jest.Mock).mockResolvedValue({ enabled: true });
  await mount(Probe, { simulated: [7, 8], watch: false }); expect(state!.isTestingLocation).toBe(false);
  (getAuthSession as jest.Mock).mockResolvedValue({ user: { id: 1, role: "admin" } });
  await mount(Probe, { simulated: [7, 8] }); expect(state!).toMatchObject({ isTestingLocation: true, location: { coordinate: [7, 8], accuracy: 0 }, isLoading: false });
});
test("provider errors surface without synthesizing a successful fix", async () => {
  (getCurrentDeviceLocation as jest.Mock).mockRejectedValue(new Error("GPS")); await mount(Probe);
  expect(state!.error).toContain("No pudimos obtener"); expect(state!.location).toBeNull();
});
