import * as Location from "expo-location";
import { Coordinate } from "./geoUtils";

export interface DeviceLocation {
  coordinate: Coordinate;
  accuracy: number | null;
  timestamp: number;
  altitudeM?: number | null;
  altitudeAccuracyM?: number | null;
}

export const toDeviceLocation = (
  location: Location.LocationObject
): DeviceLocation => ({
  coordinate: [location.coords.latitude, location.coords.longitude],
  accuracy: location.coords.accuracy ?? null,
  timestamp: location.timestamp,
  altitudeM: location.coords.altitude ?? null,
  altitudeAccuracyM: location.coords.altitudeAccuracy ?? null,
});

export const requestLocationPermission = async () => {
  const current = await Location.getForegroundPermissionsAsync();

  if (current.granted) return true;

  const requested = await Location.requestForegroundPermissionsAsync();
  return requested.granted;
};

export const getCurrentDeviceLocation = async () => {
  const granted = await requestLocationPermission();

  if (!granted) return null;

  const location = await Location.getCurrentPositionAsync({
    accuracy: Location.Accuracy.High,
  });

  return toDeviceLocation(location);
};

export const watchDeviceLocation = async (
  onLocation: (location: DeviceLocation) => void
) => {
  const granted = await requestLocationPermission();

  if (!granted) return null;

  return Location.watchPositionAsync(
    {
      accuracy: Location.Accuracy.High,
      distanceInterval: 8,
      timeInterval: 3000,
    },
    (location) => onLocation(toDeviceLocation(location))
  );
};
