import { router, useLocalSearchParams, useFocusEffect } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Text, TextInput, View } from "react-native";
import * as Crypto from "expo-crypto";
import * as SMS from "expo-sms";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";
import { getEmergencyContact } from "../../services/emergencyContact";
import { getAuthSession } from "../../services/authSession";
import { createTripPlan, TripPlanRecord } from "../../services/api";
import { getSavedTripPlans, refreshTripPlans, saveTripPlanLocally } from "../../services/tripPlans";
import { enqueueUnique, runSync } from "../../services/syncQueue";
import { EmergencyContact } from "../../types";

export default function TripPlanScreen() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const trailId = Number(id) || 1;
  const [contact, setContact] = useState<EmergencyContact | null>(null);
  const [hours, setHours] = useState("4");
  const [grace, setGrace] = useState("30");
  const [plan, setPlan] = useState<TripPlanRecord | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [closePending, setClosePending] = useState(false);
  const requestRef = useRef<Parameters<typeof createTripPlan>[0] | null>(null);
  const busyRef = useRef(false);
  useFocusEffect(useCallback(() => {
    let mounted = true;
    void getEmergencyContact().then((value) => { if (mounted) setContact(value); }).catch(() => undefined);
    return () => { mounted = false; };
  }, []));
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
      } catch { if (mounted && saved.length) setNotice("Mostrando el último estado guardado. Falta consultar al servidor."); }
    };
    void load().catch(() => setNotice("No pudimos cargar tu plan."));
    return () => { mounted = false; };
  }, [trailId]);
  const isActive = plan?.status === "active" || plan?.status === "overdue";
  const create = async () => {
    if (busyRef.current) return;
    if (!contact) { router.push("/contacto-seguridad"); return; }
    const duration = Number(hours.replace(",", "."));
    const margin = Number(grace);
    if (!(duration > 0 && duration <= 72 && Number.isInteger(margin) && margin >= 15 && margin <= 120)) {
      setNotice("Ingresá entre 0 y 72 horas y un margen de 15 a 120 minutos."); return;
    }
    busyRef.current = true; setBusy(true);
    try {
      const session = await getAuthSession();
      if (!session) throw new Error("Iniciá sesión para registrar el plan en el servidor.");
      // Retry the same immutable request if the server reply was lost.
      requestRef.current ??= { client_plan_id: Crypto.randomUUID(), trail_id: trailId,
        expected_return_at: new Date(Date.now() + duration * 3600000).toISOString(), grace_minutes: margin,
        contact_name: contact.name, contact_phone: contact.phone };
      const created = await createTripPlan(requestRef.current, session.token);
      await saveTripPlanLocally(created);
      setPlan(created); setClosePending(false); requestRef.current = null;
      setNotice("Plan registrado. El servidor intentará avisar si falta tu confirmación. La entrega al contacto no está garantizada.");
    } catch (error) { setNotice(error instanceof Error ? error.message : "El plan no quedó confirmado. Revisá su estado antes de salir."); }
    finally { busyRef.current = false; setBusy(false); }
  };
  const close = async (status: "checked_in" | "cancelled") => {
    if (!plan || busyRef.current) return;
    busyRef.current = true; setBusy(true);
    try {
      await enqueueUnique("trip_check_in", { planId: plan.id, status }, `trip-close:${plan.id}`);
      setClosePending(true);
      setNotice("Confirmación guardada en el teléfono. Hasta recibirla, el servidor puede emitir el aviso por atraso.");
      await runSync();
      const fresh = await refreshTripPlans(trailId).catch(() => []);
      const updated = fresh.find((value) => value.id === plan.id);
      if (updated) { setPlan(updated); if (["checked_in", "cancelled"].includes(updated.status)) { setClosePending(false); setNotice("El servidor confirmó el cierre del plan. Un aviso que ya se haya enviado no puede retirarse."); } }
    } catch { setNotice("No pudimos guardar la confirmación. Intentá nuevamente y avisá a tu contacto por otro medio."); }
    finally { busyRef.current = false; setBusy(false); }
  };
  const share = async () => {
    if (!contact) { router.push("/contacto-seguridad"); return; }
    const duration = Number(hours.replace(",", "."));
    if (!plan && (!Number.isFinite(duration) || duration <= 0 || duration > 72)) { setNotice("Indicá una duración válida antes de compartir."); return; }
    const deadline = plan?.expected_return_at ?? new Date(Date.now() + duration * 3600000).toISOString();
    try {
      if (!(await SMS.isAvailableAsync())) throw new Error("SMS no disponible en este dispositivo.");
      await SMS.sendSMSAsync([plan?.contact_phone ?? contact.phone], `Salgo a recorrer el sendero ${trailId}. Regreso previsto: ${new Date(deadline).toLocaleString("es-AR")}. Margen: ${plan?.grace_minutes ?? grace} min. Acordemos qué hacer si no confirmo mi regreso; puedo estar sin señal. Respondeme para confirmar que recibiste este plan.`);
      setNotice("Verificá el envío en Mensajes y esperá la respuesta del contacto. MiSendero no confirma la entrega del SMS.");
    } catch (error) { Alert.alert("No se pudo preparar el SMS", error instanceof Error ? error.message : "Intentá otro medio."); }
  };
  return <AppScreen withBottomNav={false}>
    <ScreenTitle eyebrow="Antes de salir" title="Plan de regreso" subtitle="Acordá el regreso cuando todavía tengas conexión." />
    <Card>
      <Text style={{ color: colors.ink, fontWeight: "700" }}>{contact ? `${contact.name} · ${contact.phone}` : "Falta un contacto de emergencia"}</Text>
      <Text style={{ color: colors.muted, marginTop: 8 }}>Si vos o tu contacto pierden señal, un aviso puede demorarse. Acordá también una persona alternativa y las acciones a seguir.</Text>
    </Card>
    {plan && <Card tone={isActive ? "orange" : "green"}>
      <Text style={{ color: colors.ink, fontWeight: "700" }}>{closePending ? "Cierre pendiente de confirmar" : plan.status === "active" ? "Plan registrado en el servidor" : plan.status === "overdue" ? "Regreso no confirmado a tiempo" : plan.status === "checked_in" ? "Regreso confirmado" : "Plan cancelado"}</Text>
      <Text style={{ color: colors.muted, marginTop: 8 }}>Regreso: {new Date(plan.expected_return_at).toLocaleString("es-AR")} · margen {plan.grace_minutes} min.</Text>
      {plan.notification_status === "accepted" && <Text style={{ color: colors.muted }}>El canal aceptó el aviso. Esto no confirma que el contacto lo recibió o leyó.</Text>}
    </Card>}
    {!isActive && <Card>
      <Text>Horas hasta el regreso</Text>
      <TextInput editable={!requestRef.current} accessibilityLabel="Horas hasta el regreso" keyboardType="decimal-pad" value={hours} onChangeText={setHours} style={{ minHeight: 48, borderBottomWidth: 1, borderColor: colors.muted }} />
      <Text>Margen de espera en minutos</Text>
      <TextInput editable={!requestRef.current} accessibilityLabel="Margen de espera en minutos" keyboardType="number-pad" value={grace} onChangeText={setGrace} style={{ minHeight: 48, borderBottomWidth: 1, borderColor: colors.muted }} />
      {requestRef.current && <Text style={{ color: colors.muted }}>Reintentaremos el mismo plan, con regreso previsto a las {new Date(requestRef.current.expected_return_at).toLocaleString("es-AR")}, para evitar duplicar el aviso.</Text>}
      <Text style={{ color: colors.muted, marginTop: 10 }}>Al registrar autorizás el aviso al contacto si no confirmás el regreso antes del plazo. El servicio debe tener un canal configurado.</Text>
      <PrimaryButton label={busy ? "Registrando…" : "Registrar aviso por atraso"} onPress={create} />
    </Card>}
    <View style={{ gap: 10 }}>
      <PrimaryButton label="Compartir plan por SMS" onPress={share} tone="secondary" />
      {isActive && <PrimaryButton label={busy ? "Guardando…" : "Ya regresé: confirmar"} onPress={() => void close("checked_in")} />}
      {isActive && <PrimaryButton label="Cancelar plan de salida" onPress={() => void close("cancelled")} tone="secondary" />}
      {!!notice && <Text accessibilityLiveRegion="polite" style={{ color: colors.ink, lineHeight: 21 }}>{notice}</Text>}
      <PrimaryButton label="Volver" onPress={() => router.back()} tone="secondary" />
    </View>
  </AppScreen>;
}
