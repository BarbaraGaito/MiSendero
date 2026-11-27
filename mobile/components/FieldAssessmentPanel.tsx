import { useCallback, useEffect, useRef, useState } from "react";
import { AppState, Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { getFieldSnapshot, saveBorgCheckin, evaluateMorningAms, type FieldSnapshot } from "../../services/fieldAssessments";
import { getCurrentDeviceLocation } from "../../services/deviceLocation";
import { getSessionEpoch, subscribeSessionEpoch } from "../../services/sessionEpoch";
import type { FieldPrediction } from "../../ai/fieldInference";
import { useScreenFocused } from "../hooks/useScreenFocused";
import { colors } from "./MiSenderoUI";

export function FieldAssessmentPanel({ trailId, startedAt = 0, simulated = false, morning = false, compact = false }: {
  trailId: number; startedAt?: number; simulated?: boolean; morning?: boolean; compact?: boolean;
}) {
  const focused = useScreenFocused();
  const [snapshot, setSnapshot] = useState<FieldSnapshot | null>(null);
  const [open, setOpen] = useState(false);
  const [borg, setBorg] = useState<number | null>(null);
  const [confirmations, setConfirmations] = useState([false, false, false]);
  const [ams, setAms] = useState<FieldPrediction | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [snoozedUntil, setSnoozedUntil] = useState(0);
  const generation = useRef(0);
  const refresh = useCallback(async () => {
    const request = ++generation.current;
    const epoch = getSessionEpoch();
    try {
      const next = await getFieldSnapshot(trailId, startedAt);
      if (request === generation.current && epoch === getSessionEpoch()) setSnapshot(next);
    } catch {
      if (request === generation.current) setSnapshot(null);
    }
  }, [trailId, startedAt]);

  useEffect(() => {
    const clear = () => {
      generation.current++;
      setSnapshot(null); setAms(null); setOpen(false); setBorg(null); setError(null); setBusy(false);
      setConfirmations([false, false, false]); setSnoozedUntil(0);
    };
    clear();
    const unsubscribe = subscribeSessionEpoch(clear);
    if (simulated || !focused) return unsubscribe;
    void refresh();
    const interval = setInterval(() => { if (AppState.currentState === "active") void refresh(); }, 60000);
    const listener = AppState.addEventListener("change", state => {
      if (state === "active") void refresh();
      else clear();
    });
    return () => { generation.current++; clearInterval(interval); listener.remove(); unsubscribe(); };
  }, [focused, simulated, refresh]);

  if (simulated || !snapshot?.enabled) return null;
  const latest = snapshot.checkins[0];
  const result = snapshot.fatigue;
  const reminder = snapshot.reminderDue && Date.now() >= snoozedUntil;
  const operation = async (action: () => Promise<void>) => {
    const epoch = getSessionEpoch();
    setBusy(true); setError(null);
    try { await action(); }
    catch (cause) { if (epoch === getSessionEpoch()) setError(cause instanceof Error ? cause.message : "No pudimos completar el control."); }
    finally { if (epoch === getSessionEpoch()) setBusy(false); }
  };
  const save = () => operation(async () => {
    if (borg === null) return;
    const epoch = getSessionEpoch();
    await saveBorgCheckin(trailId, startedAt, borg);
    if (epoch !== getSessionEpoch()) return;
    setOpen(false); setBorg(null); await refresh();
  });
  const control = () => operation(async () => {
    const epoch = getSessionEpoch();
    const location = await getCurrentDeviceLocation();
    if (epoch !== getSessionEpoch()) return;
    const next = await evaluateMorningAms({ trailId, startedAt, location, restedOvernight: confirmations[0], restingNow: confirmations[1], beforeAscent: confirmations[2] });
    if (epoch === getSessionEpoch()) setAms(next);
  });
  const action = (label: string, onPress: () => void, disabled = false) => (
    <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={[styles.button, disabled && styles.disabled]}>
      <Text style={styles.buttonText}>{label}</Text>
    </Pressable>
  );
  return (
    <View style={[styles.panel, compact && styles.compact]}>
      {startedAt > 0 && <>
        <Text style={styles.title}>Esfuerzo personal</Text>
        <Text style={styles.body}>{latest ? `Declarado: ${latest.borg}/10` : "Todavía no registraste tu esfuerzo."}
          {result.status === "available" ? ` · Estimado: ${result.value}/10` : " · Estimación pendiente"}</Text>
        {!compact && <Text style={styles.body}>{result.status === "available" ? "Estimación orientativa a partir de pulso y esfuerzo declarado antes de este minuto." : result.reason}</Text>}
        {reminder && <Text style={styles.body}>Si querés, registrá cómo te sentís. Es opcional.</Text>}
        <View style={styles.row}>
          {action("Registrar esfuerzo", () => { setBorg(null); setOpen(true); })}
          {reminder && action("Más tarde", () => setSnoozedUntil(Date.now()+600000))}
        </View>
      </>}
      {morning && <>
        <Text style={styles.title}>Control matutino de altura</Text>
        <Text style={styles.body}>Para la próxima etapa de ascenso: entre las 5 y las 12, después de descansar durante la noche y antes de continuar.</Text>
        {["Descansé durante la noche", "Estoy en reposo ahora", "Todavía no inicié el próximo ascenso"].map((label, index) => (
          <Pressable key={label} accessibilityRole="checkbox" accessibilityLabel={label} accessibilityState={{ checked: confirmations[index] }} onPress={() => { setAms(null); setConfirmations(values => values.map((value, i) => i === index ? !value : value)); }} style={styles.check}>
            <Text style={styles.body}>{confirmations[index] ? "☑" : "☐"} {label}</Text>
          </Pressable>
        ))}
        {action(busy ? "Leyendo mediciones…" : "Realizar control", () => void control(), busy || !confirmations.every(Boolean))}
        {ams && <Text accessibilityLiveRegion="polite" style={styles.body}>{ams.status === "available"
          ? `Puntuación orientativa: ${ams.score!.toFixed(2)} (escala de 0 a 1). ${ams.reason} No es una probabilidad personal validada ni un diagnóstico.`
          : ams.reason}</Text>}
        <Text style={styles.body}>Este control no determina si es seguro ascender ni activa SOS.</Text>
      </>}
      {error && <Text accessibilityLiveRegion="polite" style={styles.error}>{error}</Text>}
      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <View style={styles.overlay}><ScrollView contentContainerStyle={styles.dialog}>
          <Text style={styles.title}>¿Cuánto esfuerzo sentís ahora?</Text>
          <Text style={styles.body}>Escala Borg de 0 a 10: 0 = ninguno, 10 = máximo. Guardamos tu respuesta tal como la indicás.</Text>
          <View style={styles.row}>{Array.from({ length: 11 }, (_, value) => (
            <Pressable key={value} accessibilityRole="radio" accessibilityLabel={`Borg ${value}`} accessibilityState={{ selected: borg === value }} onPress={() => setBorg(value)} style={[styles.choice, borg === value && styles.selected]}>
              <Text style={styles.body}>{value}</Text>
            </Pressable>
          ))}</View>
          {error && <Text style={styles.error}>{error}</Text>}
          {action(busy ? "Guardando…" : "Guardar esfuerzo", () => void save(), busy || borg === null)}
          {action("Cancelar", () => setOpen(false), busy)}
        </ScrollView></View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { backgroundColor: colors.white, borderColor: colors.line, borderWidth: 1, borderRadius: 18, padding: 16, gap: 8 },
  compact: { padding: 10 }, title: { color: colors.ink, fontSize: 17, fontWeight: "700" },
  body: { color: colors.muted, fontSize: 14, lineHeight: 20 }, row: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  button: { backgroundColor: colors.soft, borderRadius: 12, padding: 12, minHeight: 44, alignItems: "center" },
  buttonText: { color: colors.green, fontWeight: "600" }, disabled: { opacity: .5 },
  check: { minHeight: 44, justifyContent: "center" }, choice: { padding: 14, borderWidth: 1, borderColor: colors.line, borderRadius: 10 },
  selected: { backgroundColor: colors.mint, borderColor: colors.green }, error: { color: colors.danger },
  overlay: { flex: 1, backgroundColor: "rgba(0,0,0,.5)", justifyContent: "center", padding: 24 },
  dialog: { backgroundColor: colors.white, padding: 24, gap: 16, borderRadius: 20 },
});
