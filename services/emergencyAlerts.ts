import { getCurrentDeviceLocation } from "./deviceLocation";
import { createEmergencyAlert } from "./api";
import { getAuthSession } from "./authSession";
import { enqueue, isOnline } from "./syncQueue";

export type EmergencyAlertOutcome = "sent" | "queued" | "no_location" | "no_session";

export const sendEmergencyAlert = async (
  trailId?: number | null
): Promise<EmergencyAlertOutcome> => {
  const session = await getAuthSession();

  if (!session) return "no_session";

  const location = await getCurrentDeviceLocation().catch(() => null);

  if (!location) return "no_location";

  const payload = {
    trail_id: trailId ?? null,
    latitude: location.coordinate[0],
    longitude: location.coordinate[1],
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
