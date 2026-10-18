import { router, useLocalSearchParams, useFocusEffect } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Text, TextInput, View } from "react-native";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";
import { getEmergencyContact } from "../../services/emergencyContact";
import { TripPlanRecord } from "../../services/api";
import { getSavedTripPlans, refreshTripPlans } from "../../services/tripPlans";
import { enqueueUnique, runSync } from "../../services/syncQueue";
import { EmergencyContact, Trail } from "../../types";
import { buildTripPlanMessage, getTrailForMessage } from "../../services/trailMessages";
import { getTrailById } from "../../services/trailRepository";
import { getEstimatedReturnHours } from "../../services/trailDuration";
import { DepartureMessage, getDepartureMessage, invalidateDepartureMessage, sendDeparturePlanSms } from "../../services/departureMessages";
import { isTestingLocationActive } from "../../services/testingMode";
import { userMessage } from "../../services/userMessages";

export default function TripPlanScreen() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const trailId = Number(id) || 1;
  const [contact, setContact] = useState<EmergencyContact | null>(null);
  const [hours, setHours] = useState("");
  const [grace, setGrace] = useState("30");
  const [plan, setPlan] = useState<TripPlanRecord | null>(null);
  const [trail, setTrail] = useState<Trail | null>(null);
  const [loadingTrail, setLoadingTrail] = useState(true);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [closePending, setClosePending] = useState(false);
  const [departureMessage, setDepartureMessage] = useState<DepartureMessage | null>(null);
  const [testingMode, setTestingMode] = useState(false);
  const busyRef = useRef(false);
  const hoursEditedRef = useRef(false);
  useEffect(() => {
    let active = true;
    setTrail(null);
    setHours("");
    setLoadingTrail(true);
    hoursEditedRef.current = false;
    setPlan(null);
    void getTrailById(trailId).then((value) => {
      if (!active) return;
      setTrail(value);
      const estimate = getEstimatedReturnHours(value.duration);
      if (!hoursEditedRef.current) {
        setHours(estimate === null ? "" : String(estimate).replace(".", ","));
      }
    }).catch(() => undefined).finally(() => { if (active) setLoadingTrail(false); });
    return () => { active = false; };
  }, [trailId]);
  useFocusEffect(useCallback(() => {
    let mounted = true;
    void getEmergencyContact().then((value) => { if (mounted) setContact(value); }).catch(() => undefined);
    void getDepartureMessage(trailId).then((value) => { if (mounted) setDepartureMessage(value); }).catch(() => { if (mounted) setDepartureMessage(null); });
    void isTestingLocationActive().then((value) => { if (mounted) setTestingMode(value); }).catch(() => undefined);
    return () => { mounted = false; };
  }, [trailId]));
  const invalidateNotice = async () => {
    setDepartureMessage(null);
    await invalidateDepartureMessage(trailId);
  };
  useEffect(() => {
    let mounted = true;
    const load = async () => {
      const [saved, person] = await Promise.all([getSavedTripPlans(trailId), getEmergencyContact()]);
      if (!mounted) return;
      setContact(person);
      setPlan(saved[0] ?? null);
      try {
        const fresh = await refreshTripPlans(trailId);
        if (mounted) setPlan(fresh[0] ?? null);
      } catch { if (mounted && saved.length) setNotice("Mostrando el último estado guardado. Conectate para actualizarlo."); }
    };
    void load().catch(() => setNotice("No pudimos cargar tu plan."));
    return () => { mounted = false; };
  }, [trailId]);
  const isActive = plan?.status === "active" || plan?.status === "overdue";
  const close = async (status: "checked_in" | "cancelled") => {
    if (!plan || busyRef.current) return;
    busyRef.current = true; setBusy(true);
    try {
      await invalidateNotice();
      await enqueueUnique("trip_check_in", { planId: plan.id, status }, `trip-close:${plan.id}`);
      setClosePending(true);
      setNotice("Confirmación guardada en el teléfono. Hasta que se envíe, el aviso por demora sigue activo.");
      await runSync();
      const fresh = await refreshTripPlans(trailId).catch(() => []);
      const updated = fresh.find((value) => value.id === plan.id);
      if (updated) { setPlan(updated); if (["checked_in", "cancelled"].includes(updated.status)) { setClosePending(false); setNotice("El plan quedó cerrado. Un aviso que ya se haya enviado no puede retirarse."); } }
    } catch { setNotice("No pudimos guardar la confirmación. Intentá nuevamente y avisá a tu contacto por otro medio."); }
    finally { busyRef.current = false; setBusy(false); }
  };
  const share = async () => {
    if (busyRef.current) return;
    if (!contact) { router.push("/contacto-seguridad"); return; }
    if (closePending) { setNotice("El cierre del plan sigue pendiente. Confirmalo antes de preparar otra salida."); return; }
    const sharedPlan = isActive ? plan : null;
    const duration = Number(hours.replace(",", "."));
    if (!sharedPlan && (!Number.isFinite(duration) || duration <= 0 || duration > 72)) { setNotice("Indicá una duración válida antes de compartir."); return; }
    if (!sharedPlan && (!Number.isInteger(Number(grace)) || Number(grace) < 15 || Number(grace) > 120)) { setNotice("Ingresá un margen de 15 a 120 minutos."); return; }
    const deadline = sharedPlan?.expected_return_at ?? new Date(Date.now() + duration * 3600000).toISOString();
    busyRef.current = true; setBusy(true);
    try {
      const selectedTrailId = sharedPlan?.trail_id ?? trailId;
      const selectedTrail = trail?.id === selectedTrailId ? trail : await getTrailForMessage(selectedTrailId);
      if (!selectedTrail?.name) throw new Error("No pudimos cargar el sendero. Volvé a intentar antes de enviar el plan.");
      const result = await sendDeparturePlanSms({
        trailId: selectedTrailId,
        contactPhone: sharedPlan?.contact_phone ?? contact.phone,
        expectedReturnAt: deadline,
        messageBody: buildTripPlanMessage({
          trail: selectedTrail,
          expectedReturnAt: deadline,
          graceMinutes: sharedPlan?.grace_minutes ?? grace,
        }),
      }, () => new Promise<boolean>((resolve) => Alert.alert(
        "Confirmar envío del plan",
        "El teléfono no informó si enviaste el SMS. ¿Lo enviaste a tu contacto de emergencia con este sendero y la hora de regreso? Abrir o cancelar Mensajes no cuenta como envío.",
        [{ text: "No lo envié", style: "cancel", onPress: () => resolve(false) },
          { text: "Sí, lo envié", onPress: () => resolve(true) }],
        { cancelable: true, onDismiss: () => resolve(false) }
      )));
      setDepartureMessage(await getDepartureMessage(trailId));
      setNotice(result.status === "confirmed"
        ? "Envío registrado para esta salida. Podés iniciar el recorrido. Esto no confirma que el contacto recibió el SMS."
        : "El envío no quedó confirmado. Enviá el plan antes de iniciar el recorrido.");
    } catch (error) { Alert.alert("No se pudo preparar el SMS", userMessage(error, "Intentá nuevamente o usá otro medio para avisar a tu contacto.")); }
    finally { busyRef.current = false; setBusy(false); }
  };
  return <AppScreen withBottomNav={false}>
    <ScreenTitle eyebrow="Antes de salir" title="Plan de regreso" subtitle="Acordá el regreso cuando todavía tengas conexión." />
    {testingMode && <Card tone="orange">
      <Text style={{ color: colors.ink, fontWeight: "700" }}>Modo prueba: no se envía plan de salida</Text>
      <Text style={{ color: colors.muted, marginTop: 8 }}>Los recorridos de prueba no envían SMS ni avisos a tu contacto. Para enviar un plan real, desactivá "Simular ubicacion en ruta" en Perfil.</Text>
    </Card>}
    <Card>
      <Text style={{ color: colors.ink, fontWeight: "700" }}>{contact ? `${contact.name} · ${contact.phone}` : "Falta un contacto de emergencia"}</Text>
      <Text style={{ color: colors.muted, marginTop: 8 }}>Si vos o tu contacto pierden señal, un aviso puede demorarse. Acordá también una persona alternativa y las acciones a seguir.</Text>
    </Card>
    {plan && <Card tone={isActive ? "orange" : "green"}>
      <Text style={{ color: colors.ink, fontWeight: "700" }}>{closePending ? "Cierre pendiente de confirmar" : plan.status === "active" ? "Aviso por demora activado" : plan.status === "overdue" ? "Regreso no confirmado a tiempo" : plan.status === "checked_in" ? "Regreso confirmado" : "Plan cancelado"}</Text>
      <Text style={{ color: colors.muted, marginTop: 8 }}>Regreso: {new Date(plan.expected_return_at).toLocaleString("es-AR")} · margen {plan.grace_minutes} min.</Text>
      {plan.notification_status === "accepted" && <Text style={{ color: colors.muted }}>El aviso fue aceptado para su envío. Esto no confirma que el contacto lo recibió o leyó.</Text>}
    </Card>}
    {!isActive && <Card>
      {trail?.duration && <Text style={{ color: colors.muted, marginBottom: 8 }}>Duración estimada del recorrido: {trail.duration}.</Text>}
      <Text>Horas hasta el regreso</Text>
      <TextInput editable={!busy && !testingMode} accessibilityLabel="Horas hasta el regreso" keyboardType="decimal-pad" value={hours}
        placeholder={loadingTrail ? "Cargando duración..." : "Horas"}
        onChangeText={(value) => { hoursEditedRef.current = true; setHours(value); void invalidateNotice().catch(() => setNotice("No pudimos actualizar el aviso. Volvé a enviarlo antes de salir.")); }}
        style={{ minHeight: 48, borderBottomWidth: 1, borderColor: colors.muted }} />
      <Text>Margen de espera en minutos</Text>
      <TextInput editable={!busy && !testingMode} accessibilityLabel="Margen de espera en minutos" keyboardType="number-pad" value={grace} onChangeText={(value) => { setGrace(value); void invalidateNotice().catch(() => setNotice("Volvé a enviar el plan actualizado antes de salir.")); }} style={{ minHeight: 48, borderBottomWidth: 1, borderColor: colors.muted }} />
      <Text style={{ color: colors.muted, marginTop: 10 }}>Compartí el sendero y la hora de regreso por SMS. Acordá con tu contacto qué hacer si no le avisás dentro del plazo.</Text>
    </Card>}
    <View style={{ gap: 10 }}>
      <PrimaryButton label={busy ? "Procesando..." : "Enviar plan por SMS"} icon="chatbubble-outline" disabled={busy || testingMode} onPress={share} />
      {departureMessage && <>
        <Text style={{ color: colors.green }}>Aviso {departureMessage.confirmation === "user_confirmed" ? "confirmado por vos" : "confirmado por el teléfono"}. Regreso: {new Date(departureMessage.expected_return_at).toLocaleString("es-AR")}.</Text>
        <PrimaryButton label="Volver al inicio del recorrido" disabled={busy} onPress={() => router.replace({ pathname: "/trail-start", params: { id: String(trailId) } })} />
      </>}
      {isActive && <PrimaryButton label="Ya regresé: confirmar" disabled={busy} onPress={() => void close("checked_in")} />}
      {isActive && <PrimaryButton label="Cancelar plan de salida" disabled={busy} onPress={() => void close("cancelled")} tone="secondary" />}
      {!!notice && <Text accessibilityLiveRegion="polite" style={{ color: colors.ink, lineHeight: 21 }}>{notice}</Text>}
      <PrimaryButton label="Volver" onPress={() => router.back()} tone="secondary" />
    </View>
  </AppScreen>;
}
