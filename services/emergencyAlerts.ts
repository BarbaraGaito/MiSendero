import * as Crypto from "expo-crypto";
import { getCurrentDeviceLocation } from "./deviceLocation";
import { enqueueUnique, runSync } from "./syncQueue";
import { getLastRouteTrackingPoint } from "./routeTracking";
import { EmergencyContact } from "../types";
import { getAuthSession } from "./authSession";

export interface SendEmergencyAlertOptions {
  trailId?: number | null;
  contact?: EmergencyContact | null;
  startedAt?: number | null;
  eventId?: string;
}

export const buildEmergencyMessage = ({ latitude, longitude, trailId, timestamp }: {
  contact?: EmergencyContact | null;
  latitude: number | null;
  longitude: number | null;
  trailId?: number | null;
  timestamp: number;
}) => {
  const date = new Intl.DateTimeFormat("es-AR", { dateStyle: "short", timeStyle: "short" }).format(timestamp);
  const location = latitude !== null && longitude !== null
    ? `Última ubicación: ${latitude.toFixed(5)}, ${longitude.toFixed(5)}. Registrada: ${date}. https://maps.google.com/?q=${latitude},${longitude}`
    : "Ubicación no disponible. Necesito asistencia aunque no haya GPS.";
  return `SOS MiSendero. Necesito asistencia. ${trailId ? `Sendero ID ${trailId}. ` : ""}${location}`;
};

export const getEmergencyLocation = async (trailId?: number | null, startedAt?: number | null) => {
  const lastPoint = trailId && startedAt ? await getLastRouteTrackingPoint(trailId, startedAt).catch(() => null) : null;
  const tracked = lastPoint?.simulated ? null : lastPoint;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const current = await Promise.race([
    getCurrentDeviceLocation().catch(() => null),
    new Promise<null>((resolve) => { timer = setTimeout(() => resolve(null), 4000); }),
  ]).finally(() => { if (timer) clearTimeout(timer); });
  const valid = (lat: number, lng: number, time: number) => Number.isFinite(lat) && Math.abs(lat) <= 90 && Number.isFinite(lng) && Math.abs(lng) <= 180 && Number.isFinite(time) && time > 0 && time <= Date.now() + 30000;
  const validCurrent = current && valid(current.coordinate[0], current.coordinate[1], current.timestamp) ? current : null;
  const validTracked = tracked && valid(tracked.latitude, tracked.longitude, tracked.recordedAt) ? tracked : null;
  const useCurrent = validCurrent && (!validTracked || validCurrent.timestamp >= validTracked.recordedAt);
  return {
    latitude: useCurrent ? validCurrent.coordinate[0] : validTracked?.latitude ?? null,
    longitude: useCurrent ? validCurrent.coordinate[1] : validTracked?.longitude ?? null,
    timestamp: useCurrent ? validCurrent.timestamp : validTracked?.recordedAt ?? Date.now(),
  };
};

export const sendEmergencyAlert = async (options: SendEmergencyAlertOptions = {}) => {
  const owner = (await getAuthSession())?.user.id ?? null;
  const eventId = options.eventId ?? Crypto.randomUUID();
  const location = await getEmergencyLocation(options.trailId, options.startedAt);
  const message = buildEmergencyMessage({ ...location, trailId: options.trailId });
  if (((await getAuthSession())?.user.id ?? null) !== owner) throw new Error("La cuenta cambió mientras se preparaba el SOS.");
  // Persist before attempting the network. Anonymous requests are never adopted
  // by a later account. Manual SMS/call do not require authentication.
  const operationId = await enqueueUnique("emergency_alert", {
    client_event_id: eventId,
    trail_id: options.trailId ?? null,
    latitude: location.latitude,
    longitude: location.longitude,
    contact_name: options.contact?.name ?? null,
    contact_phone: options.contact?.phone ?? null,
    message_body: message,
    last_known_at: location.latitude === null ? null : new Date(location.timestamp).toISOString(),
  }, `sos:${eventId}`);
  void runSync().catch(() => undefined);
  return { eventId, operationId, message };
};
