import { router, useLocalSearchParams } from "expo-router";
import React, { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import {
  AppScreen,
  Card,
  Metric,
  PrimaryButton,
  ScreenTitle,
  colors,
} from "../components/MiSenderoUI";
import { initDB } from "../../database/database";
import {
  attachTrailToSession,
  getLatestCompletedSession,
  getOrCreateCompletedSession,
  saveSessionReview,
} from "../../database/sessionsRepository";
import { enqueueUnique } from "../../services/syncQueue";
import { SessionRow } from "../../types";
import { getRouteTrackingSummary } from "../../services/routeTracking";

const ROUTE_COMPLETION_THRESHOLD = 0.95;

const formatDistance = (meters: number) =>
  `${(meters / 1000).toLocaleString("es-AR", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  })} km`;

const formatDuration = (seconds: number) => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (hours > 0) return `${hours}h ${minutes.toString().padStart(2, "0")}m`;
  return `${minutes}m`;
};

export default function RouteCompletedScreen() {
  const {
    id,
    startedAt,
    traveledMeters,
    routeProgressMeters,
    totalMeters,
    endedLatitude,
    endedLongitude,
  } = useLocalSearchParams<{
    id?: string;
    startedAt?: string;
    traveledMeters?: string;
    routeProgressMeters?: string;
    totalMeters?: string;
    endedLatitude?: string;
    endedLongitude?: string;
  }>();
  const [session, setSession] = useState<SessionRow | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [rating, setRating] = useState(0);
  const [reviewText, setReviewText] = useState("");
  const [reviewStatus, setReviewStatus] = useState<string | null>(null);
  const [isSavingReview, setIsSavingReview] = useState(false);
  const [completionStatus, setCompletionStatus] =
    useState<SessionRow["completion_status"]>("ended_early");
  const [trackingPointCount, setTrackingPointCount] = useState(0);

  useEffect(() => {
    const loadSession = async () => {
      await initDB();
      const trailId = Number(id);
      const startedAtMs = Number(startedAt);
      const distanceMeters = parseOptionalNumber(traveledMeters);
      const routeProgress = parseOptionalNumber(routeProgressMeters);
      const routeTotal = parseOptionalNumber(totalMeters);
      const endedLat = parseOptionalNumber(endedLatitude);
      const endedLng = parseOptionalNumber(endedLongitude);
      const endedAt = Date.now();
      let completedSession: SessionRow | null = null;

      if (trailId && startedAtMs) {
        const trackingSummary = await getRouteTrackingSummary(trailId, startedAtMs);
        setTrackingPointCount(trackingSummary.points);

        const safeDistance = Math.max(
          distanceMeters ?? 0,
          trackingSummary.distanceMeters
        );
        const safeRouteProgress =
          routeProgress ??
          (routeTotal && routeTotal > 0
            ? Math.min(safeDistance, routeTotal)
            : safeDistance);
        const safeRouteTotal = routeTotal ?? null;
        const safeEndedLatitude = endedLat ?? trackingSummary.lastPoint?.latitude ?? null;
        const safeEndedLongitude = endedLng ?? trackingSummary.lastPoint?.longitude ?? null;
        const nextCompletionStatus =
          safeRouteTotal && safeRouteTotal > 0 && safeRouteProgress >= safeRouteTotal * ROUTE_COMPLETION_THRESHOLD
            ? "completed"
            : "ended_early";
        const duration = Math.max(0, Math.floor((endedAt - startedAtMs) / 1000));

        const completedResult = await getOrCreateCompletedSession({
          trailId,
          startedAt: startedAtMs,
          endedAt,
          duration,
          distance: safeDistance,
          completionStatus: nextCompletionStatus,
          routeProgressMeters: safeRouteProgress,
          routeTotalMeters: safeRouteTotal,
          endedLatitude: safeEndedLatitude,
          endedLongitude: safeEndedLongitude,
        });
        completedSession = completedResult.session;
        setCompletionStatus(completedSession.completion_status);

        const clientSessionId = `local-session-${completedSession.id}`;
        const syncEndedAt = completedSession.ended_at ?? endedAt;
        const syncDuration = completedSession.duration ?? duration;
        const syncDistance = completedSession.distance ?? safeDistance;
        const syncRouteProgress =
          completedSession.route_progress_meters ?? safeRouteProgress;
        const syncRouteTotal = completedSession.route_total_meters ?? safeRouteTotal;

        await enqueueUnique("activity", {
          client_session_id: clientSessionId,
          trail_id: trailId,
          started_at: new Date(startedAtMs).toISOString(),
          ended_at: new Date(syncEndedAt).toISOString(),
          distance_km: Number((syncDistance / 1000).toFixed(2)),
          duration_minutes: Math.round(syncDuration / 60),
          completion_status: completedSession.completion_status,
          route_progress_meters: Math.round(syncRouteProgress),
          route_total_meters: syncRouteTotal ? Math.round(syncRouteTotal) : null,
          ended_latitude: completedSession.ended_latitude,
          ended_longitude: completedSession.ended_longitude,
        }, `activity:${clientSessionId}`);
      } else {
        setTrackingPointCount(0);
        completedSession = await getLatestCompletedSession();
        setCompletionStatus(completedSession?.completion_status ?? "ended_early");

        if (completedSession && trailId) {
          await attachTrailToSession(completedSession.id, trailId);
          completedSession = {
            ...completedSession,
            trail_id: completedSession.trail_id ?? trailId,
          };
        }
      }

      setSession(completedSession);
      setRating(completedSession?.rating ?? 0);
      setReviewText(completedSession?.review_text ?? "");
      setIsLoading(false);
    };

    loadSession();
  }, [endedLatitude, endedLongitude, id, routeProgressMeters, startedAt, totalMeters, traveledMeters]);

  const trailId = session?.trail_id ?? (Number(id) || null);
  const isPausedWithoutProgress = completionStatus === "paused";
  const isEndedEarly = completionStatus === "ended_early";
  const canReview = Boolean(session && trailId && !isPausedWithoutProgress);
  const hasReview = Boolean(session?.rating);
  const progressPercent =
    session?.route_progress_meters !== null &&
    session?.route_progress_meters !== undefined &&
    session?.route_total_meters
      ? Math.min(100, Math.round((session.route_progress_meters / session.route_total_meters) * 100))
      : null;

  const saveReview = async () => {
    if (!session || !trailId || rating < 1 || isSavingReview) return;

    setIsSavingReview(true);
    setReviewStatus(null);

    try {
      await saveSessionReview(session.id, trailId, rating, reviewText);
      setSession({
        ...session,
        trail_id: trailId,
        rating,
        review_text: reviewText.trim() || null,
        reviewed_at: Date.now(),
      });
      setReviewStatus("Gracias. Tu opinion quedo guardada en este sendero.");
    } catch (error) {
      setReviewStatus("No pudimos guardar tu opinion. Intentalo de nuevo.");
    } finally {
      setIsSavingReview(false);
    }
  };

  return (
    <AppScreen activeTab="actividad">
      <View style={styles.successIcon}>
        <Text style={styles.successCheck}>{isPausedWithoutProgress ? "||" : "OK"}</Text>
      </View>
      <ScreenTitle
        eyebrow={isPausedWithoutProgress ? "Ruta pausada" : "Recorrido finalizado"}
        title={
          isPausedWithoutProgress
            ? "Ruta en pausa"
            : isEndedEarly
              ? "Recorrido guardado"
              : "Sendero completado"
        }
        subtitle={
          isPausedWithoutProgress
            ? "No registramos distancia recorrida, asi que no la marcamos como terminada."
            : isEndedEarly
              ? "Guardamos tu actividad y el punto del sendero donde terminaste."
            : "Guardamos tu actividad con los datos registrados por la app."
        }
      />

      {isLoading ? <Text style={styles.statusText}>Cargando resumen...</Text> : null}

      {session ? (
        <>
          <View style={styles.metricsRow}>
            <Metric label="Distancia" value={formatDistance(session.distance ?? 0)} />
            <Metric label="Tiempo" value={formatDuration(session.duration ?? 0)} />
            <Metric
              label="Progreso"
              value={progressPercent !== null ? `${progressPercent}%` : "Guardado"}
            />
          </View>

          <Card tone="green">
            <Text style={styles.cardTitle}>
              {isPausedWithoutProgress
                ? "Actividad pendiente"
                : isEndedEarly
                  ? "Punto alcanzado"
                  : "Tu rendimiento"}
            </Text>
            <Text style={styles.cardText}>
              {isPausedWithoutProgress
                ? "La ruta quedo guardada en pausa. Podes continuarla desde Actividad o volver al mapa ahora."
                : isEndedEarly
                  ? getEndedEarlyText(session)
                : "La actividad quedo guardada localmente y ya esta disponible en tus actividades recientes."}
            </Text>
            {trackingPointCount > 0 ? (
              <Text style={styles.cardMeta}>
                {trackingPointCount} puntos GPS guardados para validar distancia y recorrido.
              </Text>
            ) : null}
          </Card>

          {canReview ? (
            <Card>
              <Text style={styles.cardTitle}>
                {hasReview ? "Opinion guardada" : "Como estuvo el sendero?"}
              </Text>
              <Text style={styles.cardText}>
                {hasReview
                  ? "Esta calificacion ya se usa en el promedio real del sendero."
                  : "Deja una calificacion real para que aparezca en el detalle del sendero."}
              </Text>

              <View style={styles.starsRow}>
                {[1, 2, 3, 4, 5].map((value) => (
                  <Pressable
                    key={value}
                    disabled={hasReview}
                    onPress={() => setRating(value)}
                    style={styles.starButton}
                  >
                    <Text
                      style={[
                        styles.starText,
                        value <= rating ? styles.starTextActive : null,
                      ]}
                    >
                      ★
                    </Text>
                  </Pressable>
                ))}
              </View>

              {!hasReview ? (
                <>
                  <TextInput
                    multiline
                    value={reviewText}
                    onChangeText={setReviewText}
                    placeholder="Comentario opcional"
                    placeholderTextColor={colors.muted}
                    style={styles.reviewInput}
                  />
                  <PrimaryButton
                    label={isSavingReview ? "Guardando..." : "Guardar opinion"}
                    onPress={saveReview}
                    tone={rating > 0 ? "green" : "secondary"}
                  />
                </>
              ) : null}

              {reviewStatus ? (
                <Text style={styles.reviewStatus}>{reviewStatus}</Text>
              ) : null}
            </Card>
          ) : null}
        </>
      ) : (
        <Card>
          <Text style={styles.cardTitle}>No hay actividad finalizada</Text>
          <Text style={styles.cardText}>
            Todavia no encontramos una sesion guardada para mostrar en este
            resumen.
          </Text>
        </Card>
      )}

      {isPausedWithoutProgress && trailId && session ? (
        <PrimaryButton
          label="Continuar ruta"
          icon="play-outline"
          onPress={() =>
            router.push({
              pathname: "/route-map",
              params: {
                active: "1",
                id: String(trailId),
                startedAt: String(session.started_at),
              },
            })
          }
        />
      ) : null}

      <PrimaryButton
        label={isPausedWithoutProgress ? "Ver actividades" : "Explorar otra ruta"}
        tone={isPausedWithoutProgress ? "secondary" : "green"}
        onPress={() => router.push(isPausedWithoutProgress ? "/mis-actividades" : "/explorar-rutas")}
      />
    </AppScreen>
  );
}

