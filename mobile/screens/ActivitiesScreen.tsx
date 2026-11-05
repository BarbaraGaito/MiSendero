import { router, useFocusEffect } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import {
  AppScreen,
  Card,
  Metric,
  PrimaryButton,
  ScreenTitle,
  colors,
} from "../components/MiSenderoUI";
import {
  getRecentSessions,
  getSessionsSummary,
  SessionsSummary,
} from "../../database/sessionsRepository";
import { initDB } from "../../database/database";
import { SessionRow } from "../../types";
import { formatKilometers } from "../../services/geoUtils";

const emptySummary: SessionsSummary = {
  totalDistance: 0,
  completedCount: 0,
  currentMonthCount: 0,
};

const formatDistance = (meters: number) => formatKilometers(meters / 1000);

const formatDuration = (seconds: number) => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (hours > 0) return `${hours} h ${minutes.toString().padStart(2, "0")} min`;
  return `${minutes} min`;
};

const formatDate = (timestamp: number) =>
  new Date(timestamp).toLocaleDateString("es-AR", {
    day: "2-digit",
    month: "short",
  });

export default function ActivitiesScreen() {
  const [summary, setSummary] = useState<SessionsSummary>(emptySummary);
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadActivities = useCallback(async () => {
    try {
      await initDB();

      const [nextSummary, recentSessions] = await Promise.all([
        getSessionsSummary(),
        getRecentSessions(8),
      ]);

      setSummary(nextSummary);
      setSessions(recentSessions);
      setError(null);
    } catch {
      setError("No pudimos cargar tus actividades.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadActivities();
  }, [loadActivities]);

  useFocusEffect(
    useCallback(() => {
      loadActivities();
    }, [loadActivities])
  );

  return (
    <AppScreen activeTab="actividad">
      <ScreenTitle
        eyebrow="Actividad"
        title="Mis actividades"
        subtitle="Resumen de tus recorridos guardados y pendientes."
      />

      <View style={styles.metricsRow}>
        <Metric label="Total" value={formatDistance(summary.totalDistance)} />
        <Metric label="Rutas" value={String(summary.completedCount)} />
        <Metric label="Este mes" value={String(summary.currentMonthCount)} />
      </View>

      <ScrollView showsVerticalScrollIndicator={false}>
        {error ? <Text style={styles.statusText}>{error}</Text> : null}
        {isLoading ? <Text style={styles.statusText}>Cargando actividades...</Text> : null}

        {!isLoading && sessions.length === 0 ? (
          <Card>
            <Text style={styles.emptyTitle}>Todavia no hay recorridos</Text>
            <Text style={styles.emptyText}>
              Cuando inicies y guardes una salida, va a aparecer aca con distancia,
              tiempo y estado real.
            </Text>
          </Card>
        ) : (
          sessions.map((session) => (
            <ActivityCard key={session.id} session={session} />
          ))
        )}

        <View style={styles.historyAction}>
          <PrimaryButton
            label="Ver historial local"
            icon="time-outline"
            href="/history"
            tone="secondary"
          />
        </View>
      </ScrollView>
    </AppScreen>
  );
}

function ActivityCard({ session }: { session: SessionRow }) {
  const pending = session.ended_at === null;
  const endedEarly = !pending && session.completion_status === "ended_early";
  const distance = formatDistance(session.distance ?? 0);
  const duration = pending ? "En curso" : formatDuration(session.duration ?? 0);
  const status = pending ? "Pendiente" : endedEarly ? "Interrumpida" : "Completada";
  const progress =
    endedEarly && session.route_progress_meters !== null && session.route_total_meters
      ? ` - ${Math.min(
          100,
          Math.round((session.route_progress_meters / session.route_total_meters) * 100)
        )}% del sendero`
      : "";

  return (
    <Card tone={endedEarly ? "green" : "white"}>
      <View style={styles.activityTop}>
        <View style={styles.activityText}>
          <Text style={styles.activityTitle}>
            Recorrido del {formatDate(session.started_at)}
          </Text>
          <Text style={styles.activityMeta}>
            {duration} - {distance}{progress} - Fatiga {session.avg_fatigue ?? "sin estimación"}
          </Text>
        </View>
        <Text
          style={[
            styles.status,
            pending && styles.statusPending,
            endedEarly && styles.statusEndedEarly,
          ]}
        >
          {status}
        </Text>
      </View>
      {pending && session.trail_id ? (
        <View style={styles.resumeAction}>
          <PrimaryButton
            label="Continuar ruta"
            icon="play-outline"
            onPress={() =>
              router.push({
                pathname: "/route-map",
                params: {
                  active: "1",
                  id: String(session.trail_id),
                  startedAt: String(session.started_at),
                },
              })
            }
          />
        </View>
      ) : null}
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
  activityTop: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
  },
  activityText: {
    flex: 1,
  },
  activityTitle: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "800",
  },
  activityMeta: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "600",
    marginTop: 4,
    textTransform: "capitalize",
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
  statusPending: {
    backgroundColor: colors.sky,
    color: colors.primary,
  },
  statusEndedEarly: {
    backgroundColor: colors.primarySoft,
    color: colors.greenDark,
  },
  resumeAction: {
    marginTop: 12,
  },
  historyAction: {
    marginTop: 8,
    paddingBottom: 18,
  },
});
