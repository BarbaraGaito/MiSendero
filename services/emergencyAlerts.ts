import * as Crypto from "expo-crypto";
import * as SMS from "expo-sms";
import { getCurrentDeviceLocation } from "./deviceLocation";
import { enqueueUnique, runSync } from "./syncQueue";
import { getLastRouteTrackingPoint } from "./routeTracking";
import { EmergencyContact, Trail } from "../types";
import { getAuthSession } from "./authSession";
import { formatTrailMessageContext, getTrailForMessage } from "./trailMessages";
import { getRouteSession } from "./routeSession";
import { isTestingLocationActive } from "./testingMode";

export interface EmergencyContext {
  trailId?: number | null;
  startedAt?: number | null;
  /** The SOS was raised from simulated data (e.g. a simulated wearable alert). */
  simulated?: boolean;
}

export interface SendEmergencyAlertOptions extends EmergencyContext {
  contact?: EmergencyContact | null;
  eventId?: string;
}

export type EmergencyTestReason = "testing_location" | "simulated_data";

export class SimulatedEmergencyError extends Error {
  constructor(readonly reason: EmergencyTestReason) {
    super("Modo prueba: el SOS no se envía.");
    this.name = "SimulatedEmergencyError";
  }
}

// Simulators exist only for testing: an SOS raised from simulated data, during
// testing-location mode or inside a simulated route is never sent, queued or stored.
// A storage read error counts as "not testing" so it can never block a real SOS.
export const getEmergencyTestReason = async ({ trailId, startedAt, simulated }: EmergencyContext): Promise<EmergencyTestReason | null> => {
  const [testing, session] = await Promise.all([
    isTestingLocationActive().catch(() => false),
    trailId && startedAt ? getRouteSession(trailId, startedAt).catch(() => null) : null,
  ]);
  if (testing || session?.simulated) return "testing_location";
  return simulated ? "simulated_data" : null;
};

const assertRealEmergency = async (context: EmergencyContext) => {
  const reason = await getEmergencyTestReason(context);
  if (reason) throw new SimulatedEmergencyError(reason);
};

export const sendEmergencySms = async (phone: string, message: string, context: EmergencyContext) => {
  await assertRealEmergency(context);
  return SMS.sendSMSAsync([phone], message);
};

export const buildEmergencyMessage = ({ latitude, longitude, trail, timestamp }: {
  contact?: EmergencyContact | null;
  latitude: number | null;
  longitude: number | null;
  trailId?: number | null;
  trail?: Trail | null;
  timestamp: number;
}) => {
  const date = new Intl.DateTimeFormat("es-AR", { dateStyle: "short", timeStyle: "short" }).format(timestamp);
  const location = latitude !== null && longitude !== null
    ? `Última ubicación: ${latitude.toFixed(5)}, ${longitude.toFixed(5)}. Registrada: ${date}. https://maps.google.com/?q=${latitude},${longitude}`
    : "Ubicación no disponible. Necesito asistencia aunque no haya GPS.";
  return `SOS MiSendero. Necesito asistencia. ${formatTrailMessageContext(trail)} ${location}`;
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
  await assertRealEmergency(options);
  const owner = (await getAuthSession())?.user.id ?? null;
  const eventId = options.eventId ?? Crypto.randomUUID();
  const [location, trail] = await Promise.all([
    getEmergencyLocation(options.trailId, options.startedAt),
    getTrailForMessage(options.trailId),
  ]);
  const message = buildEmergencyMessage({ ...location, trail });
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
