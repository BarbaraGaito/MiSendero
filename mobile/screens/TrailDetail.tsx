import React, { useCallback, useEffect, useState } from "react";
import { router, useLocalSearchParams } from "expo-router";
import { ImageBackground, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import {
  InfoCard,
  PrimaryButton,
  ScreenShell,
  StatusNotice,
  StatPill,
  TopBar,
  colors,
  trailImages,
} from "../components/MiSenderoUI";
import { getTrailById, getTrailReports, getTrailWeather } from "../../services/api";
import {
  getVerifiedOfflineMapByTrailId,
  saveOfflineTrailMap,
} from "../../services/offlineMaps";
import { isTrailFavorite, setTrailFavorite } from "../../services/favoriteTrails";
import {
  getTrailRatingSummary,
  TrailRatingSummary,
} from "../../database/sessionsRepository";
import { initDB } from "../../database/database";
import { Trail, TrailWeather } from "../../types";
import { parseRouteCoordinates } from "../../services/geoUtils";
import { getTerrainElevationGainMeters } from "../components/Terrain3DScene";

const loadTrailDetailData = async (trailId: number) => {
  await initDB();
  const trail = await getTrailById(trailId);
  const [offlineMap, ratingSummary, isFavorite, weather] = await Promise.all([
    getVerifiedOfflineMapByTrailId(trail.id),
    getTrailRatingSummary(trail.id),
    isTrailFavorite(trail.id),
    getTrailWeather(trail.id).catch(() => null),
  ]);

  return {
    trail,
    isDownloaded: Boolean(offlineMap),
    ratingSummary,
    isFavorite,
    weather,
  };
};

export default function Screen03TrailDetail() {
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id?: string }>();
  const [trail, setTrail] = useState<Trail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isDownloaded, setIsDownloaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloadMessage, setDownloadMessage] = useState<string | null>(null);
  const [ratingSummary, setRatingSummary] = useState<TrailRatingSummary | null>(null);
  const [weather, setWeather] = useState<TrailWeather | null>(null);
  const [isFavorite, setIsFavorite] = useState(false);

  const loadTrail = useCallback(async () => {
    const trailId = Number(id);
    setIsLoading(true);
    setError(null);

    if (!trailId) {
      setError("No se encontro el sendero seleccionado.");
      setIsLoading(false);
      return;
    }

    try {
      const data = await loadTrailDetailData(trailId);
      setTrail(data.trail);
      setIsDownloaded(data.isDownloaded);
      setRatingSummary(data.ratingSummary);
      setIsFavorite(data.isFavorite);
      setWeather(data.weather);
    } catch (loadError) {
      setError("No pudimos cargar este sendero en este momento.");
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadTrail();
  }, [loadTrail]);

  const downloadMap = async () => {
    if (!trail || isDownloading) return;

    setIsDownloading(true);
    setDownloadMessage("Descargando mapa...");

    try {
      const reports = await getTrailReports(trail.id).catch(() => []);
      await saveOfflineTrailMap(trail, reports, (downloaded, total) => {
        setDownloadMessage(`Descargando tiles ${downloaded}/${total}...`);
      });
      setIsDownloaded(true);
      setDownloadMessage("Mapa descargado. Ya podes abrirlo sin conexion.");
    } catch (downloadError) {
      setIsDownloaded(false);
      setDownloadMessage(getDownloadErrorMessage(downloadError));
    } finally {
      setIsDownloading(false);
    }
  };

  const distance = trail?.distance_km ? `${trail.distance_km} km` : "Distancia a confirmar";
  const duration = trail?.duration || "Duracion a confirmar";
  const difficultyInsight = trail ? getDifficultyInsight(trail, weather) : "";
  const beforeYouGoTips = trail ? getBeforeYouGoTips(trail, weather) : [];
  const elevationGain = trail ? getTrailElevationGain(trail) : null;

  const toggleFavorite = async () => {
    if (!trail) return;

    setIsFavorite(await setTrailFavorite(trail.id, !isFavorite));
  };

  return (
    <ScreenShell>
      <TopBar title="Detalle del sendero" onBack={() => router.back()} />

      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={[
          styles.scroll,
          { paddingBottom: Math.max(28, insets.bottom + 24) },
        ]}
      >
        {isLoading ? (
          <StatusNotice
            isLoading
            message="Consultando informacion, clima y disponibilidad offline."
            title="Cargando sendero"
          />
        ) : null}
        {error ? (
          <StatusNotice
            actionLabel="Reintentar"
            message={error}
            onAction={loadTrail}
            title="No se pudo cargar"
            tone="error"
          />
        ) : null}

        {trail ? (
          <>
            <ImageBackground
              source={{ uri: trail.image_url || trailImages.mountain }}
              style={styles.cover}
              imageStyle={styles.coverImage}
            >
              {ratingSummary ? (
                <Pressable
                  onPress={() =>
                    router.push({
                      pathname: "/sendero-opiniones",
                      params: { id: String(trail.id) },
                    })
                  }
                  style={styles.coverBadge}
                >
                  <Ionicons name="star" size={15} color={colors.warning} />
                  <Text style={styles.coverBadgeText}>
                    {ratingSummary.averageRating.toFixed(1)}
                  </Text>
                  <Text style={styles.coverBadgeMeta}>
                    ({ratingSummary.reviewCount})
                  </Text>
                </Pressable>
              ) : null}
            </ImageBackground>

            <Text style={styles.title}>{trail.name}</Text>
            <Text style={styles.location}>{trail.location}</Text>

            <View style={styles.stats}>
              <StatPill icon="walk-outline" label={distance} />
              <StatPill icon="time-outline" label={duration} />
              <StatPill icon="leaf-outline" label={trail.difficulty} />
              {elevationGain !== null ? (
                <StatPill icon="trending-up-outline" label={`${elevationGain} m desnivel`} />
              ) : null}
            </View>

            <Pressable
              accessibilityLabel={isFavorite ? "Quitar de favoritas" : "Guardar como favorita"}
              accessibilityRole="button"
              onPress={toggleFavorite}
              style={({ pressed }) => [
                styles.favoriteButton,
                isFavorite && styles.favoriteButtonActive,
                pressed && styles.pressed,
              ]}
            >
              <Ionicons
                name={isFavorite ? "star" : "star-outline"}
                size={18}
                color={isFavorite ? colors.warning : colors.greenDark}
              />
              <Text style={styles.favoriteText}>
                {isFavorite ? "Ruta favorita" : "Guardar como favorita"}
              </Text>
            </Pressable>

            <InfoCard style={styles.card}>
              <Text style={styles.cardTitle}>Descripcion</Text>
              <Text style={styles.body}>
                {trail.description || "Pronto vas a encontrar mas informacion sobre este recorrido."}
              </Text>
            </InfoCard>

            {trail.difficulty ? (
              <InfoCard style={styles.aiCard}>
                <View style={styles.aiHeader}>
                  <Ionicons name="sparkles-outline" size={20} color={colors.green} />
                  <Text style={styles.cardTitle}>Dificultad de la ruta</Text>
                </View>
                <Text style={styles.body}>
                  {difficultyInsight}
                </Text>
              </InfoCard>
            ) : null}

            <InfoCard style={styles.card}>
              <Text style={styles.cardTitle}>Antes de salir</Text>
              <View style={styles.checkRow}>
                <Ionicons name="checkmark-circle" size={20} color={colors.green} />
                <Text style={styles.checkText}>{beforeYouGoTips[0]}</Text>
              </View>
              <View style={styles.checkRow}>
                <Ionicons name="checkmark-circle" size={20} color={colors.green} />
                <Text style={styles.checkText}>{beforeYouGoTips[1]}</Text>
              </View>
              {beforeYouGoTips[2] ? (
                <View style={styles.checkRow}>
                  <Ionicons name="checkmark-circle" size={20} color={colors.green} />
                  <Text style={styles.checkText}>{beforeYouGoTips[2]}</Text>
                </View>
              ) : null}
            </InfoCard>

            <InfoCard style={styles.offlineCard}>
              <View style={styles.offlineHeader}>
                <View style={styles.offlineIcon}>
                  <Ionicons
                    name={isDownloaded ? "checkmark-circle-outline" : "download-outline"}
                    size={24}
                    color={colors.green}
                  />
                </View>
                <View style={styles.offlineText}>
                  <Text style={styles.cardTitle}>Mapa sin conexion</Text>
                  <Text style={styles.body}>
                    Guarda esta ruta y sus reportes para verla aunque no tengas internet.
                  </Text>
                </View>
              </View>
              {downloadMessage ? (
                <Text style={styles.downloadStatus}>{downloadMessage}</Text>
              ) : null}
            </InfoCard>

            <View style={styles.footer}>
              <PrimaryButton
                label="Ver ruta"
                icon="map-outline"
                onPress={() =>
                  router.push({
                    pathname: "/route-map",
                    params: { id: String(trail?.id || id || 1) },
                  })
                }
              />
              <PrimaryButton
                label={isDownloaded ? "Mapa descargado" : "Descargar mapa"}
                icon={isDownloaded ? "checkmark-circle-outline" : "download-outline"}
                disabled={isDownloaded}
                isLoading={isDownloading}
                loadingLabel="Descargando mapa"
                tone="secondary"
                onPress={downloadMap}
              />
            </View>
          </>
        ) : null}
      </ScrollView>
    </ScreenShell>
  );
}

