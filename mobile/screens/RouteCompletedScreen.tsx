import { getRouteSession, finishRouteSession, activeRouteSeconds, getSimulatedRouteTrackingSummary } from "../../services/routeSession";
import { router, useLocalSearchParams } from "expo-router";
import type { Href } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Ionicons } from "@expo/vector-icons";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
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
import { SessionRow } from "../../types";
import { getRouteTrackingSummary } from "../../services/routeTracking";
import { formatKilometers } from "../../services/geoUtils";
import { CompletionContactRequiredError, sendRouteCompletionSms } from "../../services/completionMessages";
import { userMessage } from "../../services/userMessages";

const ROUTE_COMPLETION_THRESHOLD = 0.95;

const formatDistance = (meters: number) => formatKilometers(meters / 1000);

const formatDuration = (seconds: number) => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (hours > 0) return `${hours}h ${minutes.toString().padStart(2, "0")}m`;
  return `${minutes}m`;
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
  finalActionRoute: (isPausedWithoutProgress ? "/mis-actividades" : "/explorar-rutas") as Href,
});

const getReviewCopy = (hasReview: boolean) => ({
  title: hasReview ? "Opinion guardada" : "Como estuvo el sendero?",
  text: hasReview
    ? "Esta calificacion ya se usa en el promedio real del sendero."
    : "Deja una calificacion real para que aparezca en el detalle del sendero.",
});

type RouteCompletionParams = {
  id?: string;
  startedAt?: string;
  traveledMeters?: string;
  routeProgressMeters?: string;
  totalMeters?: string;
  endedLatitude?: string;
  endedLongitude?: string;
};

const getExistingCompletionSession = async (trailId: number) => {
  let completedSession = await getLatestCompletedSession();

  if (completedSession && trailId) {
    await attachTrailToSession(completedSession.id, trailId);
    completedSession = {
      ...completedSession,
      trail_id: completedSession.trail_id ?? trailId,
    };
  }

  return completedSession;
};

const createCompletionSession = async (params: RouteCompletionParams) => {
  const trailId = Number(params.id);
  const startedAtMs = Number(params.startedAt);

  if (!trailId || !startedAtMs) {
    return {
      session: await getExistingCompletionSession(trailId),
      trackingPointCount: 0,
      isSimulated: false,
    };
  }

  const activeRuntime = await getRouteSession(trailId, startedAtMs);
  const runtime = activeRuntime?.simulated ? await finishRouteSession(trailId, startedAtMs) : activeRuntime;
  const isSimulated = Boolean(runtime?.simulated);
  const endedAt = runtime?.ended_at ?? Date.now();
  const trackingSummary = isSimulated
    ? getSimulatedRouteTrackingSummary(trailId, startedAtMs)
    : await getRouteTrackingSummary(trailId, startedAtMs);
  const routeTotal = parseOptionalNumber(params.totalMeters);
  const distance = Math.max(
    parseOptionalNumber(params.traveledMeters) ?? 0,
    trackingSummary.distanceMeters
  );
  const routeProgressMeters = getRouteProgressValue(
    parseOptionalNumber(params.routeProgressMeters),
    routeTotal,
    distance
  );
  const duration = runtime ? activeRouteSeconds(runtime) : Math.max(0, Math.floor((endedAt - startedAtMs) / 1000));
  const completionStatus = getCompletionStatus(routeProgressMeters, routeTotal);
  const endedLatitude =
    parseOptionalNumber(params.endedLatitude) ??
    trackingSummary.lastPoint?.latitude ??
    null;
  const endedLongitude =
    parseOptionalNumber(params.endedLongitude) ??
    trackingSummary.lastPoint?.longitude ??
    null;

  if (isSimulated) {
    // Testing mode: show the simulated run, but never store it as an activity or queue it for sync.
    const simulatedSession: SessionRow = {
      id: 0,
      user_id: runtime?.user_id ?? null,
      started_at: startedAtMs,
      ended_at: endedAt,
      duration,
      distance,
      avg_fatigue: null,
      trail_id: trailId,
      completion_status: completionStatus,
      route_progress_meters: routeProgressMeters,
      route_total_meters: routeTotal,
      ended_latitude: endedLatitude,
      ended_longitude: endedLongitude,
      rating: null,
      review_text: null,
      reviewed_at: null,
    };

    return { session: simulatedSession, trackingPointCount: trackingSummary.points, isSimulated };
  }

  const completedResult = await getOrCreateCompletedSession({
    trailId,
    startedAt: startedAtMs,
    endedAt,
    duration,
    distance,
    completionStatus,
    routeProgressMeters,
    routeTotalMeters: routeTotal,
    endedLatitude,
    endedLongitude,
  });

  await finishRouteSession(trailId, startedAtMs);

  return {
    session: completedResult.session,
    trackingPointCount: trackingSummary.points,
    isSimulated,
  };
};

