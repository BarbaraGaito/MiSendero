import { router, useFocusEffect } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { initDB } from "../../database/database";
import { getSessions } from "../../database/sessionsRepository";
import { SessionRow } from "../../types";
import {
  AppScreen,
  Card,
  Metric,
  PrimaryButton,
  ScreenTitle,
  TopBar,
  colors,
} from "../components/MiSenderoUI";

const formatDuration = (seconds: number) => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainingSeconds = seconds % 60;

  if (hours > 0) return `${hours} h ${minutes.toString().padStart(2, "0")} min`;
  return `${minutes} min ${remainingSeconds} s`;
};

const formatDate = (timestamp: number) =>
  new Date(timestamp).toLocaleString("es-AR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });

const formatDistance = (meters: number) =>
  `${(meters / 1000).toLocaleString("es-AR", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  })} km`;

export default function HistoryScreen() {
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      await initDB();
      setSessions(await getSessions());
      setError(null);
    } catch {
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

  const totalDistance = sessions.reduce(
    (total, session) => total + (session.distance ?? 0),
    0
  );
  const completedCount = sessions.filter(
    (session) => session.completion_status === "completed"
  ).length;

  return (
    <AppScreen activeTab="actividad">
      <TopBar title="Historial local" onBack={() => router.back()} />
      <ScreenTitle
        eyebrow="Actividad"
        title="Historial"
        subtitle="Recorridos finalizados y guardados en este dispositivo."
      />

      <View style={styles.metricsRow}>
        <Metric label="Salidas" value={String(sessions.length)} />
        <Metric label="Completadas" value={String(completedCount)} />
        <Metric label="Total" value={formatDistance(totalDistance)} />
      </View>

      <ScrollView showsVerticalScrollIndicator={false}>
        {error ? <Text style={styles.statusText}>{error}</Text> : null}
        {isLoading ? <Text style={styles.statusText}>Cargando historial...</Text> : null}

        {!isLoading && sessions.length === 0 ? (
          <Card>
            <Text style={styles.emptyTitle}>Todavia no hay recorridos</Text>
            <Text style={styles.emptyText}>
              Inicia una ruta y al finalizarla aparecera aca con duracion,
              distancia y progreso alcanzado.
            </Text>
          </Card>
        ) : (
          sessions.map((session) => (
            <HistoryCard key={session.id} session={session} />
          ))
        )}

        <View style={styles.bottomAction}>
          <PrimaryButton
            label="Volver a mis actividades"
            icon="walk-outline"
            href="/mis-actividades"
            tone="secondary"
          />
        </View>
      </ScrollView>
    </AppScreen>
  );
}

function HistoryCard({ session }: { session: SessionRow }) {
  const endedEarly = session.completion_status === "ended_early";
  const status = endedEarly ? "Interrumpida" : "Completada";
  const progress =
    endedEarly && session.route_progress_meters !== null && session.route_total_meters
      ? `${Math.min(
          100,
          Math.round((session.route_progress_meters / session.route_total_meters) * 100)
        )}% del sendero`
      : session.completion_status === "completed"
        ? "Destino alcanzado"
        : "Guardada";

  return (
    <Card tone={endedEarly ? "green" : "white"}>
      <View style={styles.cardHeader}>
        <View style={styles.cardText}>
          <Text style={styles.date}>{formatDate(session.started_at)}</Text>
          <Text style={styles.meta}>
            {formatDuration(session.duration ?? 0)} - {formatDistance(session.distance ?? 0)}
          </Text>
        </View>
        <Text style={[styles.status, endedEarly && styles.statusEndedEarly]}>
          {status}
        </Text>
      </View>

      <View style={styles.detailRow}>
        <Text style={styles.detailLabel}>Progreso</Text>
        <Text style={styles.detailValue}>{progress}</Text>
      </View>
      <View style={styles.detailRow}>
        <Text style={styles.detailLabel}>Fatiga</Text>
        <Text style={styles.detailValue}>{session.avg_fatigue ?? "Sin estimación"}</Text>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  metricsRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 14,
  },
  statusText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 12,
  },
  emptyTitle: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "800",
  },
  emptyText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "600",
    lineHeight: 20,
    marginTop: 6,
  },
  cardHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
  },
  cardText: {
    flex: 1,
  },
  date: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "800",
  },
  meta: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "600",
    marginTop: 4,
  },
  status: {
    backgroundColor: colors.primarySoft,
    borderRadius: 999,
    color: colors.primary,
    fontSize: 12,
    fontWeight: "800",
    overflow: "hidden",
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  statusEndedEarly: {
    color: colors.greenDark,
  },
  detailRow: {
    alignItems: "center",
    borderTopColor: colors.border,
    borderTopWidth: 1,
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
    marginTop: 12,
    paddingTop: 12,
  },
  detailLabel: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "700",
  },
  detailValue: {
    color: colors.ink,
    flex: 1,
    fontSize: 13,
    fontWeight: "800",
    textAlign: "right",
    textTransform: "capitalize",
  },
  bottomAction: {
    marginTop: 8,
    paddingBottom: 18,
  },
});
