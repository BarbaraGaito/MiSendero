import { getTrailById } from "./trailRepository";
import { useEffect } from "react";
import { AppState } from "react-native";
import { DeviceLocation, watchDeviceLocation } from "./deviceLocation";
import { getActiveRouteSession, getRouteSession, getSimulatedRouteTrackingSummary, saveSimulatedRouteTrackingPoint, subscribeRouteSession, activeRouteSeconds } from "./routeSession";
import { getRouteTrackingSummary, saveRouteTrackingPoint } from "./routeTracking";
import { getOrCreatePausedSession } from "../database/sessionsRepository";
import { getDistanceMeters, parseRouteCoordinates } from "./geoUtils";
import { getAuthSession } from "./authSession";

// One writer for GPS across all screens. It records only foreground fixes;
// a gap in coverage never becomes a straight-line distance estimate.
export function RouteTrackingCoordinator() {
  useEffect(() => {
    let disposed = false;
    let subscription: { remove(): void } | null = null;
    let key = "";
    let generation = 0;
    let refreshing = false;
    const refresh = async () => {
      if (refreshing || disposed) return;
      refreshing = true;
      try {
        const route = await getActiveRouteSession();
        const nextKey = route?.state === "running" && AppState.currentState !== "background"
          ? `${route.user_id}:${route.trail_id}:${route.started_at}:${route.simulated}` : "";
        if (disposed || nextKey === key) return;
        key = nextKey;
        const currentGeneration = ++generation;
        subscription?.remove();
        subscription = null;
        if (!route || !key) return;
        if (route.simulated) {
          // Testing mode: synthetic positions stay in memory and never become GPS points or an activity.
          const trail = await getTrailById(route.trail_id);
          const summary = getSimulatedRouteTrackingSummary(route.trail_id, route.started_at);
          const points = parseRouteCoordinates(trail.route_coordinates);
          if (!points.length || disposed || generation !== currentGeneration) return;
          let index = summary.lastPoint ? points.reduce((best, point, candidate) =>
            getDistanceMeters(point, [summary.lastPoint!.latitude, summary.lastPoint!.longitude]) < getDistanceMeters(points[best], [summary.lastPoint!.latitude, summary.lastPoint!.longitude]) ? candidate : best, 0) : 0;
          let writing = false;
          const timer = setInterval(async () => {
            if (writing || disposed || generation !== currentGeneration || index >= points.length - 1) return;
            writing = true;
            try {
              const state = await getRouteSession(route.trail_id, route.started_at);
              if (state?.state !== "running" || generation !== currentGeneration) return;
              const previous = points[index++]; const point = points[index];
              const delta = getDistanceMeters(previous, point);
              saveSimulatedRouteTrackingPoint({ trailId: route.trail_id, startedAt: route.started_at,
                latitude: point[0], longitude: point[1], accuracyMeters: 0, speedKmh: delta / 3 * 3.6,
                distanceDeltaMeters: delta, recordedAt: Date.now(), simulated: true });
            } catch { /* A failed sample is not counted. */ }
            finally { writing = false; }
          }, 3000);
          subscription = { remove: () => clearInterval(timer) };
          return;
        }
        let previous: DeviceLocation | null = null;
        let pending = Promise.resolve();
        const save = async (location: DeviceLocation) => {
          if (disposed || generation !== currentGeneration) return;
          const [current, auth] = await Promise.all([getRouteSession(route.trail_id, route.started_at), getAuthSession()]);
          if (current?.state !== "running" || auth?.user.id !== route.user_id || generation !== currentGeneration) return;
          if (location.accuracy === null || location.accuracy > 50 || Date.now() - location.timestamp > 30000 || location.timestamp > Date.now() + 5000) return;
          const elapsed = previous ? (location.timestamp - previous.timestamp) / 1000 : 0;
          if (previous && elapsed <= 0) return;
          const distance = previous && elapsed <= 30 ? getDistanceMeters(previous.coordinate, location.coordinate) : 0;
          previous = location;
          if (elapsed > 0 && distance / elapsed > 7) return;
          const delta = distance >= 2 ? distance : 0;
          await saveRouteTrackingPoint({ trailId: route.trail_id, startedAt: route.started_at,
            latitude: location.coordinate[0], longitude: location.coordinate[1], accuracyMeters: location.accuracy,
            speedKmh: elapsed > 0 ? delta / elapsed * 3.6 : null, distanceDeltaMeters: delta,
            recordedAt: location.timestamp, simulated: false });
          const summary = await getRouteTrackingSummary(route.trail_id, route.started_at);
          await getOrCreatePausedSession({ trailId: route.trail_id, startedAt: route.started_at,
            duration: activeRouteSeconds(current), distance: summary.distanceMeters });
        };
        const watcher = await watchDeviceLocation((location) => {
          pending = pending.then(() => save(location)).catch(() => undefined);
        });
        if (disposed || currentGeneration !== generation) watcher?.remove();
        else { subscription = watcher; if (!watcher) key = ""; }
      } finally { refreshing = false; }
    };
    const tick = () => { void refresh().catch(() => undefined); };
    const unsubscribe = subscribeRouteSession(tick);
    const app = AppState.addEventListener("change", tick);
    const timer = setInterval(tick, 1000);
    tick();
    return () => { disposed = true; generation++; subscription?.remove(); clearInterval(timer); app.remove(); unsubscribe(); };
  }, []);
  return null;
}
