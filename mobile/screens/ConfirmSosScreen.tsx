import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Linking, StyleSheet, Text, View } from "react-native";
import * as Crypto from "expo-crypto";
import * as SMS from "expo-sms";
import { getEmergencyContact } from "../../services/emergencyContact";
import { buildEmergencyMessage, getEmergencyLocation, sendEmergencyAlert } from "../../services/emergencyAlerts";
import { getTrailForMessage } from "../../services/trailMessages";
import { getEmergencyOperation, PendingOperation, runSync } from "../../services/syncQueue";
import { EmergencyContact } from "../../types";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";

export default function ConfirmSosScreen() {
  const { id, startedAt, operationId: savedOperationId } = useLocalSearchParams<{ id?: string; startedAt?: string; operationId?: string }>();
  const trailId = Number(id) || null;
  const startedAtMs = Number(startedAt) || null;
  const eventId = useRef(Crypto.randomUUID());
  const saving = useRef(false);
  const [contact, setContact] = useState<EmergencyContact | null>(null);
  const [message, setMessage] = useState(buildEmergencyMessage({ latitude: null, longitude: null, trailId, timestamp: Date.now() }));
  const [operationId, setOperationId] = useState<number | null>(Number(savedOperationId) || null);
  const [operation, setOperation] = useState<PendingOperation | null>(null);
  const [busy, setBusy] = useState(false);
  const [smsStatus, setSmsStatus] = useState("");
  const [preparingSms, setPreparingSms] = useState(false);

  useFocusEffect(useCallback(() => {
    let active = true;
    void getEmergencyContact().then((value) => { if (active) setContact(value); }).catch(() => undefined);
    return () => { active = false; };
  }, []));

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
      if (typeof value?.payload.message_body === "string") {
        if (value.payload.message_body.includes("Sendero ID ")) {
          if (savedTrail === undefined) savedTrail = await getTrailForMessage(
            typeof value.payload.trail_id === "number" ? value.payload.trail_id : null
          );
          if (!active) return;
          const recordedAt = typeof value.payload.last_known_at === "string" ? Date.parse(value.payload.last_known_at) : NaN;
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
    if (operationId) { void runSync().catch(() => undefined); return; }
    saving.current = true;
    setBusy(true);
    try {
      const result = await sendEmergencyAlert({ trailId, contact, startedAt: startedAtMs, eventId: eventId.current });
      setMessage(result.message);
      setOperationId(result.operationId);
      router.setParams({ operationId: String(result.operationId) });
    } catch {
      Alert.alert("No pudimos guardar el pedido", "Podés usar el SMS preparado o llamar al contacto. Volvé a intentar guardar el SOS.");
    } finally { saving.current = false; setBusy(false); }
  };

  const handleSms = async () => {
    if (preparingSms) return;
    if (!contact) { router.push("/contacto-seguridad"); return; }
    setPreparingSms(true);
    try {
      if (!(await SMS.isAvailableAsync())) {
        Alert.alert("SMS no disponible en este dispositivo", "Usá el mensaje preparado desde un teléfono con servicio celular.");
        return;
      }
      let preparedMessage = message;
      if (!operationId) {
        const [location, trail] = await Promise.all([getEmergencyLocation(trailId, startedAtMs), getTrailForMessage(trailId)]);
        preparedMessage = buildEmergencyMessage({ ...location, trail });
        setMessage(preparedMessage);
      }
      const result = await SMS.sendSMSAsync([contact.phone], preparedMessage);
      setSmsStatus(result.result === "cancelled" ? "SMS cancelado." : "Se abrió Mensajes. Verificá allí el estado del SMS; MiSendero no puede confirmar su entrega.");
    } catch { setSmsStatus("No pudimos abrir Mensajes. Intentá llamar al contacto."); }
    finally { setPreparingSms(false); }
  };

  const registered = operation?.status === "synced";
  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle eyebrow="Emergencia" title="Pedir ayuda" subtitle="El registro en MiSendero y el aviso a tu contacto son acciones distintas." />
      <Card tone="red">
        <Text style={styles.title}>{registered ? "SOS registrado en el servidor" : operationId ? "SOS guardado en este teléfono" : "Guardá tu pedido de ayuda"}</Text>
        <Text style={styles.body}>{registered
          ? "El servidor recibió el registro. Esto no confirma que tu contacto haya sido avisado. Usá SMS o llamada."
          : operationId
            ? operation?.userId === null ? "Sin sesión: conservamos el pedido localmente. Usá SMS o llamada; no se subirá con otra cuenta."
              : "Pendiente de registro en el servidor. La app reintentará con internet mientras esté abierta. El contacto todavía no fue avisado."
            : "Se guardará aunque falte GPS o internet. La última ubicación incluirá su hora; puede no ser tu posición actual."}</Text>
      </Card>
      <Card>
        <Text style={styles.title}>{contact ? `${contact.name} · ${contact.phone}` : "Sin contacto configurado"}</Text>
        <Text style={styles.body}>Podés guardar o cambiar el contacto en este dispositivo sin internet.</Text>
        <PrimaryButton label="Editar contacto" href="/contacto-seguridad" tone="secondary" />
      </Card>
      <Card>
        <Text style={styles.title}>Mensaje para compartir</Text>
        <Text selectable style={styles.body}>{message}</Text>
      </Card>
      <View style={styles.actions}>
        <PrimaryButton label={busy ? "Guardando pedido…" : operationId ? "Reintentar registro" : "Guardar pedido SOS"} onPress={handleSos} tone="danger" />
        <PrimaryButton label="Preparar SMS al contacto" onPress={handleSms} isLoading={preparingSms} loadingLabel="Preparando mensaje" />
        {contact && <PrimaryButton label="Llamar al contacto" tone="secondary" onPress={() => {
          void Linking.openURL(`tel:${contact.phone.replace(/[^+\d]/g, "")}`).catch(() => Alert.alert("No se pudo abrir Teléfono"));
        }} />}
        {!!smsStatus && <Text accessibilityLiveRegion="polite" style={styles.body}>{smsStatus}</Text>}
      </View>
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
