jest.mock("expo-location", () => ({ Accuracy: { High: 4 }, getForegroundPermissionsAsync: jest.fn(), requestForegroundPermissionsAsync: jest.fn(), getCurrentPositionAsync: jest.fn(), watchPositionAsync: jest.fn() }));
import * as Location from "expo-location";
import { getCurrentDeviceLocation, requestLocationPermission, watchDeviceLocation, toDeviceLocation } from "../deviceLocation";
const fix = { coords: { latitude: -41.1, longitude: -71.2, accuracy: 8 }, timestamp: 1700000000000 };
beforeEach(() => { jest.resetAllMocks(); (Location.getForegroundPermissionsAsync as jest.Mock).mockResolvedValue({ granted: true }); });
test("uses an already granted permission without prompting again", async () => {
  expect(await requestLocationPermission()).toBe(true);
  expect(Location.requestForegroundPermissionsAsync).not.toHaveBeenCalled();
});
test("denial prevents both a GPS read and a location subscription", async () => {
  (Location.getForegroundPermissionsAsync as jest.Mock).mockResolvedValue({ granted: false });
  (Location.requestForegroundPermissionsAsync as jest.Mock).mockResolvedValue({ granted: false });
  expect(await getCurrentDeviceLocation()).toBeNull();
  expect(await watchDeviceLocation(jest.fn())).toBeNull();
  expect(Location.getCurrentPositionAsync).not.toHaveBeenCalled();
  expect(Location.watchPositionAsync).not.toHaveBeenCalled();
});
test("returns measured coordinates, accuracy and source timestamp", async () => {
  (Location.getCurrentPositionAsync as jest.Mock).mockResolvedValue(fix);
  expect(await getCurrentDeviceLocation()).toEqual({ coordinate: [-41.1, -71.2], accuracy: 8, timestamp: fix.timestamp });
  expect(toDeviceLocation({ ...fix, coords: { ...fix.coords, accuracy: null } } as never).accuracy).toBeNull();
  expect(Location.getCurrentPositionAsync).toHaveBeenCalledWith({ accuracy: 4 });
});
test("watch forwards each measured fix and returns its removable native subscription", async () => {
  const remove = jest.fn(), listener = jest.fn();
  (Location.watchPositionAsync as jest.Mock).mockImplementation(async (_options, callback) => { callback(fix); return { remove }; });
  const subscription = await watchDeviceLocation(listener);
  expect(listener).toHaveBeenCalledWith({ coordinate: [-41.1, -71.2], accuracy: 8, timestamp: fix.timestamp });
  subscription?.remove(); expect(remove).toHaveBeenCalledTimes(1);
});
test("provider failure is not replaced with invented coordinates", async () => {
  (Location.getCurrentPositionAsync as jest.Mock).mockRejectedValue(new Error("GPS unavailable"));
  await expect(getCurrentDeviceLocation()).rejects.toThrow("GPS unavailable");
});
