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
  TopBar,
  colors,
  typography,
} from "../components/MiSenderoUI";
import { ExpandableSection } from "../components/ExpandableSection";
import { TrailMetrics } from "../components/TrailMetrics";
import { TrailSkeleton } from "../components/TrailSkeleton";
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
import { formatKilometers, parseRouteCoordinates } from "../../services/geoUtils";

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
        setDownloadMessage(total > 0 ? `Descargando mapa: ${Math.round(downloaded / total * 100)}%` : "Preparando el mapa...");
      });
      if (saved?.trail) setTrail(saved.trail);
      setIsDownloaded(true);
      setDownloadMessage("Mapa básico y recorrido descargados. Ya podés abrirlos sin conexión.");
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
        {isLoading ? <TrailSkeleton variant="detail" /> : null}
        {error ? (
          <StatusNotice
            actionLabel="Reintentar"
            message={error}
            onAction={loadTrail}
            title="No se pudo cargar"
            tone="error"
          />
        ) : null}

        {!isLoading && !error && trail ? (
          <TrailDetailContent
            key={trail.id}
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
  const hasGeometry = parseRouteCoordinates(trail.route_coordinates).length >= 2;

  return (
    <>
      <TrailCover ratingSummary={ratingSummary} trail={trail} />
      <Text accessibilityRole="header" style={styles.title}>{trail.name}</Text>
      <Text style={styles.location}>{trail.location}</Text>
      <TrailStats trail={trail} />
      {trail.provenance ? <Text style={styles.routeMetadata}>
        {trail.provenance.route_type === "out_and_back" ? "Ida y vuelta" : trail.provenance.route_type === "loop" ? "Circuito completo" : trail.provenance.route_type === "point_to_point" ? "Solo ida; coordiná el regreso" : "Tipo de recorrido a confirmar"}
        {!trail.duration ? ". Duración total a confirmar."
          : trail.provenance.duration_basis === "round_trip_from_official_one_way" ? ". Tiempo total orientativo calculado; no publicado como ida y vuelta."
          : trail.provenance.duration_basis === "planning_estimate" ? ". Tiempo orientativo de planificación."
          : ["official_reference", "catalog_record_unconfirmed", "unconfirmed"].includes(trail.provenance.duration_basis) ? ". Confirmá el alcance del tiempo indicado." : "."}
      </Text> : null}
      {!hasGeometry && trail.provenance?.mapping_pending_reason ? <Text style={styles.routeMetadata}>Ficha informativa sin navegación GPS ni mapa descargable.</Text> : null}
      <FavoriteButton
        isFavorite={isFavorite}
        onPress={toggleFavorite}
      />
      {weather?.risk_level === "alto" || weather?.risk_level === "medio" ? <StatusNotice
        title={`Riesgo meteorológico ${weather.risk_level}`}
        message={`${weather.condition}, viento ${weather.wind_kmh} km/h. Considerá postergar o elegir una ruta más corta.`}
        tone="warning"
      /> : null}
      {trail.provenance?.precautions || trail.provenance?.source_notice ? <View style={styles.precautions}>
        <Ionicons name="information-circle-outline" size={20} color={colors.greenDark} />
        <View style={styles.precautionsText}>
          {trail.provenance.source_notice ? <Text style={styles.checkText}>{trail.provenance.source_notice}</Text> : null}
          {trail.provenance.precautions ? <Text style={styles.checkText}>{trail.provenance.precautions}</Text> : null}
        </View>
      </View> : null}
      {hasGeometry ? <TrailDetailActions
        downloadMap={downloadMap}
        isDownloaded={isDownloaded}
        isDownloading={isDownloading}
        trail={trail}
      /> : null}
      <View style={styles.detailSections}>
        <BeforeYouGoCard tips={beforeYouGoTips} />
        <DescriptionCard trail={trail} />
        <DifficultyCard trail={trail} weather={weather} />
      </View>
      {hasGeometry ? <AltimetrySection trail={trail} /> : null}
      {trail.national_park && <NationalParkEntry park={trail.national_park} trailId={trail.id} trailName={trail.name} />}
      <TrailSources trail={trail} />
      {hasGeometry ? <OfflineMapCard
        downloadMessage={downloadMessage}
        isDownloaded={isDownloaded}
      /> : <InfoCard style={styles.card}>
        <Text style={styles.cardTitle}>Consultá el recorrido</Text>
        <Text style={styles.body}>Podés ver la información del sendero y sus accesos en la fuente del recorrido.</Text>
      </InfoCard>}
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
  const [imageFailed, setImageFailed] = useState(false);
  const hasImage = Boolean(trail.image_url) && !imageFailed;
  const photo = trail.provenance?.photo;
  return (
    <>
    <ImageBackground
      source={hasImage ? { uri: trail.image_url! } : undefined}
      onError={() => setImageFailed(true)}
      style={[styles.cover, !hasImage && styles.coverFallback]}
      imageStyle={styles.coverImage}
    >
      {!hasImage ? <Text style={styles.body}>Foto no disponible</Text> : null}
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
          <Ionicons name="star" size={15} color={colors.primary} />
          <Text style={styles.coverBadgeText}>
            {ratingSummary.averageRating.toFixed(1)}
          </Text>
          <Text style={styles.coverBadgeMeta}>({ratingSummary.reviewCount})</Text>
        </Pressable>
      ) : null}
      {hasImage && photo && (
        <Pressable accessibilityLabel="Creditos de la foto" accessibilityRole="button" hitSlop={8}
          onPress={() => {
            Alert.alert("Creditos de la foto", `${photo.author} - ${photo.license}${photo.context ? `\n${photo.context}` : ""}`, [
              { text: "Cerrar", style: "cancel" },
              { text: "Ver fuente", onPress: () => { void Linking.openURL(photo.page_url).catch(() => Alert.alert("No se pudo abrir la foto")); } },
            ]);
          }} style={styles.photoCreditsButton}>
          <Ionicons name="information-circle-outline" size={16} color={colors.muted} />
        </Pressable>
      )}
    </ImageBackground>
    </>
  );
}

