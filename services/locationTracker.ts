import * as Location from 'expo-location';

import { LocationSnapshot } from '../types';
import { SENSOR_INTERVAL_MS, getSimulationProfile } from './simulationProfile';

interface GeoPoint {
  latitude: number;
  longitude: number;
  timestamp: number;
}

type SnapshotSource = LocationSnapshot['source'];
type UpdateCallback = (snapshot: LocationSnapshot) => void;

const EARTH_RADIUS_METERS = 6_371_000;
const BASE_SIMULATION_POINT = {
  latitude: -34.6037,
  longitude: -58.3816,
};

export function createLocationTracker() {
  let cancelled = false;
  let lastPoint: GeoPoint | null = null;
  let onUpdate: UpdateCallback | null = null;
  let simulationInterval: ReturnType<typeof setInterval> | null = null;
  let startTime = 0;
  let step = 0;
  let stoppedSeconds = 0;
  let totalDistance = 0;
  let watchSubscription: Location.LocationSubscription | null = null;

  const stop = () => {
    cancelled = true;

    if (watchSubscription) {
      watchSubscription.remove();
      watchSubscription = null;
    }

    if (simulationInterval) {
      clearInterval(simulationInterval);
      simulationInterval = null;
    }
  };

  const publishInitialSnapshot = (point: GeoPoint, source: SnapshotSource) => {
    if (cancelled) {
      return;
    }

    onUpdate?.({
      distanceMeters: 0,
      durationSec: 0,
      latitude: point.latitude,
      longitude: point.longitude,
      source,
      speedMps: 0,
      stoppedSeconds: 0,
    });
  };

  const publishSnapshot = (point: GeoPoint, speedMps: number, source: SnapshotSource) => {
    if (cancelled) {
      return;
    }

    if (lastPoint) {
      totalDistance += distanceBetween(lastPoint, point);
    }

    lastPoint = point;
    stoppedSeconds = speedMps < 0.35 ? stoppedSeconds + SENSOR_INTERVAL_MS / 1000 : 0;

    onUpdate?.({
      distanceMeters: totalDistance,
      durationSec: Math.max(0, Math.floor((point.timestamp - startTime) / 1000)),
      latitude: point.latitude,
      longitude: point.longitude,
      source,
      speedMps,
      stoppedSeconds,
    });
  };

  const startSimulation = () => {
    if (cancelled) {
      return;
    }

    const initialPoint: GeoPoint = lastPoint ?? {
      ...BASE_SIMULATION_POINT,
      timestamp: Date.now(),
    };

    lastPoint = initialPoint;
    publishInitialSnapshot(initialPoint, 'simulated');

    simulationInterval = setInterval(() => {
      const sample = getSimulationProfile(step);
      const distanceMeters = sample.speedMps * (SENSOR_INTERVAL_MS / 1000);
      const headingDegrees = 42 + ((step % 5) * 11);
      const nextPoint = projectPoint(lastPoint ?? initialPoint, distanceMeters, headingDegrees);

      step += 1;
      publishSnapshot(nextPoint, sample.speedMps, 'simulated');
    }, SENSOR_INTERVAL_MS);
  };

  const start = async (callback: UpdateCallback) => {
    cancelled = false;
    onUpdate = callback;
    startTime = Date.now();
    step = 0;
    stoppedSeconds = 0;
    totalDistance = 0;
    lastPoint = null;

    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      const servicesEnabled = await Location.hasServicesEnabledAsync();

      if (permission.status !== 'granted' || !servicesEnabled) {
        startSimulation();
        return;
      }

      const initialLocation = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });

      const initialPoint: GeoPoint = {
        latitude: initialLocation.coords.latitude,
        longitude: initialLocation.coords.longitude,
        timestamp: initialLocation.timestamp,
      };

      if (cancelled) {
        return;
      }

      lastPoint = initialPoint;
      publishInitialSnapshot(initialPoint, 'real');

      watchSubscription = await Location.watchPositionAsync(
        {
          accuracy: Location.Accuracy.Balanced,
          distanceInterval: 5,
          timeInterval: SENSOR_INTERVAL_MS,
        },
        (position) => {
          const point: GeoPoint = {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            timestamp: position.timestamp,
          };

          const derivedSpeed =
            position.coords.speed ??
            Math.max(0, distanceBetween(lastPoint ?? point, point) / (SENSOR_INTERVAL_MS / 1000));

          publishSnapshot(point, derivedSpeed, 'real');
        },
        () => {
          stop();
          startSimulation();
        }
      );
    } catch {
      startSimulation();
    }
  };

  return {
    start,
    stop,
  };
}

function distanceBetween(start: GeoPoint, end: GeoPoint) {
  const startLatitude = degreesToRadians(start.latitude);
  const endLatitude = degreesToRadians(end.latitude);
  const deltaLatitude = degreesToRadians(end.latitude - start.latitude);
  const deltaLongitude = degreesToRadians(end.longitude - start.longitude);

  const a =
    Math.sin(deltaLatitude / 2) * Math.sin(deltaLatitude / 2) +
    Math.cos(startLatitude) *
      Math.cos(endLatitude) *
      Math.sin(deltaLongitude / 2) *
      Math.sin(deltaLongitude / 2);

  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return EARTH_RADIUS_METERS * c;
}

function degreesToRadians(value: number) {
  return (value * Math.PI) / 180;
}

function projectPoint(start: GeoPoint, distanceMeters: number, headingDegrees: number): GeoPoint {
  const angularDistance = distanceMeters / EARTH_RADIUS_METERS;
  const heading = degreesToRadians(headingDegrees);
  const latitude1 = degreesToRadians(start.latitude);
  const longitude1 = degreesToRadians(start.longitude);

  const latitude2 = Math.asin(
    Math.sin(latitude1) * Math.cos(angularDistance) +
      Math.cos(latitude1) * Math.sin(angularDistance) * Math.cos(heading)
  );

  const longitude2 =
    longitude1 +
    Math.atan2(
      Math.sin(heading) * Math.sin(angularDistance) * Math.cos(latitude1),
      Math.cos(angularDistance) - Math.sin(latitude1) * Math.sin(latitude2)
    );

  return {
    latitude: (latitude2 * 180) / Math.PI,
    longitude: (longitude2 * 180) / Math.PI,
    timestamp: Date.now(),
  };
}
