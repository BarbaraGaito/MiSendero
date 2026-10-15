import { useCallback, useEffect, useState } from "react";
import { router, useLocalSearchParams } from "expo-router";
import { Alert, ImageBackground, Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
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
import { getTrailById, getTrailReports, getTrailWeather } from "../../services/trailRepository";
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
import { NationalParkEntry } from "../components/NationalParkUI";
import { formatKilometers } from "../../services/geoUtils";

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
    } catch {
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
      const saved = await saveOfflineTrailMap(trail, reports, (downloaded, total) => {
        setDownloadMessage(`Descargando tiles ${downloaded}/${total}...`);
      });
      if (saved?.trail) setTrail(saved.trail);
      setIsDownloaded(true);
      setDownloadMessage("Mapa descargado. Ya podes abrirlo sin conexion.");
    } catch (downloadError) {
      setIsDownloaded(false);
      setDownloadMessage(getDownloadErrorMessage(downloadError));
    } finally {
      setIsDownloading(false);
    }
  };

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
          <TrailDetailContent
            downloadMap={downloadMap}
            downloadMessage={downloadMessage}
            isDownloaded={isDownloaded}
            isDownloading={isDownloading}
            isFavorite={isFavorite}
            ratingSummary={ratingSummary}
            toggleFavorite={toggleFavorite}
            trail={trail}
            weather={weather}
          />
        ) : null}
      </ScrollView>
    </ScreenShell>
  );
}

function TrailDetailContent({
  downloadMap,
  downloadMessage,
  isDownloaded,
  isDownloading,
  isFavorite,
  ratingSummary,
  toggleFavorite,
  trail,
  weather,
}: {
  downloadMap: () => void;
  downloadMessage: string | null;
  isDownloaded: boolean;
  isDownloading: boolean;
  isFavorite: boolean;
  ratingSummary: TrailRatingSummary | null;
  toggleFavorite: () => void;
  trail: Trail;
  weather: TrailWeather | null;
}) {
  const beforeYouGoTips = getBeforeYouGoTips(trail, weather);

  return (
    <>
      <TrailCover ratingSummary={ratingSummary} trail={trail} />
      <Text style={styles.title}>{trail.name}</Text>
      <Text style={styles.location}>{trail.location}</Text>
      <TrailStats trail={trail} />
      <FavoriteButton
        isFavorite={isFavorite}
        onPress={toggleFavorite}
      />
      <DescriptionCard trail={trail} />
      <DifficultyCard trail={trail} weather={weather} />
      <BeforeYouGoCard tips={trail.provenance ? [trail.provenance.precautions, ...beforeYouGoTips] : beforeYouGoTips} />
      <AltimetrySection trail={trail} />
      {trail.national_park && <NationalParkEntry park={trail.national_park} trailId={trail.id} trailName={trail.name} />}
      <TrailSources trail={trail} />
      <OfflineMapCard
        downloadMessage={downloadMessage}
        isDownloaded={isDownloaded}
      />
      <TrailDetailActions
        downloadMap={downloadMap}
        isDownloaded={isDownloaded}
        isDownloading={isDownloading}
        trail={trail}
      />
    </>
  );
}

function TrailCover({
  ratingSummary,
  trail,
}: {
  ratingSummary: TrailRatingSummary | null;
  trail: Trail;
}) {
  return (
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
          <Text style={styles.coverBadgeMeta}>({ratingSummary.reviewCount})</Text>
        </Pressable>
      ) : null}
      {trail.provenance?.photo && (
        <Pressable accessibilityLabel="Creditos de la foto" accessibilityRole="button"
          onPress={() => {
            const photo = trail.provenance!.photo;
            Alert.alert("Creditos de la foto", `${photo.author} - ${photo.license}${photo.context ? `\n${photo.context}` : ""}`, [
              { text: "Cerrar", style: "cancel" },
              { text: "Ver fuente", onPress: () => { void Linking.openURL(photo.page_url).catch(() => Alert.alert("No se pudo abrir la foto")); } },
            ]);
          }} style={styles.photoCreditsButton}>
          <Ionicons name="information-circle-outline" size={23} color={colors.ink} />
        </Pressable>
      )}
    </ImageBackground>
  );
}

function TrailStats({ trail }: { trail: Trail }) {

  return (
    <View style={styles.stats}>
      <StatPill icon="walk-outline" label={getTrailDistanceLabel(trail)} />
      <StatPill icon="time-outline" label={trail.duration || "Duracion a confirmar"} />
      <StatPill icon="leaf-outline" label={trail.difficulty} />
      <StatPill icon="trending-up-outline" label={trail.elevation ? `Desnivel: +${trail.elevation.ascent_m} m` : "Desnivel no disponible"} />
    </View>
  );
}

function FavoriteButton({
  isFavorite,
  onPress,
}: {
  isFavorite: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityLabel={isFavorite ? "Quitar de favoritas" : "Guardar como favorita"}
      accessibilityRole="button"
      onPress={onPress}
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
  );
}

function AltimetrySection({ trail }: { trail: Trail }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Abrir altimetria del sendero"
      onPress={() => router.push({ pathname: "/trail-elevation", params: { id: String(trail.id) } })}
      style={({ pressed }) => [styles.altimetrySection, pressed && styles.pressed]}
    >
      <Ionicons name="analytics-outline" size={22} color={colors.green} />
      <Text style={styles.altimetryTitle}>Altimetria</Text>
      <Ionicons name="chevron-forward" size={20} color={colors.muted} />
    </Pressable>
  );
}

