import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { StyleSheet, Text, Vibration, View } from "react-native";
import { answerFallEvent, FallEventRecord, getFallEvent } from "../../services/fallDetection/fallEvents";
import { fallMonitor } from "../../services/fallDetection/monitor";
import { getLastRouteTrackingPoint } from "../../services/routeTracking";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";

export const FALL_ASSISTANCE_MESSAGE = "MiSendero detectó un movimiento compatible con una caída. ¿Necesitás ayuda?";

// Nothing is sent or dialled here. "Solicitar ayuda" only opens the existing SOS screen, where the
// user still chooses SMS / call. Closing the screen without answering is stored as "unanswered":
// it is never read as "the user is fine" nor as "the user is unconscious".
export default function FallAssistanceScreen() {
  const { eventId, id, startedAt } = useLocalSearchParams<{ eventId?: string; id?: string; startedAt?: string }>();
  const [event, setEvent] = useState<FallEventRecord | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const answered = useRef(false);

  useEffect(() => {
    let active = true;
    if (eventId) void getFallEvent(eventId).then((value) => { if (active) setEvent(value); }).catch(() => undefined);
    return () => { active = false; };
  }, [eventId]);

  useEffect(() => () => {
    Vibration.cancel();
    if (eventId && !answered.current) {
      void answerFallEvent(eventId, "unanswered", "none").catch(() => undefined);
      fallMonitor.clearPending(eventId);
    }
  }, [eventId]);

  const finish = (action: () => void) => { Vibration.cancel(); answered.current = true; fallMonitor.clearPending(eventId); action(); };

  const imFine = async () => {
    if (!eventId || busy) return;
    setBusy(true);
    try {
      await answerFallEvent(eventId, "ok", "dismissed");
      finish(() => { if (router.canGoBack()) router.back(); else router.replace("/inicio"); });
    } catch { setError("No pudimos guardar tu respuesta. Intentá nuevamente."); setBusy(false); }
  };

  const requestHelp = async () => {
    if (!eventId || busy) return;
    setBusy(true);
    try {
      const trailId = Number(id) || null;
      const startedAtMs = Number(startedAt) || null;
      const point = trailId && startedAtMs ? await getLastRouteTrackingPoint(trailId, startedAtMs).catch(() => null) : null;
      const location = point && !point.simulated ? { latitude: point.latitude, longitude: point.longitude, recordedAt: point.recordedAt } : null;
      await answerFallEvent(eventId, "help", "sos_opened", location);
    } catch { /* The SOS must open even if the local log fails. */ }
    finish(() => router.replace({ pathname: "/confirmar-sos", params: {
      ...(id ? { id } : {}), ...(startedAt ? { startedAt } : {}), origen: "caida" } }));
  };

  return (
    <AppScreen withBottomNav={false}>
      <ScreenTitle eyebrow="IA experimental" title="Posible caída" subtitle="Detección local en el teléfono, sin Internet." />
      <Card tone="red">
        <Text accessibilityRole="alert" style={styles.message}>{FALL_ASSISTANCE_MESSAGE}</Text>
        {event && <Text style={styles.body}>
          Detectado a las {new Intl.DateTimeFormat("es-AR", { timeStyle: "medium" }).format(event.detectedAt)}.
        </Text>}
      </Card>
      <View style={styles.actions}>
        <PrimaryButton label="Estoy bien" tone="green" onPress={() => void imFine()} disabled={busy || !eventId} />
        <PrimaryButton label="Solicitar ayuda" tone="danger" onPress={() => void requestHelp()} disabled={busy || !eventId} />
        {!!error && <Text accessibilityLiveRegion="polite" style={styles.error}>{error}</Text>}
      </View>
      <Card tone="orange">
        <Text style={styles.body}>MiSendero no llama ni envía mensajes por su cuenta. Si no respondés, no asumimos que estás inconsciente ni avisamos a nadie.</Text>
        <Text style={styles.body}>El modelo es experimental y puede equivocarse: se entrenó con caídas simuladas, no con accidentes de montaña.</Text>
      </Card>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  message: { color: colors.ink, fontSize: 20, fontWeight: "800", lineHeight: 28 },
  body: { color: colors.muted, fontSize: 14, lineHeight: 21, marginTop: 8 },
  actions: { gap: 10, marginVertical: 12 },
  error: { color: colors.danger, fontSize: 14, fontWeight: "700" },
});