const getRouteProgressValue = (
  routeProgress: number | null,
  routeTotal: number | null,
  distance: number
) => routeProgress ?? (routeTotal && routeTotal > 0 ? Math.min(distance, routeTotal) : distance);

const getCompletionStatus = (
  routeProgressMeters: number,
  routeTotalMeters: number | null
): Exclude<SessionRow["completion_status"], "paused"> =>
  routeTotalMeters && routeTotalMeters > 0 && routeProgressMeters >= routeTotalMeters * ROUTE_COMPLETION_THRESHOLD
    ? "completed"
    : "ended_early";

export default function RouteCompletedScreen() {
  const insets = useSafeAreaInsets();
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
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveAttempt, setSaveAttempt] = useState(0);
  const [rating, setRating] = useState(0);
  const [reviewText, setReviewText] = useState("");
  const [reviewStatus, setReviewStatus] = useState<string | null>(null);
  const [isSavingReview, setIsSavingReview] = useState(false);
  const [completionStatus, setCompletionStatus] =
    useState<SessionRow["completion_status"]>("ended_early");
  const [trackingPointCount, setTrackingPointCount] = useState(0);
  const [isSimulated, setIsSimulated] = useState(false);
  const [isPreparingSms, setIsPreparingSms] = useState(false);
  const [smsStatus, setSmsStatus] = useState<string | null>(null);
  const smsBusy = useRef(false);

  useEffect(() => {
    let mounted = true;
    setIsLoading(true);
    setSaveError(null);
    setSession(null);
    const loadSession = async () => {
      await initDB();
      const completion = await createCompletionSession({
        id,
        startedAt,
        traveledMeters,
        routeProgressMeters,
        totalMeters,
        endedLatitude,
        endedLongitude,
      });
      if (!mounted) return;
      const completedSession = completion.session;

      setTrackingPointCount(completion.trackingPointCount);
      setIsSimulated(completion.isSimulated);
      setCompletionStatus(completedSession?.completion_status ?? "ended_early");
      setSession(completedSession);
      setRating(completedSession?.rating ?? 0);
      setReviewText(completedSession?.review_text ?? "");
    };

    void loadSession().catch(() => {
      if (mounted) setSaveError("No pudimos guardar el recorrido. Reintentá para confirmar que tu actividad quedó guardada.");
    }).finally(() => { if (mounted) setIsLoading(false); });
    return () => { mounted = false; };
  }, [endedLatitude, endedLongitude, id, routeProgressMeters, startedAt, totalMeters, traveledMeters, saveAttempt]);

  const trailId = session?.trail_id ?? (Number(id) || null);
  const isPausedWithoutProgress = completionStatus === "paused";
  const isEndedEarly = completionStatus === "ended_early";
  const canReview = Boolean(session && trailId && !isPausedWithoutProgress && !isSimulated);
  const hasReview = Boolean(session?.rating);
  const completionCopy = getCompletionCopy(isPausedWithoutProgress);
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
    } catch {
      setReviewStatus("No pudimos guardar tu opinion. Intentalo de nuevo.");
    } finally {
      setIsSavingReview(false);
    }
  };

  const notifyContact = async () => {
    if (!session || !trailId || isLoading || isSimulated || isPausedWithoutProgress || smsBusy.current) return;
    smsBusy.current = true;
    setIsPreparingSms(true);
    setSmsStatus(null);
    try {
      const result = await sendRouteCompletionSms({ trailId, startedAt: session.started_at, simulated: isSimulated });
      setSmsStatus(result.result === "sent"
        ? "El teléfono indicó que enviaste el SMS. Esto no confirma que tu contacto lo recibió."
        : result.result === "cancelled" ? "SMS cancelado. No se confirmó el envío a tu contacto."
          : "Se abrió Mensajes. Revisá allí el estado del SMS; MiSendero no puede confirmar su entrega.");
    } catch (error) {
      if (error instanceof CompletionContactRequiredError) router.push("/contacto-seguridad");
      else setSmsStatus(userMessage(error, "No pudimos preparar el SMS. Intentá nuevamente o avisá a tu contacto por otro medio."));
    } finally { smsBusy.current = false; setIsPreparingSms(false); }
  };

  return (
    <AppScreen activeTab="actividad">
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={styles.keyboardAvoiding}
      >
        <ScrollView
          contentContainerStyle={[
            styles.scrollContent,
            { paddingBottom: Math.max(32, insets.bottom + 92) },
          ]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
      <View style={styles.successIcon}>
        <Text style={styles.successCheck}>{saveError ? "!" : isLoading ? "..." : completionCopy.icon}</Text>
      </View>
      <ScreenTitle
        eyebrow={saveError ? "Guardado pendiente" : isLoading ? "Resumen del recorrido" : isSimulated ? "Modo prueba" : isPausedWithoutProgress ? "Ruta pausada" : "Recorrido finalizado"}
        title={
          saveError ? "No se pudo guardar el recorrido"
            : isLoading ? "Cargando resumen"
            : isSimulated
            ? "Recorrido simulado"
            : isPausedWithoutProgress
            ? "Ruta en pausa"
            : isEndedEarly
              ? "Recorrido guardado"
              : "Sendero completado"
        }
        subtitle={
          saveError ? "Volvé a intentar el guardado antes de continuar."
            : isLoading ? "Estamos preparando tu actividad."
            : isSimulated
            ? "Usaste ubicacion simulada: este recorrido no se guarda como actividad ni se sincroniza."
            : isPausedWithoutProgress
            ? "No registramos distancia recorrida, asi que no la marcamos como terminada."
            : isEndedEarly
              ? "Guardamos tu actividad y el punto del sendero donde terminaste."
            : "Guardamos tu actividad con los datos registrados por la app."
        }
      />

      {isLoading ? <Text style={styles.statusText}>Cargando resumen...</Text> : null}
      {saveError && <Card tone="orange">
        <Text accessibilityLiveRegion="polite" style={styles.cardText}>{saveError}</Text>
        <PrimaryButton label="Reintentar guardado" onPress={() => setSaveAttempt((attempt) => attempt + 1)} />
      </Card>}

      {!isLoading && session && !!trailId && !isSimulated && !isPausedWithoutProgress && <Card tone="green">
        <Text style={styles.cardTitle}>Informá que terminaste</Text>
        <Text style={styles.cardText}>Avisale a tu contacto de emergencia que finalizaste tu recorrido. Abriremos Mensajes con el texto preparado para que confirmes el envío.</Text>
        <PrimaryButton label="Informar a mi contacto de emergencia" icon="chatbubble-outline" onPress={notifyContact} isLoading={isPreparingSms} loadingLabel="Preparando mensaje" />
        {!!smsStatus && <Text accessibilityLiveRegion="polite" style={styles.cardText}>{smsStatus}</Text>}
      </Card>}

      {!isLoading && !saveError && <CompletionSessionContent
        canReview={canReview}
        hasReview={hasReview}
        isEndedEarly={isEndedEarly}
        isPausedWithoutProgress={isPausedWithoutProgress}
        isSavingReview={isSavingReview}
        isSimulated={isSimulated}
        progressPercent={progressPercent}
        rating={rating}
        reviewStatus={reviewStatus}
        reviewText={reviewText}
        saveReview={saveReview}
        session={session}
        setRating={setRating}
        setReviewText={setReviewText}
        trackingPointCount={trackingPointCount}
        trailId={trailId}
      />}

      {!isLoading && !saveError && <PrimaryButton
        label={completionCopy.finalActionLabel}
        tone={completionCopy.finalActionTone}
        onPress={() => router.push(completionCopy.finalActionRoute)}
      />}
        </ScrollView>
      </KeyboardAvoidingView>
    </AppScreen>
  );
}

