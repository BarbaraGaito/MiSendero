import * as SMS from "expo-sms";
import { getAuthSession } from "./authSession";
import { getEmergencyContact } from "./emergencyContact";
import { getRouteSession } from "./routeSession";
import { isTestingLocationActive } from "./testingMode";
import { buildRouteCompletionMessage, getTrailForMessage } from "./trailMessages";

export class CompletionContactRequiredError extends Error {
  constructor() { super("Agregá tu contacto de emergencia para informarle que terminaste el recorrido."); }
}

export const sendRouteCompletionSms = async (context: { trailId: number; startedAt: number; simulated: boolean }) => {
  const assertRealRoute = async () => {
    if (context.simulated || await isTestingLocationActive() || (await getRouteSession(context.trailId, context.startedAt))?.simulated) {
      throw new Error("Los recorridos de prueba no envían avisos a tu contacto.");
    }
  };
  await assertRealRoute();
  const owner = (await getAuthSession())?.user.id;
  const contact = await getEmergencyContact();
  if (!contact?.phone) throw new CompletionContactRequiredError();
  if (!await SMS.isAvailableAsync()) throw new Error("Este dispositivo no permite enviar SMS. Avisá a tu contacto desde un teléfono con servicio celular.");
  const trail = await getTrailForMessage(context.trailId);
  const message = buildRouteCompletionMessage(trail);
  await assertRealRoute();
  const currentContact = await getEmergencyContact();
  if ((await getAuthSession())?.user.id !== owner || currentContact?.phone !== contact.phone) {
    throw new Error("La cuenta o el contacto cambió. Volvé a preparar el mensaje.");
  }
  // Opening the composer neither confirms delivery nor closes a trip plan.
  const result = await SMS.sendSMSAsync([contact.phone], message);
  return { result: result.result, message };
};
