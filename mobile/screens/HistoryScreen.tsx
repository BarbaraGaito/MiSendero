import { useFocusEffect } from "expo-router";
import React, { useCallback, useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { initDB } from "../../database/database";
import { getSessions } from "../../database/sessionsRepository";
import { SessionRow } from "../../types";

const formatDuration = (seconds: number) => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainingSeconds = seconds % 60;

  if (hours > 0) return `${hours}h ${minutes.toString().padStart(2, "0")}m`;
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
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      await initDB();
      setSessions(await getSessions());
      setError(null);
    } catch (loadError) {
      setError("No pudimos cargar el historial local.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  return (
    <SafeAreaView edges={["top", "bottom"]} style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title}>Historial</Text>
        <Text style={styles.subtitle}>
          Sesiones guardadas localmente en el dispositivo
        </Text>

        {error ? <Text style={styles.statusText}>{error}</Text> : null}
        {isLoading ? <Text style={styles.statusText}>Cargando historial...</Text> : null}

        {!isLoading && sessions.length === 0 ? (
          <View style={styles.emptyCard}>
            <Text style={styles.emptyTitle}>Todavia no hay recorridos</Text>
            <Text style={styles.emptyText}>
              Inicia un trekking y al detenerlo aparecera aca con duracion,
              distancia y fatiga promedio.
            </Text>
          </View>
        ) : (
          sessions.map((session) => (
            <View key={session.id} style={styles.sessionCard}>
              <Text style={styles.date}>{formatDate(session.started_at)}</Text>
              <View style={styles.row}>
                <HistoryMetric
                  label="Duracion"
                  value={formatDuration(session.duration ?? 0)}
                />
                <HistoryMetric
                  label="Distancia"
                  value={`${((session.distance ?? 0) / 1000).toFixed(2)} km`}
                />
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
    gap: 14,
    padding: 20,
    paddingBottom: 28,
  },
  title: { color: "#F6FFF8", fontSize: 28, fontWeight: "800" },
  subtitle: { color: "#A7B8AE", marginBottom: 4 },
  statusText: { color: "#A7B8AE", fontWeight: "700" },
  emptyCard: {
    backgroundColor: "#121A16",
    borderColor: "#223128",
    borderRadius: 20,
    borderWidth: 1,
    gap: 6,
    padding: 18,
  },
  emptyTitle: { color: "#F6FFF8", fontSize: 16, fontWeight: "700" },
  emptyText: { color: "#A7B8AE", lineHeight: 20 },
  sessionCard: {
    backgroundColor: "#121A16",
    borderColor: "#223128",
    borderRadius: 20,
    borderWidth: 1,
    gap: 12,
    padding: 16,
  },
  date: { color: "#64D38C", fontWeight: "700" },
  row: { flexDirection: "row", gap: 10 },
  metric: { flex: 1 },
  metricLabel: { color: "#8FA395", fontSize: 12 },
  metricValue: {
    color: "#F6FFF8",
    fontWeight: "700",
    marginTop: 4,
    textTransform: "capitalize",
  },
});
