import { getCurrentDeviceLocation } from "./deviceLocation";
import { createEmergencyAlert } from "./api";
import { getAuthSession } from "./authSession";
import { enqueue, isOnline } from "./syncQueue";
import { getLastRouteTrackingPoint } from "./routeTracking";
import { EmergencyContact } from "../types";

export type EmergencyAlertOutcome = "sent" | "queued" | "no_location" | "no_session";

export interface SendEmergencyAlertOptions {
  trailId?: number | null;
  contact?: EmergencyContact | null;
  startedAt?: number | null;
}

const normalizeOptions = (
  options?: number | null | SendEmergencyAlertOptions
): SendEmergencyAlertOptions => {
  if (typeof options === "number" || options === null) {
    return { trailId: options ?? null };
  }

  return options ?? {};
};

export const buildEmergencyMessage = ({
  contact,
  latitude,
  longitude,
  trailId,
  timestamp,
}: {
  contact?: EmergencyContact | null;
  latitude: number;
  longitude: number;
  trailId?: number | null;
  timestamp: number;
}) => {
  const date = new Intl.DateTimeFormat("es-AR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(timestamp));
  const trailText = trailId ? `Sendero ID ${trailId}` : "Sendero no informado";
  const contactText = contact
    ? `Contacto configurado: ${contact.name} (${contact.phone}).`
    : "Sin contacto configurado en el dispositivo.";

  return `SOS MiSendero. Necesito asistencia. ${trailText}. Ultima ubicacion: ${latitude.toFixed(
    5
  )}, ${longitude.toFixed(5)}. Hora: ${date}. ${contactText}`;
};

export const sendEmergencyAlert = async (
  options?: number | null | SendEmergencyAlertOptions
): Promise<EmergencyAlertOutcome> => {
  const { contact, startedAt, trailId } = normalizeOptions(options);
  const session = await getAuthSession();

  if (!session) return "no_session";

  const currentLocation = await getCurrentDeviceLocation().catch(() => null);
  const lastTrackedPoint =
    currentLocation || !trailId || !startedAt
      ? null
      : await getLastRouteTrackingPoint(trailId, startedAt).catch(() => null);
  const location =
    currentLocation ||
    (lastTrackedPoint
      ? {
          coordinate: [lastTrackedPoint.latitude, lastTrackedPoint.longitude] as [
            number,
            number,
          ],
          accuracy: lastTrackedPoint.accuracyMeters,
          timestamp: lastTrackedPoint.recordedAt,
        }
      : null);

  if (!location) return "no_location";

  const messageBody = buildEmergencyMessage({
    contact,
    latitude: location.coordinate[0],
    longitude: location.coordinate[1],
    trailId,
    timestamp: location.timestamp,
  });

  const payload = {
    trail_id: trailId ?? null,
    latitude: location.coordinate[0],
    longitude: location.coordinate[1],
    device_battery_percent: null,
    contact_name: contact?.name ?? null,
    contact_phone: contact?.phone ?? null,
    message_body: messageBody,
    last_known_at: new Date(location.timestamp).toISOString(),
  };

  const online = await isOnline();

  if (online) {
    try {
      await createEmergencyAlert(payload, session.token);
      return "sent";
    } catch (error) {
      // Se degrada a la cola offline en vez de perder el pedido de ayuda (RF-12).
    }
  }

  await enqueue("emergency_alert", payload);
  return "queued";
};
