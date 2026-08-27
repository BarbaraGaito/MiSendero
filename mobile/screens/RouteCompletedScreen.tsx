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
  getOrCreatePausedSession,
  saveSessionReview,
} from "../../database/sessionsRepository";
import { SessionRow } from "../../types";

const MIN_COMPLETED_DISTANCE_METERS = 10;

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

const getRouteCompletionSession = async ({
  id,
  startedAt,
  traveledMeters,
}: {
  id?: string;
  startedAt?: string;
  traveledMeters?: string;
}) => {
  const trailId = Number(id);
  const startedAtMs = Number(startedAt);
  const distanceMeters = Number(traveledMeters);
  const endedAt = Date.now();

  if (!trailId || !startedAtMs) {
    const latestSession = await getLatestCompletedSession();
    if (latestSession && trailId) {
      await attachTrailToSession(latestSession.id, trailId);
      return {
        session: {
          ...latestSession,
          trail_id: latestSession.trail_id ?? trailId,
        },
        isPausedWithoutProgress: false,
      };
    }

    return { session: latestSession, isPausedWithoutProgress: false };
  }

  const safeDistance = Number.isFinite(distanceMeters) ? distanceMeters : 0;
  const duration = Math.max(0, Math.floor((endedAt - startedAtMs) / 1000));

  if (safeDistance < MIN_COMPLETED_DISTANCE_METERS) {
    return {
      session: await getOrCreatePausedSession({
        trailId,
        startedAt: startedAtMs,
        duration,
        distance: safeDistance,
      }),
      isPausedWithoutProgress: true,
    };
  }

  return {
    session: await getOrCreateCompletedSession({
      trailId,
      startedAt: startedAtMs,
      endedAt,
      duration,
      distance: safeDistance,
    }),
    isPausedWithoutProgress: false,
  };
};

const getCompletionCopy = (isPausedWithoutProgress: boolean) => ({
  icon: isPausedWithoutProgress ? "||" : "OK",
  eyebrow: isPausedWithoutProgress ? "Ruta pausada" : "Recorrido finalizado",
  title: isPausedWithoutProgress ? "Ruta en pausa" : "Recorrido completado",
  subtitle: isPausedWithoutProgress
    ? "No registramos distancia recorrida, asi que no la marcamos como terminada."
    : "Guardamos tu actividad con los datos registrados por la app.",
  performanceTitle: isPausedWithoutProgress ? "Actividad pendiente" : "Tu rendimiento",
  performanceText: isPausedWithoutProgress
    ? "La ruta quedo guardada en pausa. Podes continuarla desde Actividad o volver al mapa ahora."
    : "La actividad quedo guardada localmente y ya esta disponible en tus actividades recientes.",
  finalActionLabel: isPausedWithoutProgress ? "Ver actividades" : "Explorar otra ruta",
  finalActionTone: isPausedWithoutProgress ? "secondary" as const : "green" as const,
  finalActionRoute: isPausedWithoutProgress ? "/mis-actividades" : "/explorar-rutas",
});

const getReviewCopy = (hasReview: boolean) => ({
  title: hasReview ? "Opinion guardada" : "Como estuvo el sendero?",
  text: hasReview
    ? "Esta calificacion ya se usa en el promedio real del sendero."
    : "Deja una calificacion real para que aparezca en el detalle del sendero.",
});

export default function RouteCompletedScreen() {
  const { id, startedAt, traveledMeters } = useLocalSearchParams<{
    id?: string;
    startedAt?: string;
    traveledMeters?: string;
  }>();
  const [session, setSession] = useState<SessionRow | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [rating, setRating] = useState(0);
  const [reviewText, setReviewText] = useState("");
  const [reviewStatus, setReviewStatus] = useState<string | null>(null);
  const [isSavingReview, setIsSavingReview] = useState(false);
  const [isPausedWithoutProgress, setIsPausedWithoutProgress] = useState(false);

  useEffect(() => {
    const loadSession = async () => {
      await initDB();
      const completion = await getRouteCompletionSession({ id, startedAt, traveledMeters });
      const completedSession = completion.session;

      setIsPausedWithoutProgress(completion.isPausedWithoutProgress);
      setSession(completedSession);
      setRating(completedSession?.rating ?? 0);
      setReviewText(completedSession?.review_text ?? "");
      setIsLoading(false);
    };

    loadSession();
  }, [id, startedAt, traveledMeters]);

  const trailId = session?.trail_id ?? (Number(id) || null);
  const canReview = Boolean(session && trailId && !isPausedWithoutProgress);
  const hasReview = Boolean(session?.rating);
  const completionCopy = getCompletionCopy(isPausedWithoutProgress);
  const reviewCopy = getReviewCopy(hasReview);

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
        <Text style={styles.successCheck}>{completionCopy.icon}</Text>
      </View>
      <ScreenTitle
        eyebrow={completionCopy.eyebrow}
        title={completionCopy.title}
        subtitle={completionCopy.subtitle}
      />

      {isLoading ? <Text style={styles.statusText}>Cargando resumen...</Text> : null}

      {session ? (
        <>
          <View style={styles.metricsRow}>
            <Metric label="Distancia" value={formatDistance(session.distance ?? 0)} />
            <Metric label="Tiempo" value={formatDuration(session.duration ?? 0)} />
            <Metric label="Fatiga" value={session.avg_fatigue} />
          </View>

          <Card tone="green">
            <Text style={styles.cardTitle}>{completionCopy.performanceTitle}</Text>
            <Text style={styles.cardText}>{completionCopy.performanceText}</Text>
          </Card>

          {canReview ? (
            <Card>
              <Text style={styles.cardTitle}>{reviewCopy.title}</Text>
              <Text style={styles.cardText}>{reviewCopy.text}</Text>

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
        label={completionCopy.finalActionLabel}
        tone={completionCopy.finalActionTone}
        onPress={() => router.push(completionCopy.finalActionRoute as any)}
      />
    </AppScreen>
  );
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