function parseOptionalNumber(value: string | undefined) {
  const numberValue = Number(value);

  return Number.isFinite(numberValue) ? numberValue : null;
}

function getEndedEarlyText(session: SessionRow) {
  if (session.route_progress_meters !== null && session.route_total_meters) {
    return `Terminaste en ${formatDistance(session.route_progress_meters)} de ${formatDistance(session.route_total_meters)} del sendero. La salida queda finalizada, no pausada.`;
  }

  if (session.ended_latitude !== null && session.ended_longitude !== null) {
    return `Terminaste cerca de ${session.ended_latitude.toFixed(5)}, ${session.ended_longitude.toFixed(5)}. La salida queda finalizada, no pausada.`;
  }

  return "La salida queda finalizada, no pausada, aunque no tengamos el punto exacto del sendero.";
}

const styles = StyleSheet.create({
  successIcon: {
    alignItems: "center",
    alignSelf: "center",
    backgroundColor: colors.successSoft,
    borderRadius: 999,
    height: 72,
    justifyContent: "center",
    marginBottom: 18,
    width: 72,
  },
  successCheck: {
    color: colors.primary,
    fontSize: 18,
    fontWeight: "900",
  },
  statusText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 14,
  },
  metricsRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 14,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "800",
  },
  cardText: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
    marginTop: 6,
  },
  cardMeta: {
    color: colors.greenDark,
    fontSize: 12,
    fontWeight: "800",
    lineHeight: 17,
    marginTop: 10,
  },
  reviewInput: {
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    color: colors.ink,
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 12,
    minHeight: 86,
    paddingHorizontal: 14,
    paddingVertical: 12,
    textAlignVertical: "top",
  },
  reviewStatus: {
    color: colors.greenDark,
    fontSize: 13,
    fontWeight: "800",
    marginTop: 10,
  },
  starButton: {
    alignItems: "center",
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  starsRow: {
    flexDirection: "row",
    gap: 2,
    marginVertical: 12,
  },
  starText: {
    color: colors.border,
    fontSize: 31,
    lineHeight: 35,
  },
  starTextActive: {
    color: colors.warning,
  },
});
