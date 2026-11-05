import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Linking, StyleSheet, Text, View } from "react-native";
import * as Crypto from "expo-crypto";
import * as SMS from "expo-sms";
import { getEmergencyContact } from "../../services/emergencyContact";
import {
  buildEmergencyMessage, EmergencyTestReason, getEmergencyLocation, getEmergencyTestReason,
  sendEmergencyAlert, sendEmergencySms, SimulatedEmergencyError,
} from "../../services/emergencyAlerts";
import { saveTestingLocationMode } from "../../services/testingMode";
import { getTrailForMessage } from "../../services/trailMessages";
import { getEmergencyOperation, PendingOperation, runSync } from "../../services/syncQueue";
import { EmergencyContact } from "../../types";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";
import { SosConnectivityNotice } from "../components/SosConnectivityNotice";

export default function ConfirmSosScreen() {
  const { id, startedAt, operationId: savedOperationId, simulated, sendSms, origen } = useLocalSearchParams<{ id?: string; startedAt?: string; operationId?: string; simulated?: string; sendSms?: string; origen?: string }>();
  const trailId = Number(id) || null;
  const startedAtMs = Number(startedAt) || null;
  const simulatedSource = simulated === "1";
  const eventId = useRef(Crypto.randomUUID());
  const saving = useRef(false);
  const sendingSms = useRef(false);
  const autoSmsHandled = useRef(false);
  const smsMessage = useRef<string | null>(null);
  const [contextReady, setContextReady] = useState(false);
  const [contact, setContact] = useState<EmergencyContact | null>(null);
  const [message, setMessage] = useState(buildEmergencyMessage({ latitude: null, longitude: null, trailId, timestamp: Date.now() }));
  const [operationId, setOperationId] = useState<number | null>(Number(savedOperationId) || null);
  const [operation, setOperation] = useState<PendingOperation | null>(null);
  const [busy, setBusy] = useState(false);
  const [smsStatus, setSmsStatus] = useState("");
  const [preparingSms, setPreparingSms] = useState(false);
  // Test mode: the flow stays testable but nothing is sent, queued or stored.
  const [testReason, setTestReason] = useState<EmergencyTestReason | null>(simulatedSource ? "simulated_data" : null);
  const [testDone, setTestDone] = useState(false);
  const testing = testReason !== null;

  useFocusEffect(useCallback(() => {
    let active = true;
    setContextReady(false);
    void Promise.all([
      getEmergencyContact().catch(() => null),
      getEmergencyTestReason({ trailId, startedAt: startedAtMs, simulated: simulatedSource }),
    ]).then(([person, reason]) => {
      if (!active) return;
      setContact(person);
      setTestReason(reason);
      setContextReady(true);
    }).catch(() => {
      if (active) setSmsStatus("No pudimos preparar el SOS. Intentá nuevamente o llamá a tu contacto.");
    });
    return () => { active = false; };
  }, [trailId, startedAtMs, simulatedSource]));

  useEffect(() => {
    if (operationId) return;
    let active = true;
    void Promise.all([getEmergencyLocation(trailId, startedAtMs), getTrailForMessage(trailId)]).then(([location, trail]) => {
      if (active) setMessage(buildEmergencyMessage({ ...location, trail }));
    });
    return () => { active = false; };
  }, [trailId, startedAtMs, operationId]);

  useEffect(() => {
    if (!operationId) return;
    let active = true;
    let savedTrail: Awaited<ReturnType<typeof getTrailForMessage>> | undefined;
    const refresh = async () => {
      const value = await getEmergencyOperation(operationId);
      if (!active) return;
      setOperation(value);
      if (!smsMessage.current && typeof value?.payload.message_body === "string") {
        if (value.payload.message_body.includes("Sendero ID ")) {
          if (savedTrail === undefined) savedTrail = await getTrailForMessage(
            typeof value.payload.trail_id === "number" ? value.payload.trail_id : null
          );
          if (!active) return;
          const recordedAt = typeof value.payload.last_known_at === "string" ? Date.parse(value.payload.last_known_at) : Number.NaN;
          setMessage(buildEmergencyMessage({
            trail: savedTrail,
            latitude: typeof value.payload.latitude === "number" ? value.payload.latitude : null,
            longitude: typeof value.payload.longitude === "number" ? value.payload.longitude : null,
            timestamp: Number.isFinite(recordedAt) ? recordedAt : value.createdAt,
          }));
        } else {
          setMessage(value.payload.message_body);
        }
      }
    };
    void refresh().catch(() => undefined);
    const timer = setInterval(() => { void refresh().catch(() => undefined); }, 2000);
    return () => { active = false; clearInterval(timer); };
  }, [operationId]);

  const handleSos = async () => {
    if (saving.current) return;
    if (testing) { setTestDone(true); return; }
    if (operationId) { void runSync().catch(() => undefined); return; }
    saving.current = true;
    setBusy(true);
    try {
      const result = await sendEmergencyAlert({ trailId, contact, startedAt: startedAtMs, eventId: eventId.current, simulated: simulatedSource });
      setMessage(result.message);
      setOperationId(result.operationId);
      router.setParams({ operationId: String(result.operationId) });
    } catch (error) {
      if (error instanceof SimulatedEmergencyError) { setTestReason(error.reason); setTestDone(true); }
      else Alert.alert("No pudimos guardar el pedido", "Podés usar el SMS preparado o llamar al contacto. Volvé a intentar guardar el SOS.");
    } finally { saving.current = false; setBusy(false); }
  };

  // Real emergency during a test: leave testing mode and open a real SOS that
  // only carries the device GPS, never the simulated route or wearable data.
  const requestRealHelp = async () => {
    if (testReason === "testing_location") {
      await saveTestingLocationMode(false).catch(() => undefined);
      router.replace("/confirmar-sos");
      return;
    }
    router.replace({ pathname: "/confirmar-sos", params: { ...(id ? { id } : {}), ...(startedAt ? { startedAt } : {}) } });
  };

  const handleSms = useCallback(async () => {
    if (sendingSms.current || !contextReady || testing) return;
    if (!contact) { router.push("/contacto-seguridad"); return; }
    sendingSms.current = true;
    setPreparingSms(true);
    setSmsStatus("");
    try {
      if (!(await SMS.isAvailableAsync())) {
        Alert.alert("SMS no disponible en este dispositivo", "Usá el mensaje preparado desde un teléfono con servicio celular.");
        return;
      }
      // Refresh the location for every SMS, even when a previous SOS was saved.
      // Native Messages can open without Internet or a backend acknowledgement.
      const [location, trail] = await Promise.all([getEmergencyLocation(trailId, startedAtMs), getTrailForMessage(trailId)]);
      const preparedMessage = buildEmergencyMessage({ ...location, trail });
      smsMessage.current = preparedMessage;
      setMessage(preparedMessage);
      const result = await sendEmergencySms(contact.phone, preparedMessage, { trailId, startedAt: startedAtMs, simulated: simulatedSource });
      setSmsStatus(result.result === "cancelled" ? "SMS cancelado. No se confirmó el envío a tu contacto."
        : result.result === "sent" ? "El teléfono indicó que enviaste el SMS. Esto no confirma que tu contacto lo recibió."
          : "Se abrió Mensajes. Verificá allí el estado del SMS; MiSendero no puede confirmar su entrega.");
    } catch (error) {
      if (error instanceof SimulatedEmergencyError) setTestReason(error.reason);
      else setSmsStatus("No pudimos abrir Mensajes. Intentá llamar al contacto.");
    }
    finally { sendingSms.current = false; setPreparingSms(false); }
  }, [contact, contextReady, testing, trailId, startedAtMs, simulatedSource]);

  useEffect(() => {
    // Consume only an explicit tap on the route SOS. Returning from Messages
    // must never open another composer automatically.
    if (sendSms !== "1" || !contextReady || autoSmsHandled.current) return;
    autoSmsHandled.current = true;
    router.setParams({ sendSms: "0" });
    void handleSms();
  }, [sendSms, contextReady, handleSms]);

  const registered = operation?.status === "synced";
  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle eyebrow={testing ? "Modo prueba" : "Emergencia"} title="Pedir ayuda" subtitle="Enviá un SMS a tu contacto con el sendero y tu última ubicación disponible." />
      {testing ? <Card tone="orange">
        <Text style={styles.title}>Modo prueba: el SOS no se envía</Text>
        <Text style={styles.body}>{testDone
          ? "Prueba completada. No se envió ningún SMS ni se guardó un pedido de ayuda."
          : `${testReason === "simulated_data" ? "Esta alerta salió de datos simulados del reloj." : "Estás en un recorrido con ubicación simulada."} No se envía SMS ni se guarda un pedido de ayuda.`}</Text>
        <Text style={styles.body}>{testReason === "simulated_data"
          ? "¿Es una emergencia real? Abrí el SOS real: usa la ubicación GPS del teléfono, no los datos simulados."
          : "¿Es una emergencia real? Para enviar un SOS real tenés que salir del modo prueba: el botón desactiva \"Simular ubicacion en ruta\" y abre el SOS real con la ubicación GPS del teléfono. También podés llamar directamente a tu contacto."}</Text>
        <PrimaryButton label={testReason === "simulated_data" ? "Emergencia real: pedir ayuda" : "Emergencia real: salir del modo prueba"}
          onPress={() => void requestRealHelp()} tone="danger" />
      </Card> : <Card tone="red">
        <Text style={styles.title}>{registered ? "Pedido guardado en MiSendero" : operationId ? "SOS guardado en este teléfono" : "Avisá a tu contacto"}</Text>
        <Text style={styles.body}>{registered
          ? "Guardamos tu pedido en MiSendero. Para avisar a tu contacto, usá SMS o llamada."
          : operationId
            ? operation?.userId === null ? "Sin sesión: conservamos el pedido localmente. Usá SMS o llamada; no se subirá con otra cuenta."
              : "El pedido se guardó en este teléfono. Se enviará a MiSendero cuando tengas internet y la app esté abierta. Para avisar a tu contacto, usá SMS o llamada."
            : "Abriremos Mensajes con el SOS preparado. Confirmá el envío desde allí. Si no hay GPS, podés enviar el pedido igualmente."}</Text>
      </Card>}
      {origen === "caida" && <Card tone="orange">
        <Text style={styles.title}>Abierto desde la detección de caídas (IA experimental)</Text>
        <Text style={styles.body}>MiSendero no envió ni llamó a nadie. Elegí cómo avisar: SMS o llamada a tu contacto. La última ubicación disponible y su fecha figuran en el mensaje.</Text>
      </Card>}
      <Card>
        <Text style={styles.title}>{contact ? `${contact.name} · ${contact.phone}` : "Sin contacto configurado"}</Text>
        <Text style={styles.body}>Podés guardar o cambiar el contacto en este dispositivo sin internet.</Text>
        <PrimaryButton label="Editar contacto" href="/contacto-seguridad" tone="secondary" />
      </Card>
      <Card>
        <Text style={styles.title}>{testing ? "Mensaje de ejemplo (no se envía)" : "Mensaje para compartir"}</Text>
        <Text selectable style={styles.body}>{message}</Text>
      </Card>
      {!testing && <Card>
        <Text style={styles.title}>Estado del pedido</Text>
        <Text style={styles.body}>Preparación: mensaje disponible en este teléfono.</Text>
        <Text style={styles.body}>Registro en MiSendero: {registered ? "guardado" : operation?.status === "syncing" ? "enviando" : operationId ? "por enviar" : "sin iniciar"}.</Text>
        <Text style={styles.body}>Envío al contacto: {smsStatus || "sin confirmación; abrí Mensajes o llamá al contacto"}.</Text>
        <Text style={styles.body}>Entrega al contacto: sin confirmación en MiSendero.</Text>
        <Text style={styles.body}>Asistencia: sin confirmación. MiSendero no activa ni garantiza un rescate.</Text>
      </Card>}
      <View style={styles.actions}>
        {!testing && <PrimaryButton label="Enviar SOS por SMS" onPress={handleSms} tone="danger" disabled={!contextReady} isLoading={preparingSms} loadingLabel="Preparando mensaje" />}
        {contact && <PrimaryButton label="Llamar al contacto" tone="secondary" onPress={() => {
          void Linking.openURL(`tel:${contact.phone.replace(/[^+\d]/g, "")}`).catch(() => Alert.alert("No se pudo abrir Teléfono"));
        }} />}
        <PrimaryButton label={testing ? "Probar pedido SOS (no se envía)" : busy ? "Guardando pedido…" : operationId ? "Reintentar registro" : "Guardar pedido SOS"} onPress={handleSos} tone="secondary" disabled={!contextReady || busy} />
        {!!smsStatus && <Text accessibilityLiveRegion="polite" style={styles.body}>{smsStatus}</Text>}
      </View>
      <SosConnectivityNotice />
      <Card tone="orange">
        <Text style={styles.title}>Qué ocurre sin señal</Text>
        <Text style={styles.body}>Sin internet pero con servicio celular, el SMS o la llamada pueden funcionar. Sin cobertura celular ni Wi-Fi, el teléfono no puede avisar por estos medios. Si tu contacto está sin señal, puede recibir el aviso más tarde: necesitás una respuesta suya para confirmar que lo vio.</Text>
        <Text style={styles.body}>Antes de salir, acordá ruta, hora de regreso y qué hacer si no confirmás la llegada. No dependas de un envío desde una zona sin cobertura.</Text>
      </Card>
      <PrimaryButton label="Volver al recorrido" tone="secondary" onPress={() => {
        if (router.canGoBack()) router.back();
        else router.replace({ pathname: "/route-map", params: { id: id ?? "1", ...(startedAt ? { active: "1", startedAt } : {}) } });
      }} />
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  title: { color: colors.ink, fontSize: 17, fontWeight: "800" },
  body: { color: colors.muted, fontSize: 14, lineHeight: 21, marginTop: 8 },
  actions: { gap: 10, marginVertical: 12 },
});
