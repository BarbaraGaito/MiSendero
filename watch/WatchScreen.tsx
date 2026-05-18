import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { FatigueLevel } from "../types";

interface Props {
  hr: number;
  fatigue: FatigueLevel;
  elapsedSeconds: number;
  inactiveTooLong: boolean;
  isActive: boolean;
  onStart: () => void;
  onStop: () => void;
}

const fatigueColors: Record<FatigueLevel, string> = {
  bajo: "#64D38C",
  medio: "#F4C95D",
  alto: "#FF6B6B",
};

const formatTime = (seconds: number) => {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const remainingSeconds = (seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainingSeconds}`;
};

export default function WatchScreen({
  hr,
  fatigue,
  elapsedSeconds,
  inactiveTooLong,
  isActive,
  onStart,
  onStop,
}: Props) {
  return (
    <View style={styles.watchShell}>
      <View style={styles.header}>
        <Text style={styles.brand}>MiSendero</Text>
        <View style={[styles.statusDot, isActive && styles.statusDotActive]} />
      </View>

      <Text style={styles.heartRate}>{hr || "--"}</Text>
      <Text style={styles.heartRateLabel}>BPM</Text>

      <View style={styles.metricsRow}>
        <Metric label="Tiempo" value={formatTime(elapsedSeconds)} />
        <Metric label="Fatiga" value={fatigue.toUpperCase()} accent={fatigueColors[fatigue]} />
      </View>

      <View style={styles.alertArea}>
        {fatigue === "alto" && <Text style={styles.alert}>⚠ Fatiga alta</Text>}
        {inactiveTooLong && <Text style={styles.alert}>⏸ Detenido mucho tiempo</Text>}
      </View>

      <View style={styles.actions}>
        <Pressable
          style={[styles.button, styles.primaryButton, isActive && styles.disabledButton]}
          onPress={onStart}
          disabled={isActive}
        >
          <Text style={styles.buttonText}>Iniciar</Text>
        </Pressable>

        <Pressable
          style={[styles.button, styles.secondaryButton, !isActive && styles.disabledButton]}
          onPress={onStop}
          disabled={!isActive}
        >
          <Text style={styles.buttonText}>Detener</Text>
        </Pressable>
      </View>

      <Pressable style={styles.sosButton} onPress={() => alert("SOS enviado")}>
        <Text style={styles.sosText}>SOS</Text>
      </Pressable>
    </View>
  );
}

const Metric = ({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) => (
  <View style={styles.metricCard}>
    <Text style={styles.metricLabel}>{label}</Text>
    <Text style={[styles.metricValue, accent ? { color: accent } : null]}>{value}</Text>
  </View>
);

const styles = StyleSheet.create({
  watchShell: {
    backgroundColor: "#101714",
    borderRadius: 32,
    padding: 20,
    width: "100%",
    minHeight: 360,
    borderWidth: 1,
    borderColor: "#233128",
  },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  brand: { color: "#E8F1EA", fontWeight: "700", fontSize: 18 },
  statusDot: { width: 10, height: 10, borderRadius: 10, backgroundColor: "#546157" },
  statusDotActive: { backgroundColor: "#64D38C" },
  heartRate: {
    color: "#F6FFF8",
    fontSize: 72,
    fontWeight: "800",
    textAlign: "center",
    marginTop: 18,
  },
  heartRateLabel: { color: "#8FA395", textAlign: "center", marginTop: -8 },
  metricsRow: { flexDirection: "row", gap: 10, marginTop: 18 },
  metricCard: {
    flex: 1,
    backgroundColor: "#17211C",
    borderRadius: 18,
    padding: 12,
  },
  metricLabel: { color: "#8FA395", fontSize: 12 },
  metricValue: { color: "#F6FFF8", fontSize: 18, fontWeight: "700", marginTop: 4 },
  alertArea: { minHeight: 46, justifyContent: "center", gap: 4, marginTop: 10 },
  alert: { color: "#FF8D8D", fontWeight: "600" },
  actions: { flexDirection: "row", gap: 10, marginTop: 8 },
  button: { flex: 1, paddingVertical: 12, borderRadius: 16, alignItems: "center" },
  primaryButton: { backgroundColor: "#2C8F5A" },
  secondaryButton: { backgroundColor: "#37443C" },
  disabledButton: { opacity: 0.45 },
  buttonText: { color: "#F6FFF8", fontWeight: "700" },
  sosButton: {
    marginTop: 12,
    borderRadius: 16,
    backgroundColor: "#8E2C2C",
    paddingVertical: 12,
    alignItems: "center",
  },
  sosText: { color: "#FFF3F3", fontWeight: "800", letterSpacing: 1 },
});
