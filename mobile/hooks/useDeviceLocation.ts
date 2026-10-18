import { useScreenFocused } from "./useScreenFocused";
import { AppState } from "react-native";
import { useEffect, useState } from "react";
import {
  DeviceLocation,
  getCurrentDeviceLocation,
  watchDeviceLocation,
} from "../../services/deviceLocation";
import { Coordinate } from "../../services/geoUtils";
import { getAuthSession } from "../../services/authSession";
import { getTestingLocationMode } from "../../services/testingMode";

export const useDeviceLocation = (
  watch = true,
  simulatedCoordinate?: Coordinate | null
) => {
  const isFocused = useScreenFocused();
  const [appActive, setAppActive] = useState(AppState.currentState === "active");
  useEffect(() => {
    const listener = AppState.addEventListener("change", state => setAppActive(state === "active"));
    return () => listener.remove();
  }, []);
  const [location, setLocation] = useState<DeviceLocation | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isTestingLocation, setIsTestingLocation] = useState(false);

  useEffect(() => {
    if (!isFocused || !appActive) return;
    let isMounted = true;
    let subscription: { remove: () => void } | null = null;

    const loadLocation = async () => {
      try {
        setIsLoading(true);
        setError(null);

        const [testingMode, session] = await Promise.all([
          getTestingLocationMode(),
          getAuthSession(),
        ]);
        const canUseTestingLocation = session?.user.role === "admin";

        if (testingMode.enabled && canUseTestingLocation && simulatedCoordinate) {
          setPermissionDenied(false);
          setIsTestingLocation(true);
          setLocation({
            coordinate: simulatedCoordinate,
            accuracy: 0,
            timestamp: Date.now(),
          });
          return;
        }

        setIsTestingLocation(false);
        const currentLocation = await getCurrentDeviceLocation();

        if (!isMounted) return;

        if (!currentLocation) {
          setPermissionDenied(true);
          setLocation(null);
          return;
        }

        setPermissionDenied(false);
        setLocation(currentLocation);

        if (watch) {
          subscription = await watchDeviceLocation((nextLocation) => {
            if (isMounted) setLocation(nextLocation);
          });
          if (!isMounted) subscription?.remove();
        }
      } catch {
        if (!isMounted) return;
        setError("No pudimos obtener tu ubicacion actual.");
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    loadLocation();

    return () => {
      isMounted = false;
      subscription?.remove();
    };
  }, [simulatedCoordinate?.[0], simulatedCoordinate?.[1], watch, isFocused, appActive]);

  return {
    location,
    isLoading,
    permissionDenied,
    error,
    isTestingLocation,
  };
};