function DescriptionCard({ trail }: { trail: Trail }) {
  return (
    <InfoCard style={styles.card}>
      <Text style={styles.cardTitle}>Descripcion</Text>
      <Text style={styles.body}>
        {trail.description || "Pronto vas a encontrar mas informacion sobre este recorrido."}
      </Text>
      {trail.provenance ? (
        <>
          <Text style={styles.routeMetadata}>Inicio: {trail.provenance.access}</Text>
          <Text style={styles.routeMetadata}>
            {trail.provenance.route_type === "out_and_back" ? "Ida y vuelta" : "Solo ida; coordinar el regreso"}
            {trail.provenance.duration_basis === "planning_estimate" ? ". Tiempo orientativo, no oficial." : "."}
          </Text>
        </>
      ) : null}
    </InfoCard>
  );
}

function TrailSources({ trail }: { trail: Trail }) {
  const source = trail.provenance?.sources.find((item) => item.title === "Ficha del recorrido");
  if (!source) return null;
  const openSource = (url: string) => {
    Linking.openURL(url).catch(() => Alert.alert("No se pudo abrir la fuente", "Revisa tu conexion e intenta nuevamente."));
  };
  return (
    <View style={styles.sourcesSection}>
      <Text style={styles.cardTitle}>Fuentes del recorrido</Text>
      <Pressable accessibilityRole="link" onPress={() => openSource(source.url)} style={styles.sourceLink}>
        <Ionicons name="open-outline" size={16} color={colors.greenDark} />
        <Text style={styles.sourceText}>Ficha del recorrido</Text>
      </Pressable>
    </View>
  );
}

function DifficultyCard({
  trail,
  weather,
}: {
  trail: Trail;
  weather: TrailWeather | null;
}) {
  if (!trail.difficulty) return null;

  return (
    <InfoCard style={styles.aiCard}>
      <View style={styles.aiHeader}>
        <Ionicons name="sparkles-outline" size={20} color={colors.green} />
        <Text style={styles.cardTitle}>Dificultad de la ruta</Text>
      </View>
      <Text style={styles.body}>{getDifficultyInsight(trail, weather)}</Text>
    </InfoCard>
  );
}

function BeforeYouGoCard({ tips }: { tips: string[] }) {
  return (
    <InfoCard style={styles.card}>
      <Text style={styles.cardTitle}>Antes de salir</Text>
      {tips.map((tip) => (
        <View key={tip} style={styles.checkRow}>
          <Ionicons name="checkmark-circle" size={20} color={colors.green} />
          <Text style={styles.checkText}>{tip}</Text>
        </View>
      ))}
    </InfoCard>
  );
}

function OfflineMapCard({
  downloadMessage,
  isDownloaded,
}: {
  downloadMessage: string | null;
  isDownloaded: boolean;
}) {
  return (
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
          <Text style={styles.cardTitle}>
            {isDownloaded ? "Mapa sin conexion descargado" : "Mapa sin conexion"}
          </Text>
          <Text style={styles.body}>
            {isDownloaded
              ? "Esta ruta y sus reportes ya estan disponibles aunque no tengas internet."
              : "Guarda esta ruta y sus reportes para verla aunque no tengas internet."}
          </Text>
        </View>
      </View>
      {downloadMessage ? (
        <Text style={styles.downloadStatus}>{downloadMessage}</Text>
      ) : null}
    </InfoCard>
  );
}

function TrailDetailActions({
  downloadMap,
  isDownloaded,
  isDownloading,
  trail,
}: {
  downloadMap: () => void;
  isDownloaded: boolean;
  isDownloading: boolean;
  trail: Trail;
}) {
  return (
    <View style={styles.footer}>
      <PrimaryButton
        label="Ver ruta"
        icon="map-outline"
        onPress={() =>
          router.push({
            pathname: "/route-map",
            params: { id: String(trail.id) },
          })
        }
      />
      {!isDownloaded ? (
        <PrimaryButton
          label="Descargar mapa"
          icon="download-outline"
          isLoading={isDownloading}
          loadingLabel="Descargando mapa"
          tone="secondary"
          onPress={downloadMap}
        />
      ) : null}
    </View>
  );
}

const getTrailDistanceLabel = (trail: Trail) =>
  trail.distance_km ? formatKilometers(trail.distance_km) : "Distancia a confirmar";

function getDifficultyInsight(trail: Trail, weather: TrailWeather | null) {
  const difficulty = normalizeDifficulty(trail.difficulty);
  const distanceText = trail.distance_km
    ? formatKilometers(trail.distance_km)
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

function getDownloadErrorMessage(error: unknown) {
  if (error instanceof Error && error.message === "offline-elevation-unavailable") {
    return "No pudimos obtener la altimetria. Reintenta con conexion antes de descargar esta ruta.";
  }
  if (error instanceof Error && "code" in error && error.code === "provider-not-configured") return error.message;
  if (error instanceof Error && error.message.startsWith("offline-map-incomplete")) {
    return "La descarga no quedo completa. Reintenta con conexion estable antes de salir.";
  }

  return "No pudimos descargar el mapa completo. Revisa tu conexion e intenta de nuevo.";
}

const styles = StyleSheet.create({
  photoCreditsButton: {
    position: "absolute", bottom: 10, right: 10, width: 44, height: 44,
    alignItems: "center", justifyContent: "center", borderRadius: 8,
    backgroundColor: "rgba(255,255,255,0.95)",
  },
  routeMetadata: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21,
    marginTop: 10,
  },
  sourcesSection: {
    marginTop: 20,
  },
  sourceLink: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    minHeight: 44,
    paddingVertical: 8,
  },
  sourceText: {
    flex: 1,
    color: colors.greenDark,
    fontSize: 14,
    lineHeight: 21,
  },
  altimetrySection: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 20,
    marginTop: 18,
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: colors.line,
  },
  altimetryTitle: {
    flex: 1,
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
  },
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
