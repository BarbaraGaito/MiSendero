import { Trail } from "../types";
import { parseRouteCoordinates } from "./geoUtils";
import { getTrailById } from "./trailRepository";

export const getTrailForMessage = async (trailId?: number | null): Promise<Trail | null> => {
  if (!trailId || !Number.isInteger(trailId) || trailId <= 0) return null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  // Optional route metadata must not delay an SOS when the network is unavailable.
  const trail = await Promise.race([
    getTrailById(trailId).catch(() => null),
    new Promise<null>((resolve) => { timer = setTimeout(() => resolve(null), 2000); }),
  ]).finally(() => { if (timer) clearTimeout(timer); });
  return trail?.id === trailId ? trail : null;
};

export const formatTrailMessageContext = (trail?: Trail | null) => {
  if (!trail?.name?.trim()) return "Sendero: nombre no disponible.";
  const parts = [`Sendero: ${trail.name.trim()}.`];
  if (trail.location?.trim()) parts.push(`Zona: ${trail.location.trim()}.`);
  const start = parseRouteCoordinates(trail.route_coordinates)[0];
  if (start && Math.abs(start[0]) <= 90 && Math.abs(start[1]) <= 180) {
    parts.push(`Inicio del recorrido: ${start[0].toFixed(5)}, ${start[1].toFixed(5)}. https://maps.google.com/?q=${start[0]},${start[1]}`);
  }
  return parts.join(" ");
};

export const buildTripPlanMessage = ({ trail, expectedReturnAt, graceMinutes }: {
  trail: Trail | null;
  expectedReturnAt: string;
  graceMinutes: string | number;
}) => `Plan de salida MiSendero. ${formatTrailMessageContext(trail)} Regreso previsto: ${new Date(expectedReturnAt).toLocaleString("es-AR")}. Margen: ${graceMinutes} min. Acordemos qu\u00e9 hacer si no confirmo mi regreso; puedo estar sin se\u00f1al. Respondeme para confirmar que recibiste este plan.`;

export const buildRouteCompletionMessage = (trail: Trail | null) => {
  const route = trail?.name?.trim() ? `en el sendero ${trail.name.trim()}` : "de trekking";
  const location = trail?.location?.trim() ? ` Ubicación: ${trail.location.trim()}.` : "";
  return `MiSendero: terminé mi recorrido ${route}.${location} Te aviso para que sepas que finalicé mi salida.`;
};