function CompletionSessionContent({
  canReview,
  hasReview,
  isEndedEarly,
  isPausedWithoutProgress,
  isSavingReview,
  isSimulated,
  progressPercent,
  rating,
  reviewStatus,
  reviewText,
  saveReview,
  session,
  setRating,
  setReviewText,
  trackingPointCount,
  trailId,
}: {
  canReview: boolean;
  hasReview: boolean;
  isEndedEarly: boolean;
  isPausedWithoutProgress: boolean;
  isSavingReview: boolean;
  isSimulated: boolean;
  progressPercent: number | null;
  rating: number;
  reviewStatus: string | null;
  reviewText: string;
  saveReview: () => void;
  session: SessionRow | null;
  setRating: (rating: number) => void;
  setReviewText: (text: string) => void;
  trackingPointCount: number;
  trailId: number | null;
}) {
  if (!session) return <EmptyCompletionCard />;

  return (
    <>
      <CompletionMetrics session={session} progressPercent={progressPercent} isSimulated={isSimulated} />
      <CompletionPerformanceCard
        isEndedEarly={isEndedEarly}
        isPausedWithoutProgress={isPausedWithoutProgress}
        isSimulated={isSimulated}
        session={session}
        trackingPointCount={trackingPointCount}
      />
      {canReview ? (
        <ReviewCard
          hasReview={hasReview}
          isSavingReview={isSavingReview}
          rating={rating}
          reviewStatus={reviewStatus}
          reviewText={reviewText}
          saveReview={saveReview}
          setRating={setRating}
          setReviewText={setReviewText}
        />
      ) : null}
      <ContinueRouteButton
        isPausedWithoutProgress={isPausedWithoutProgress}
        session={session}
        trailId={trailId}
      />
    </>
  );
}

