import { router } from "expo-router";
import { useEffect } from "react";
import { getActiveRouteSession, subscribeRouteSession } from "../routeSession";
import { closeStalePendingFallEvents, getFallSettings, purgeOldFallEvents, subscribeFallSettings } from "./fallEvents";
import { fallMonitor } from "./monitor";

// Starts the accelerometer only while the user has enabled the feature AND an activity is running.
// It never starts by itself: enabling requires the explicit switch in FallDetectionCard.
export function FallDetectionCoordinator() {
  useEffect(() => {
    let disposed = false;
    let refreshing = false;
    let desired = "";
    void closeStalePendingFallEvents().then(() => purgeOldFallEvents()).catch(() => undefined);
    const refresh = async () => {
      if (refreshing || disposed) return;
      refreshing = true;
      try {
        const [settings, route] = await Promise.all([getFallSettings(), getActiveRouteSession()]);
        if (disposed) return;
        const running = settings.enabled && settings.limitationsAcknowledgedAt !== null && route?.state === "running";
        const next = running && route ? `${route.user_id}:${route.trail_id}:${route.started_at}` : "";
        if (next === desired) return;
        desired = next;
        if (running && route) void fallMonitor.start({ trailId: route.trail_id, startedAt: route.started_at });
        else fallMonitor.stop();
      } catch {
        // An unreadable preference must never leave the sensor running without consent.
        if (desired) { desired = ""; fallMonitor.stop(); }
      } finally { refreshing = false; }
    };
    const tick = () => { void refresh(); };
    const offAlarm = fallMonitor.onAlarm(({ eventId, context }) => {
      router.push({ pathname: "/caida-detectada", params: {
        eventId, ...(context.trailId ? { id: String(context.trailId) } : {}),
        ...(context.startedAt ? { startedAt: String(context.startedAt) } : {}) } });
    });
    const offRoute = subscribeRouteSession(tick);
    const offSettings = subscribeFallSettings(tick);
    const timer = setInterval(tick, 2000);
    tick();
    return () => { disposed = true; clearInterval(timer); offRoute(); offSettings(); offAlarm(); fallMonitor.stop(); };
  }, []);
  return null;
}