function TrailStats({ trail }: { trail: Trail }) {

  return (
    <TrailMetrics columns={2} items={[
      { icon: "walk-outline", label: "Distancia", value: getTrailDistanceLabel(trail) },
      { icon: "time-outline", label: "Duración estimada", value: trail.duration || "A confirmar" },
      { icon: "trail-sign-outline", label: "Dificultad", value: trail.difficulty || "A confirmar" },
      { icon: "trending-up-outline", label: "Desnivel de ascenso", value: trail.elevation ? `+${trail.elevation.ascent_m} m` : "Sin dato" },
    ]} />
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
        color={colors.greenDark}
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
    <ExpandableSection title="Sobre el recorrido" summary="Descripción y punto de inicio" icon="leaf-outline">
      <Text style={styles.body}>
        {trail.description || "Pronto vas a encontrar mas informacion sobre este recorrido."}
      </Text>
      {trail.provenance ? <Text style={styles.routeMetadata}>Inicio: {trail.provenance.access}</Text> : null}
    </ExpandableSection>
  );
}

function TrailSources({ trail }: { trail: Trail }) {
  const source = trail.provenance?.sources.find((item) => item.title === "Ficha del recorrido") ?? trail.provenance?.sources[0];
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
      {trail.provenance?.mapping ? <Pressable accessibilityRole="link" onPress={() => router.push({ pathname: "/atribuciones", params: { trailId: String(trail.id) } })} style={styles.sourceLink}>
        <Text style={styles.creditsText}>Créditos cartográficos</Text>
      </Pressable> : null}
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
    <ExpandableSection title="Dificultad de la ruta" summary="Qué esfuerzo requiere" icon="trail-sign-outline">
      <Text style={styles.body}>{getDifficultyInsight(trail, weather)}</Text>
    </ExpandableSection>
  );
}

function BeforeYouGoCard({ tips }: { tips: string[] }) {
  return (
    <ExpandableSection title="Ver preparación y clima" summary={`Antes de salir · ${tips.length} recomendaciones`} icon="checkmark-circle-outline">
      {tips.map((tip) => (
        <View key={tip} style={styles.checkRow}>
          <Ionicons name="checkmark-circle" size={20} color={colors.green} />
          <Text style={styles.checkText}>{tip}</Text>
        </View>
      ))}
    </ExpandableSection>
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
  if (error instanceof Error && "code" in error) {
    if (error.code === "provider-not-configured") return "Las descargas de mapas todavía no están disponibles. Podés consultar el sendero con conexión.";
    if (error.code === "storage-unavailable") return "Este dispositivo no permite guardar mapas sin conexión. Probá desde tu teléfono.";
  }
  if (error instanceof Error && error.message.startsWith("offline-map-incomplete")) {
    return "La descarga no quedo completa. Reintenta con conexion estable antes de salir.";
  }

  return "No pudimos descargar el mapa completo. Revisa tu conexion e intenta de nuevo.";
}

const styles = StyleSheet.create({
  photoCreditsButton: {
    position: "absolute", bottom: 8, right: 8, width: 28, height: 28,
    alignItems: "center", justifyContent: "center", borderRadius: 8,
    backgroundColor: "rgba(255,255,255,0.85)",
  },
  creditsText: { color: colors.muted, fontSize: 11, lineHeight: 16 },
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
  coverFallback: { height: 88, backgroundColor: colors.soft, borderRadius: 24, justifyContent: "center" },
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
    fontFamily: typography.extraBold,
    color: colors.ink,
    fontSize: 30,
    fontWeight: "800",
    lineHeight: 36,
  },
  location: {
    fontFamily: typography.regular,
    color: colors.muted,
    fontSize: 15,
    marginTop: 6,
  },
  card: {
    marginTop: 16,
  },
  cardTitle: {
    fontFamily: typography.bold,
    color: colors.ink,
    fontSize: 18,
    fontWeight: "700",
    marginBottom: 10,
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
  body: {
    fontFamily: typography.regular,
    color: colors.muted,
    fontSize: 15,
    lineHeight: 23,
  },
  checkRow: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 9,
    marginTop: 9,
  },
  checkText: {
    fontFamily: typography.regular,
    color: colors.muted,
    flex: 1,
    fontSize: 14,
    lineHeight: 20,
  },
  footer: {
    gap: 10,
    marginTop: 18,
  },
  detailSections: { marginTop: 24 },
  precautions: { flexDirection: "row", alignItems: "flex-start", gap: 10, marginTop: 18 },
  precautionsText: { flex: 1, gap: 8 },
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
    backgroundColor: colors.mint,
    borderColor: colors.primary,
  },
  favoriteText: {
    color: colors.greenDark,
    fontSize: 13,
    fontWeight: "900",
  },
});