function CompletionMetrics({
  isSimulated,
  progressPercent,
  session,
}: {
  isSimulated: boolean;
  progressPercent: number | null;
  session: SessionRow;
}) {
  return (
    <View style={styles.metricsRow}>
      <Metric label="Distancia" value={formatDistance(session.distance ?? 0)} />
      <Metric label="Tiempo" value={formatDuration(session.duration ?? 0)} />
      <Metric
        label="Progreso"
        value={progressPercent !== null ? `${progressPercent}%` : isSimulated ? "Sin guardar" : "Guardado"}
      />
    </View>
  );
}

function CompletionPerformanceCard({
  isEndedEarly,
  isPausedWithoutProgress,
  isSimulated,
  session,
  trackingPointCount,
}: {
  isEndedEarly: boolean;
  isPausedWithoutProgress: boolean;
  isSimulated: boolean;
  session: SessionRow;
  trackingPointCount: number;
}) {
  if (isSimulated) {
    return (
      <Card tone="orange">
        <Text style={styles.cardTitle}>Datos simulados</Text>
        <Text style={styles.cardText}>
          Distancia y tiempo calculados con ubicación simulada para pruebas. No quedan en tu historial.
        </Text>
        {trackingPointCount > 0 ? (
          <Text style={styles.cardMeta}>{trackingPointCount} puntos simulados (no se guardan).</Text>
        ) : null}
      </Card>
    );
  }

  return (
    <Card tone="green">
      <Text style={styles.cardTitle}>
        {getPerformanceTitle(isPausedWithoutProgress, isEndedEarly)}
      </Text>
      <Text style={styles.cardText}>
        {getPerformanceText(isPausedWithoutProgress, isEndedEarly, session)}
      </Text>
      {trackingPointCount > 0 ? (
        <Text style={styles.cardMeta}>
          {trackingPointCount} puntos GPS guardados para validar distancia y recorrido.
        </Text>
      ) : null}
    </Card>
  );
}

function ReviewCard({
  hasReview,
  isSavingReview,
  rating,
  reviewStatus,
  reviewText,
  saveReview,
  setRating,
  setReviewText,
}: {
  hasReview: boolean;
  isSavingReview: boolean;
  rating: number;
  reviewStatus: string | null;
  reviewText: string;
  saveReview: () => void;
  setRating: (rating: number) => void;
  setReviewText: (text: string) => void;
}) {
  const reviewCopy = getReviewCopy(hasReview);

  return (
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
            <Ionicons
              name={value <= rating ? "star" : "star-outline"}
              size={32}
              color={value <= rating ? colors.primary : colors.border}
            />
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
  );
}

function ContinueRouteButton({
  isPausedWithoutProgress,
  session,
  trailId,
}: {
  isPausedWithoutProgress: boolean;
  session: SessionRow;
  trailId: number | null;
}) {
  if (!isPausedWithoutProgress || !trailId) return null;

  return (
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
  );
}

function EmptyCompletionCard() {
  return (
    <Card>
      <Text style={styles.cardTitle}>No hay actividad finalizada</Text>
      <Text style={styles.cardText}>
        Todavia no encontramos una sesion guardada para mostrar en este resumen.
      </Text>
    </Card>
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

function getPerformanceTitle(
  isPausedWithoutProgress: boolean,
  isEndedEarly: boolean
) {
  if (isPausedWithoutProgress) return "Actividad pendiente";
  return isEndedEarly ? "Punto alcanzado" : "Tu rendimiento";
}

function getPerformanceText(
  isPausedWithoutProgress: boolean,
  isEndedEarly: boolean,
  session: SessionRow
) {
  if (isPausedWithoutProgress) {
    return "La ruta quedo guardada en pausa. Podes continuarla desde Actividad o volver al mapa ahora.";
  }

  if (isEndedEarly) return getEndedEarlyText(session);

  return "La actividad quedo guardada localmente y ya esta disponible en tus actividades recientes.";
}

const styles = StyleSheet.create({
  keyboardAvoiding: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
  },
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
});