function getDifficultyInsight(trail: Trail, weather: TrailWeather | null) {
  const difficulty = normalizeDifficulty(trail.difficulty);
  const distanceText = trail.distance_km
    ? `${trail.distance_km} km`
    : "distancia pendiente de confirmar";
  const durationText = trail.duration || "duracion pendiente de confirmar";
  const weatherText = weather
    ? ` Para hoy figura ${weather.condition.toLowerCase()}, ${weather.temperature_c} C, viento de ${weather.wind_kmh} km/h y riesgo ${weather.risk_level}.`
    : "";
  const context = { distanceText, durationText, weatherText };

  return getDifficultyInsightText(difficulty, trail.difficulty, context);
}

function getBeforeYouGoTips(trail: Trail, weather: TrailWeather | null) {
  const difficulty = normalizeDifficulty(trail.difficulty);
  const isLongRoute = typeof trail.distance_km === "number" && trail.distance_km > 10;
  const hasWeatherRisk = weather?.risk_level === "alto" || weather?.risk_level === "medio";
  const weatherTip = weather
    ? `Clima actual: ${weather.condition.toLowerCase()}, ${weather.temperature_c} C, viento ${weather.wind_kmh} km/h y ${weather.rain_probability}% de probabilidad de lluvia.`
    : "Si no tenes clima actualizado, revisalo antes de salir y descarga el mapa offline.";

  if (difficulty === "alta") {
    return getHighDifficultyTips(isLongRoute, hasWeatherRisk, weatherTip);
  }

  if (difficulty === "media") {
    return [
      "Lleva agua, abrigo liviano y calzado con buena traccion; el esfuerzo puede sostenerse varias horas.",
      "Marca un punto de regreso si el clima cambia o si el ritmo real es mas lento de lo previsto.",
      weatherTip,
    ];
  }

  if (difficulty === "baja") {
    return [
      "Aunque sea una ruta accesible, lleva agua, proteccion solar y calzado comodo.",
      "Descarga el mapa si la zona tiene poca senal y revisa el punto de inicio antes de moverte.",
      weatherTip,
    ];
  }

  return [
    "Revisa distancia, duracion y punto de inicio antes de salir.",
    "Lleva agua, abrigo y bateria suficiente para usar el mapa durante todo el recorrido.",
    weatherTip,
  ];
}

