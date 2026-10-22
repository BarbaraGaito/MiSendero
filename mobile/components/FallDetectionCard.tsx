import { Ionicons } from "@expo/vector-icons";
import { useCallback, useEffect, useState } from "react";
import { Alert, StyleSheet, Switch, Text, View } from "react-native";
import { getFallSettings, saveFallSettings } from "../../services/fallDetection/fallEvents";
import { platformLimitations, requestSensorPermission } from "../../services/fallDetection/monitor";
import type { MonitorSnapshot } from "../../services/fallDetection/monitor";
import { useFallMonitor } from "../hooks/useFallMonitor";
import { InfoCard, colors } from "./MiSenderoUI";

export const FALL_FEATURE_NAME = "Detección de caídas — IA experimental";

const POSITION_NOTE = "El modelo se entrenó con teléfonos en el bolsillo del pantalón. En mochila, mano u otra posición no fue validado y puede no detectar caídas.";
const OFFLINE_NOTE = "Funciona sin Internet: el modelo se ejecuta en este teléfono y no se envían datos del sensor.";
const EXPERIMENTAL_NOTE = "Experimental: se entrenó con caídas simuladas por voluntarios, no con accidentes de montaña. Puede no detectar una caída o avisar sin que haya ocurrido. No reemplaza llevar un plan de emergencia.";

export const monitorStatusText = (snapshot: MonitorSnapshot, enabled: boolean, routeActive: boolean) => {
  switch (snapshot.state) {
    case "monitoring": return `Monitoreo activo${snapshot.measuredRateHz ? ` (${snapshot.measuredRateHz.toFixed(0)} Hz)` : ""}.`;
    case "starting": return "Iniciando el acelerómetro…";
    case "interrupted": return snapshot.reason ?? "Monitoreo interrumpido: sin protección.";
    case "degraded_rate": return snapshot.reason ?? "Frecuencia de muestreo insuficiente.";
    case "unavailable": return snapshot.reason ?? "No disponible en este teléfono.";
    default: return !enabled ? "Desactivada: no se lee el acelerómetro."
      : routeActive ? "Activada: esperando que el monitoreo comience." : "Activada: comenzará cuando inicies un recorrido.";
  }
};

const useEnabled = () => {
  const [enabled, setEnabled] = useState(false);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let active = true;
    void getFallSettings().then((s) => { if (active) { setEnabled(s.enabled); setLoaded(true); } }).catch(() => { if (active) setLoaded(true); });
    return () => { active = false; };
  }, []);
  return { enabled, setEnabled, loaded };
};

export function FallDetectionCard() {
  const snapshot = useFallMonitor();
  const { enabled, setEnabled, loaded } = useEnabled();
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  const enable = useCallback(async () => {
    setBusy(true);
    try {
      const check = await requestSensorPermission();
      if (!check.available) { setNotice("Este teléfono no informa un acelerómetro disponible."); return; }
      if (!check.granted) { setNotice("Falta el permiso de movimiento. Activalo en los ajustes del teléfono."); return; }
      await saveFallSettings({ enabled: true, limitationsAcknowledgedAt: Date.now() });
      setEnabled(true);
      setNotice("");
    } catch { setNotice("No pudimos guardar la preferencia. Intentá nuevamente."); }
    finally { setBusy(false); }
  }, [setEnabled]);

  const onToggle = (value: boolean) => {
    if (busy || !loaded) return;
    if (!value) {
      setBusy(true);
      void saveFallSettings({ enabled: false, limitationsAcknowledgedAt: null }).then(() => { setEnabled(false); setNotice(""); })
        .catch(() => setNotice("No pudimos guardar la preferencia. Intentá nuevamente."))
        .finally(() => setBusy(false));
      return;
    }
    Alert.alert("Antes de activar", `${EXPERIMENTAL_NOTE}\n\n${POSITION_NOTE}\n\n${platformLimitations}\n\nMiSendero nunca llama ni envía SMS por su cuenta: solo te pregunta si necesitás ayuda.`, [
      { text: "Cancelar", style: "cancel" },
      { text: "Entiendo, activar", onPress: () => { void enable(); } },
    ]);
  };

  return (
    <InfoCard style={styles.card}>
      <View style={styles.header}>
        <Ionicons name="pulse-outline" size={24} color={colors.green} />
        <View style={styles.headerText}>
          <Text style={styles.title}>{FALL_FEATURE_NAME}</Text>
          <Text accessibilityLiveRegion="polite" style={[styles.status, ["interrupted", "unavailable", "degraded_rate"].includes(snapshot.state) && styles.statusWarning]}>
            {monitorStatusText(snapshot, enabled, snapshot.startedAt !== null)}
          </Text>
        </View>
        <Switch accessibilityLabel={FALL_FEATURE_NAME} value={enabled} disabled={busy || !loaded} onValueChange={onToggle}
          trackColor={{ true: colors.green, false: colors.line }} />
      </View>
      {!!notice && <Text accessibilityLiveRegion="polite" style={styles.statusWarning}>{notice}</Text>}
      <Text style={styles.body}>Sensor: {snapshot.sensorAvailable === null ? "se verificará al activar" : snapshot.sensorAvailable ? "acelerómetro disponible" : "acelerómetro no disponible"}.</Text>
      <Text style={styles.body}>{OFFLINE_NOTE}</Text>
      <Text style={styles.body}>{POSITION_NOTE}</Text>
      <Text style={styles.body}>{platformLimitations}</Text>
      <Text style={styles.body}>{EXPERIMENTAL_NOTE}</Text>
    </InfoCard>
  );
}

/** One line for the active-route screen: the real state, never a promise of protection. */
export function FallDetectionStatusLine() {
  const snapshot = useFallMonitor();
  const { enabled } = useEnabled();
  if (!enabled && snapshot.state === "off") return null;
  const ok = snapshot.state === "monitoring";
  return (
    <Text accessibilityLiveRegion="polite" style={[styles.line, !ok && styles.statusWarning]}>
      Caídas (IA experimental): {monitorStatusText(snapshot, enabled, true)}
    </Text>
  );
}

const styles = StyleSheet.create({
  card: { flexDirection: "column", alignItems: "stretch", gap: 6 },
  header: { flexDirection: "row", alignItems: "center", gap: 12 },
  headerText: { flex: 1 },
  title: { color: colors.ink, fontSize: 16, fontWeight: "800" },
  status: { color: colors.muted, fontSize: 13, lineHeight: 18, marginTop: 2 },
  statusWarning: { color: colors.danger, fontSize: 13, lineHeight: 18, fontWeight: "700" },
  body: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  line: { color: colors.muted, fontSize: 12, fontWeight: "700", marginTop: 4 },
});
