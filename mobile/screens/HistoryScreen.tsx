import React, { useCallback, useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { getSessions } from "../../database/sessionsRepository";
import { SessionRow } from "../../types";

const formatDuration = (seconds: number) => {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds}s`;
};

const formatDate = (timestamp: number) =>
  new Date(timestamp).toLocaleString("es-AR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });

export default function HistoryScreen() {
  const [sessions, setSessions] = useState<SessionRow[]>([]);

  const load = async () => {
    setSessions(await getSessions());
  };

  useEffect(() => {
    load();
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [])
  );

  return (
    <SafeAreaView edges={["top", "bottom"]} style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Historial</Text>
      <Text style={styles.subtitle}>Sesiones guardadas localmente en el dispositivo</Text>

      {sessions.length === 0 ? (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyTitle}>Todavía no hay recorridos</Text>
          <Text style={styles.emptyText}>
            Iniciá un trekking y al detenerlo aparecerá acá con duración, distancia y fatiga promedio.
          </Text>
        </View>
      ) : (
        sessions.map((session) => (
          <View key={session.id} style={styles.sessionCard}>
            <Text style={styles.date}>{formatDate(session.started_at)}</Text>
            <View style={styles.row}>
              <HistoryMetric label="Duración" value={formatDuration(session.duration)} />
              <HistoryMetric label="Distancia" value={`${(session.distance / 1000).toFixed(2)} km`} />
              <HistoryMetric label="Fatiga" value={session.avg_fatigue} />
            </View>
          </View>
        ))
      )}
      </ScrollView>
    </SafeAreaView>
  );
}

const HistoryMetric = ({ label, value }: { label: string; value: string }) => (
  <View style={styles.metric}>
    <Text style={styles.metricLabel}>{label}</Text>
    <Text style={styles.metricValue}>{value}</Text>
  </View>
);

const styles = StyleSheet.create({
  safeArea: {
    backgroundColor: "#0B110E",
    flex: 1,
  },
  container: {
    backgroundColor: "#0B110E",
    flexGrow: 1,
    padding: 20,
    paddingBottom: 28,
    gap: 14,
  },
  title: { color: "#F6FFF8", fontSize: 28, fontWeight: "800" },
  subtitle: { color: "#A7B8AE", marginBottom: 4 },
  emptyCard: {
    backgroundColor: "#121A16",
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "#223128",
    padding: 18,
    gap: 6,
  },
  emptyTitle: { color: "#F6FFF8", fontWeight: "700", fontSize: 16 },
  emptyText: { color: "#A7B8AE", lineHeight: 20 },
  sessionCard: {
    backgroundColor: "#121A16",
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "#223128",
    padding: 16,
    gap: 12,
  },
  date: { color: "#64D38C", fontWeight: "700" },
  row: { flexDirection: "row", gap: 10 },
  metric: { flex: 1 },
  metricLabel: { color: "#8FA395", fontSize: 12 },
  metricValue: { color: "#F6FFF8", fontWeight: "700", marginTop: 4, textTransform: "capitalize" },
});