function getDifficultyInsightText(
  difficulty: string,
  rawDifficulty: string,
  context: { distanceText: string; durationText: string; weatherText: string }
) {
  const { distanceText, durationText, weatherText } = context;

  if (difficulty === "alta") {
    return `Ruta exigente: son ${distanceText} y una duracion estimada de ${durationText}, por lo que conviene encararla con buen margen de luz, ritmo conservador y experiencia previa en trekking.${weatherText}`;
  }

  if (difficulty === "media") {
    return `Ruta de esfuerzo moderado: combina ${distanceText} con una duracion estimada de ${durationText}. Es una buena opcion si ya caminaste senderos similares y podes sostener un paso constante.${weatherText}`;
  }

  if (difficulty === "baja") {
    return `Ruta accesible: por sus ${distanceText} y duracion estimada de ${durationText}, esta pensada para una salida tranquila, aunque igual requiere revisar el estado del camino antes de salir.${weatherText}`;
  }

  return `Esta ruta tiene dificultad ${rawDifficulty}, ${distanceText} y una duracion estimada de ${durationText}. Revisa el mapa, el clima y el estado del sendero antes de iniciarla.${weatherText}`;
}

function getHighDifficultyTips(
  isLongRoute: boolean,
  hasWeatherRisk: boolean,
  weatherTip: string
) {
  const timingTip = isLongRoute
    ? "Sali temprano, avisa tu itinerario y evita iniciar si no tenes margen para volver con luz."
    : "Planifica el regreso antes de empezar y evita exigirte si notas fatiga temprana.";
  const weatherRiskTip = hasWeatherRisk
    ? "Con riesgo meteorologico medio o alto, considera postergar o elegir una ruta mas corta."
    : weatherTip;

  return [
    timingTip,
    "Lleva agua extra, abrigo, comida, bateria suficiente y mapa descargado.",
    weatherRiskTip,
  ];
}

function normalizeDifficulty(difficulty: string) {
  return difficulty
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

function getTrailElevationGain(trail: Trail) {
  const routePoints = parseRouteCoordinates(trail.route_coordinates);

  if (routePoints.length < 2 && !trail.distance_km) return null;

  return getTerrainElevationGainMeters(
    routePoints,
    trail.difficulty,
    trail.distance_km
  );
}

function getDownloadErrorMessage(error: unknown) {
  if (error instanceof Error && error.message.startsWith("offline-map-incomplete")) {
    return "La descarga no quedo completa. Reintenta con conexion estable antes de salir.";
  }

  return "No pudimos descargar el mapa completo. Revisa tu conexion e intenta de nuevo.";
}

const styles = StyleSheet.create({
  scroll: {
    flexGrow: 1,
  },
  statusText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 14,
  },
  cover: {
    height: 230,
    justifyContent: "flex-start",
    marginBottom: 22,
    padding: 16,
  },
  coverImage: {
    borderRadius: 28,
  },
  coverBadge: {
    alignItems: "center",
    alignSelf: "flex-end",
    backgroundColor: colors.white,
    borderRadius: 17,
    flexDirection: "row",
    gap: 5,
    paddingHorizontal: 11,
    paddingVertical: 7,
  },
  coverBadgeText: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "900",
  },
  coverBadgeMeta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "800",
  },
  title: {
    color: colors.ink,
    fontSize: 30,
    fontWeight: "900",
    lineHeight: 36,
  },
  location: {
    color: colors.muted,
    fontSize: 15,
    marginTop: 6,
  },
  stats: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 9,
    marginTop: 18,
  },
  card: {
    marginTop: 16,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
    marginBottom: 10,
  },
  aiCard: {
    backgroundColor: colors.mint,
    marginTop: 16,
  },
  offlineCard: {
    marginTop: 16,
  },
  offlineHeader: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 12,
    marginBottom: 14,
  },
  offlineIcon: {
    alignItems: "center",
    backgroundColor: colors.primarySoft,
    borderRadius: 18,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  offlineText: {
    flex: 1,
  },
  downloadStatus: {
    color: colors.greenDark,
    fontSize: 13,
    fontWeight: "800",
    lineHeight: 18,
    marginBottom: 12,
  },
  aiHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  body: {
    color: colors.muted,
    fontSize: 15,
    lineHeight: 23,
  },
  checkRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 9,
    marginTop: 9,
  },
  checkText: {
    color: colors.muted,
    flex: 1,
    fontSize: 14,
    lineHeight: 20,
  },
  footer: {
    gap: 10,
    marginTop: 18,
  },
  pressed: {
    opacity: 0.72,
  },
  favoriteButton: {
    alignItems: "center",
    alignSelf: "flex-start",
    backgroundColor: colors.primarySoft,
    borderColor: colors.border,
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: "row",
    gap: 7,
    marginTop: 16,
    paddingHorizontal: 13,
    paddingVertical: 9,
  },
  favoriteButtonActive: {
    backgroundColor: colors.orangeSoft,
    borderColor: colors.warning,
  },
  favoriteText: {
    color: colors.greenDark,
    fontSize: 13,
    fontWeight: "900",
  },
});
