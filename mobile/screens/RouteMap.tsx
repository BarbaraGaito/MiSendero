import { Ionicons } from "@expo/vector-icons";
import * as Network from "expo-network";
import { router, useLocalSearchParams } from "expo-router";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { getTrailById, getTrailReports, getTrailWeather } from "../../services/api";
import { getVerifiedOfflineMapByTrailId } from "../../services/offlineMaps";
import {
  createDevelopmentMetricSequence,
  getWearableRuntimeStatus,
  saveWearableConnection,
} from "../../services/wearableMetrics";
import {
  Trail,
  TrailReport,
  TrailWeather,
  WearableRuntimeStatus,
  WearableSimulationScenario,
} from "../../types";
import { TrailMap } from "../components/TrailMap";
import { useDeviceLocation } from "../hooks/useDeviceLocation";
import { DeviceLocation } from "../../services/deviceLocation";
import {
  Coordinate,
  formatDistance,
  getDistanceMeters,
  getDistanceToRouteMeters,
  getRouteLengthMeters,
  getRouteProgressMeters,
  getRouteStart,
  parseRouteCoordinates,
  ROUTE_DEVIATION_WARNING_METERS,
} from "../../services/geoUtils";
import { saveRouteTrackingPoint } from "../../services/routeTracking";
import {
  InfoCard,
  PrimaryButton,
  ScreenShell,
  TopBar,
  colors,
} from "../components/MiSenderoUI";

const GPS_NOISE_FLOOR_METERS = 2;
const routeSimulationOptions: Array<{
  id: WearableSimulationScenario;
  title: string;
  icon: keyof typeof Ionicons.glyphMap;
}> = [
  { id: "normal", title: "Normal", icon: "walk-outline" },
  { id: "esfuerzo_moderado", title: "Esfuerzo", icon: "trending-up-outline" },
  { id: "fatiga_alta", title: "Fatiga", icon: "battery-dead-outline" },
  { id: "riesgo_fisiologico", title: "Riesgo", icon: "alert-circle-outline" },
];

export default function Screen04RouteMap() {
  const insets = useSafeAreaInsets();
  const { active, id, startedAt } = useLocalSearchParams<{
    active?: string;
    id?: string;
    startedAt?: string;
  }>();
  const trailId = Number(id) || 1;
  const isActiveRoute = active === "1";
  const fallbackStartedAt = useMemo(() => Date.now(), []);
  const startedAtMs = Number(startedAt) || fallbackStartedAt;
  const [trail, setTrail] = useState<Trail | null>(null);
  const [weather, setWeather] = useState<TrailWeather | null>(null);
  const [reports, setReports] = useState<TrailReport[]>([]);
  const [isWifiConnected, setIsWifiConnected] = useState(false);
  const [hasInternetConnection, setHasInternetConnection] = useState(false);
  const [isContextLoading, setIsContextLoading] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [wearableRuntime, setWearableRuntime] =
    useState<WearableRuntimeStatus | null>(null);
  const [testingWearableScenario, setTestingWearableScenario] =
    useState<WearableSimulationScenario>("esfuerzo_moderado");
  const [testingWearableMessage, setTestingWearableMessage] = useState<string | null>(null);
  const [isSimulatingWearable, setIsSimulatingWearable] = useState(false);
  const [trackedDistanceMeters, setTrackedDistanceMeters] = useState(0);
  const [lastGpsRecordedAt, setLastGpsRecordedAt] = useState<number | null>(null);
  const lastTrackedLocationRef = useRef<DeviceLocation | null>(null);
  const trackedDistanceMetersRef = useRef(0);

  useEffect(() => {
    let isMounted = true;

    const loadRouteContext = async () => {
      setIsLoading(true);
      setIsContextLoading(true);

      try {
        const networkState = await Network.getNetworkStateAsync().catch(() => null);
        if (!isMounted) return;

        const hasWifi =
          networkState?.type === Network.NetworkStateType.WIFI &&
          networkState.isConnected !== false &&
          networkState.isInternetReachable !== false;
        const hasInternet =
          networkState?.isConnected !== false &&
          networkState?.isInternetReachable !== false;
        let trailData: Trail | null = null;
        let reportsData: TrailReport[] = [];

        if (hasInternet) {
          trailData = await getTrailById(trailId);
          reportsData = await getTrailReports(trailId).catch(() => []);
        } else {
          const offlineMap = await getVerifiedOfflineMapByTrailId(trailId);

          if (!offlineMap?.trail) {
            throw new Error("offline-map-not-found");
          }

          trailData = offlineMap.trail;
          reportsData = offlineMap.reports;
        }

        setTrail(trailData);
        setReports(reportsData);
        setIsWifiConnected(hasWifi);
        setHasInternetConnection(hasInternet);
        setError(null);

        if (!hasWifi) {
          setWeather(null);
          return;
        }

        const weatherData = await getTrailWeather(trailId).catch(() => null);

        if (isMounted) {
          setWeather(weatherData);
        }
      } catch (loadError) {
        if (!isMounted) return;

        const offlineMap = await getVerifiedOfflineMapByTrailId(trailId).catch(() => null);

        if (offlineMap?.trail) {
          setTrail(offlineMap.trail);
          setReports(offlineMap.reports);
          setIsWifiConnected(false);
          setHasInternetConnection(false);
          setWeather(null);
          setError(null);
        } else {
          setError("No pudimos cargar el mapa de este sendero.");
          setWeather(null);
          setReports([]);
          setIsWifiConnected(false);
          setHasInternetConnection(false);
        }
      } finally {
        if (!isMounted) return;

        setIsLoading(false);
        setIsContextLoading(false);
      }
    };

    loadRouteContext();

    return () => {
      isMounted = false;
    };
  }, [trailId]);

  const refreshWearableMetrics = useCallback(async () => {
    const elapsedMinutes = Math.max(
      0,
      Math.floor((Date.now() - startedAtMs) / 60000)
    );
    const status = await getWearableRuntimeStatus(elapsedMinutes).catch(
      () => null
    );

    return status;
  }, [startedAtMs]);

  useEffect(() => {
    if (!isActiveRoute) {
      setWearableRuntime(null);
      return;
    }

    let isMounted = true;

    const refreshIfMounted = async () => {
      const status = await refreshWearableMetrics();
      if (!isMounted) return;
      setWearableRuntime(status);
    };

    refreshIfMounted();
    const interval = setInterval(refreshIfMounted, 12_000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [isActiveRoute, refreshWearableMetrics]);

  const routePoints = useMemo(
    () => parseRouteCoordinates(trail?.route_coordinates),
    [trail?.route_coordinates]
  );
  const simulatedStartLocation = useMemo(() => {
    if (!trail) return null;
    if (
      routePoints.length === 0 &&
      (trail.center_lat === null || trail.center_lng === null)
    ) {
      return null;
    }

    const fallbackCenter: Coordinate = [
      trail.center_lat ?? 0,
      trail.center_lng ?? 0,
    ];

    return getRouteStart(routePoints, fallbackCenter);
  }, [routePoints, trail]);
  const {
    location,
    permissionDenied: locationPermissionDenied,
    isTestingLocation,
  } = useDeviceLocation(isActiveRoute, simulatedStartLocation);

  useEffect(() => {
    trackedDistanceMetersRef.current = trackedDistanceMeters;
  }, [trackedDistanceMeters]);

  useEffect(() => {
    if (!isActiveRoute) return;

    setTrackedDistanceMeters(0);
    trackedDistanceMetersRef.current = 0;
    setLastGpsRecordedAt(null);
    lastTrackedLocationRef.current = null;
  }, [isActiveRoute, startedAtMs, trailId]);

  useEffect(() => {
    if (!isActiveRoute || !location) return;

    const previous = lastTrackedLocationRef.current;
    let deltaMeters = 0;

    if (previous && !isTestingLocation) {
      deltaMeters = getDistanceMeters(previous.coordinate, location.coordinate);

      if (deltaMeters < GPS_NOISE_FLOOR_METERS) {
        lastTrackedLocationRef.current = location;
        return;
      }
    }

    const elapsedMs =
      previous && location.timestamp > previous.timestamp
        ? location.timestamp - previous.timestamp
        : 0;
    const speedFromGps =
      !isTestingLocation && elapsedMs > 0
        ? Number(((deltaMeters / (elapsedMs / 1000)) * 3.6).toFixed(2))
        : null;

    lastTrackedLocationRef.current = location;
    if (deltaMeters > 0) {
      trackedDistanceMetersRef.current += deltaMeters;
      setTrackedDistanceMeters(trackedDistanceMetersRef.current);
    }
    setLastGpsRecordedAt(location.timestamp);

    saveRouteTrackingPoint({
      trailId,
      startedAt: startedAtMs,
      latitude: location.coordinate[0],
      longitude: location.coordinate[1],
      accuracyMeters: location.accuracy,
      speedKmh: speedFromGps,
      distanceDeltaMeters: deltaMeters,
      recordedAt: location.timestamp,
      simulated: isTestingLocation,
    }).catch(() => null);
  }, [isActiveRoute, isTestingLocation, location, startedAtMs, trailId]);

  useEffect(() => {
    if (!isActiveRoute || !isTestingLocation || routePoints.length === 0) return;

    let pointIndex = 0;
    let previousPoint = routePoints[0];

    const interval = setInterval(() => {
      pointIndex = Math.min(pointIndex + 1, routePoints.length - 1);
      const nextPoint = routePoints[pointIndex];
      const deltaMeters =
        pointIndex === 0 ? 0 : getDistanceMeters(previousPoint, nextPoint);
      previousPoint = nextPoint;

      if (deltaMeters > 0) {
        trackedDistanceMetersRef.current += deltaMeters;
        setTrackedDistanceMeters(trackedDistanceMetersRef.current);
      }

      const timestamp = Date.now();
      setLastGpsRecordedAt(timestamp);

      saveRouteTrackingPoint({
        trailId,
        startedAt: startedAtMs,
        latitude: nextPoint[0],
        longitude: nextPoint[1],
        accuracyMeters: 0,
        speedKmh: deltaMeters > 0 ? Number(((deltaMeters / 3) * 3.6).toFixed(2)) : 0,
        distanceDeltaMeters: deltaMeters,
        recordedAt: timestamp,
        simulated: true,
      }).catch(() => null);

      if (pointIndex >= routePoints.length - 1) {
        clearInterval(interval);
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [isActiveRoute, isTestingLocation, routePoints, startedAtMs, trailId]);
  const routeDeviationMeters = useMemo(() => {
    if (!isActiveRoute || !location || routePoints.length === 0) return null;
    return getDistanceToRouteMeters(location.coordinate, routePoints);
  }, [isActiveRoute, location, routePoints]);
  const totalRouteMeters = useMemo(() => {
    if (trail?.distance_km) return trail.distance_km * 1000;
    return getRouteLengthMeters(routePoints);
  }, [routePoints, trail?.distance_km]);
  const traveledMeters = useMemo(() => {
    if (!isActiveRoute || !location || routePoints.length === 0) return null;
    return getRouteProgressMeters(location.coordinate, routePoints);
  }, [isActiveRoute, location, routePoints]);
  const completedDistanceMeters =
    trackedDistanceMeters > 0 ? trackedDistanceMeters : traveledMeters;
  const isOffRoute =
    !isTestingLocation &&
    routeDeviationMeters !== null &&
    routeDeviationMeters > ROUTE_DEVIATION_WARNING_METERS;
  const simulateWearableScenario = async (scenario: WearableSimulationScenario) => {
    if (isSimulatingWearable) return;

    if (wearableRuntime?.status === "requires_consent") {
      setTestingWearableMessage("Activa datos sensibles en Perfil para ver el analisis IA.");
      return;
    }

    setTestingWearableScenario(scenario);
    setIsSimulatingWearable(true);
    try {
      if (!wearableRuntime?.connection.linked) {
        await saveWearableConnection("development_simulator", true, true);
      }
      await createDevelopmentMetricSequence(scenario, 8);
      const status = await refreshWearableMetrics();
      setWearableRuntime(status);
      setTestingWearableMessage(
        `Simulacion ${routeSimulationOptions.find((option) => option.id === scenario)?.title.toLowerCase()} aplicada.`
      );
    } catch {
      setTestingWearableMessage("No pudimos generar la simulacion wearable.");
    } finally {
      setIsSimulatingWearable(false);
    }
  };
  const activeTop = Math.max(22, insets.top + 14);
  const activeBannerTop = activeTop + 68;
  const hasStatusBanner =
    isLoading || Boolean(error) || (!isLoading && !error && locationPermissionDenied);
  const primaryBannerHeight = isOffRoute ? 76 : hasStatusBanner ? 64 : 0;
  const testingBannerTop = activeBannerTop + primaryBannerHeight + 10;
  const testingBannerHeight = isTestingLocation ? 158 : 0;
  const mapControlsTop =
    activeBannerTop + primaryBannerHeight + testingBannerHeight + 18;
  const hasBlockingReport = reports.some((report) => report.blocks_path);
  const severeReports = reports.filter((report) =>
    ["Alta", "Critica"].includes(report.severity)
  ).length;

  if (isActiveRoute) {
    return (
      <SafeAreaView edges={["top", "bottom"]} style={styles.activeShell}>
        <TrailMap
          trail={trail}
          fitRoute
          immersive
          initialPerspective
          showDetailsCard={false}
          showMapNotices={false}
          controlsTopOffset={mapControlsTop}
          allowSatellite={hasInternetConnection}
        />

        <View style={[styles.activeHeader, { top: activeTop }]}>
          <Pressable onPress={() => router.back()} style={styles.activeIconButton}>
            <Ionicons name="chevron-back" size={22} color={colors.ink} />
          </Pressable>
          <View style={styles.activeTitleBox}>
            <Text style={styles.activeEyebrow}>Ruta en curso</Text>
            <Text numberOfLines={1} style={styles.activeTitle}>
              {trail?.name || "Mapa del recorrido"}
            </Text>
          </View>
        </View>

        {isLoading || error ? (
          <View style={[styles.activeStatus, { top: activeBannerTop }]}>
            <Text style={styles.statusText}>
              {isLoading ? "Cargando mapa..." : error}
            </Text>
          </View>
        ) : null}

        {!isLoading && !error && locationPermissionDenied ? (
          <View style={[styles.activeStatus, { top: activeBannerTop }]}>
            <Text style={styles.statusText}>
              Activa la ubicacion para detectar desvíos de ruta.
            </Text>
          </View>
        ) : null}

        {isOffRoute && routeDeviationMeters !== null ? (
          <View style={[styles.deviationBanner, { top: activeBannerTop }]}>
            <Ionicons name="warning-outline" size={20} color={colors.danger} />
            <View style={styles.deviationText}>
              <Text style={styles.deviationTitle}>Te alejaste de la ruta</Text>
              <Text style={styles.deviationBody}>
                Estas a {formatDistance(routeDeviationMeters)} del sendero marcado.
              </Text>
            </View>
            <Pressable
              onPress={() =>
                router.push({
                  pathname: "/alerta-ruta",
                  params: {
                    id: String(trailId),
                    distance: String(Math.round(routeDeviationMeters)),
                    startedAt: String(startedAtMs),
                  },
                })
              }
              style={styles.deviationButton}
            >
              <Text style={styles.deviationButtonText}>Ver</Text>
            </Pressable>
          </View>
        ) : null}

        {isTestingLocation ? (
          <View style={[styles.testingBanner, { top: testingBannerTop }]}>
            <View style={styles.testingBannerHeader}>
              <Ionicons name="flask-outline" size={17} color={colors.greenDark} />
              <View style={styles.testingBannerTextBox}>
                <Text style={styles.testingBannerText}>
                  Testing activo
                </Text>
                <Text style={styles.testingBannerHint}>
                  Simula ubicacion y situaciones del wearable.
                </Text>
              </View>
              <Pressable
                accessibilityRole="button"
                onPress={() => router.push("/reloj-salud")}
                style={styles.testingSettingsButton}
              >
                <Ionicons name="settings-outline" size={16} color={colors.greenDark} />
              </Pressable>
            </View>
            <View style={styles.testingScenarioRow}>
              {routeSimulationOptions.map((option) => {
                const selected = testingWearableScenario === option.id;
                return (
                  <Pressable
                    accessibilityRole="button"
                    disabled={isSimulatingWearable}
                    key={option.id}
                    onPress={() => simulateWearableScenario(option.id)}
                    style={[
                      styles.testingScenarioButton,
                      selected && styles.testingScenarioButtonSelected,
                      isSimulatingWearable && styles.testingScenarioButtonDisabled,
                    ]}
                  >
                    <Ionicons
                      name={option.icon}
                      size={15}
                      color={selected ? colors.white : colors.greenDark}
                    />
                    <Text
                      style={[
                        styles.testingScenarioText,
                        selected && styles.testingScenarioTextSelected,
                      ]}
                    >
                      {option.title}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
            <Text style={styles.testingBannerStatus}>
              {isSimulatingWearable
                ? "Generando ventana de metricas..."
                : testingWearableMessage || "Toca un escenario para probar el analisis IA."}
            </Text>
          </View>
        ) : null}

        <View style={[styles.activeFooter, { paddingBottom: Math.max(16, insets.bottom + 10) }]}>
          {wearableRuntime?.prediction && wearableRuntime.latestSample ? (
            <View
              style={[
                styles.wearableAnalysisPanel,
                wearableRuntime.prediction.level === "high" && styles.wearableBannerHigh,
                wearableRuntime.prediction.level === "caution" && styles.wearableBannerCaution,
              ]}
            >
              <View style={styles.wearableAnalysisHeader}>
                <View style={styles.wearableAnalysisIcon}>
                  <Ionicons
                    name="sparkles-outline"
                    size={18}
                    color={
                      wearableRuntime.prediction.level === "high"
                        ? colors.danger
                        : colors.green
                    }
                  />
                </View>
                <View style={styles.wearableText}>
                  <Text style={styles.wearableEyebrow}>Analisis IA en vivo</Text>
                  <Text style={styles.wearableTitle}>
                    {wearableRuntime.latestSample.heartRateBpm} bpm - {wearableRuntime.prediction.title}
                  </Text>
                </View>
              </View>
              <View style={styles.wearableMetricRow}>
                <WearableChip label="Riesgo" value={wearableRuntime.prediction.riskLabel} />
                <WearableChip label="Fatiga" value={wearableRuntime.prediction.fatigue} />
                <WearableChip
                  label="Conf."
                  value={`${Math.round(wearableRuntime.prediction.riskConfidence * 100)}%`}
                />
              </View>
              <Text numberOfLines={2} style={styles.wearableBody}>
                {wearableRuntime.prediction.recommendedAction}
              </Text>
              <View style={styles.wearableFactorRow}>
                {wearableRuntime.prediction.factors.slice(0, 3).map((factor) => (
                  <Text key={factor} numberOfLines={1} style={styles.wearableFactor}>
                    {factor}
                  </Text>
                ))}
              </View>
            </View>
          ) : null}

          <Pressable
            onPress={() =>
              router.push({
                pathname: "/recorrido-finalizado",
                params: {
                  id: String(trailId),
                  startedAt: String(startedAtMs),
                  traveledMeters:
                    completedDistanceMeters !== null ? String(Math.round(completedDistanceMeters)) : "",
                  routeProgressMeters:
                    traveledMeters !== null ? String(Math.round(traveledMeters)) : "",
                  totalMeters:
                    totalRouteMeters > 0 ? String(Math.round(totalRouteMeters)) : "",
                  endedLatitude: location ? String(location.coordinate[0]) : "",
                  endedLongitude: location ? String(location.coordinate[1]) : "",
                },
              })
            }
            style={styles.finishRouteButton}
          >
            <View style={styles.finishRouteIcon}>
              <Ionicons name="flag-outline" size={22} color={colors.white} />
            </View>
            <View style={styles.finishRouteTextBox}>
              <Text style={styles.finishRouteLabel}>Terminar ruta</Text>
              <Text style={styles.finishRouteHint}>Guardar actividad y dejar opinion</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.white} />
          </Pressable>

          <View style={styles.quickActionsRow}>
            <Pressable
              onPress={() =>
                router.push({
                  pathname: "/descanso",
                  params: {
                    id: String(trailId),
                    startedAt: String(startedAtMs),
                    traveledMeters:
                      traveledMeters !== null ? String(Math.round(traveledMeters)) : "",
                    totalMeters:
                      totalRouteMeters > 0 ? String(Math.round(totalRouteMeters)) : "",
                  },
                })
              }
              style={styles.activeAction}
            >
              <Ionicons name="pause-outline" size={20} color={colors.greenDark} />
              <Text style={styles.activeActionText}>Pausa</Text>
            </Pressable>
            <Pressable
              onPress={() =>
                router.push({
                  pathname: "/reportar-terreno",
                  params: { id: String(trailId) },
                })
              }
              style={styles.activeAction}
            >
              <Ionicons name="megaphone-outline" size={20} color={colors.greenDark} />
              <Text style={styles.activeActionText}>Reporte</Text>
            </Pressable>
            <Pressable
              onPress={() =>
                router.push({
                  pathname: "/alerta-ruta",
                  params: { id: String(trailId), startedAt: String(startedAtMs) },
                })
              }
              style={styles.activeAction}
            >
              <Ionicons name="trail-sign-outline" size={20} color={colors.greenDark} />
              <Text style={styles.activeActionText}>Ruta</Text>
            </Pressable>
            <Pressable
              onPress={() =>
                router.push({
                  pathname: "/confirmar-sos",
                  params: { id: String(trailId), startedAt: String(startedAtMs) },
                })
              }
              style={[styles.activeAction, styles.activeDangerAction]}
            >
              <Ionicons name="alert-circle-outline" size={20} color={colors.white} />
              <Text style={styles.activeDangerText}>SOS</Text>
            </Pressable>
          </View>
          <View style={styles.activeTelemetryRow}>
            <Text style={styles.activeTelemetryText}>
              GPS: {formatDistance(trackedDistanceMeters)}
            </Text>
            <Text style={styles.activeTelemetryText}>
              {lastGpsRecordedAt ? "Ultimo punto guardado" : "Esperando punto GPS"}
            </Text>
          </View>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <ScreenShell>
      <TopBar title="Mapa del recorrido" onBack={() => router.back()} />

      <ScrollView
        contentContainerStyle={[
          styles.scrollContent,
          { paddingBottom: Math.max(24, insets.bottom + 18) },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {isLoading ? <Text style={styles.statusText}>Cargando mapa...</Text> : null}
        {error ? <Text style={styles.statusText}>{error}</Text> : null}

        <TrailMap trail={trail} allowSatellite={hasInternetConnection} />

        <InfoCard style={styles.progressCard}>
          <View style={styles.progressText}>
            <Text style={styles.cardTitle}>Ruta lista</Text>
            <Text style={styles.cardText}>
              Usa Terreno para ver curvas de nivel o 3D para revisar la ruta con relieve.
            </Text>
          </View>
          <View style={styles.downloadBadge}>
            <Ionicons name="map-outline" size={24} color={colors.green} />
          </View>
        </InfoCard>

        {isWifiConnected ? (
          <InfoCard style={styles.previewCard}>
            <View style={styles.sectionHeader}>
              <View style={styles.sectionHeaderText}>
                <Text style={styles.cardTitle}>Clima de hoy</Text>
                <Text style={styles.cardText}>
                  {trail?.location || "Ubicacion de la ruta"}
                </Text>
              </View>
              <View
                style={[
                  styles.riskBadge,
                  weather?.risk_level === "alto" && styles.riskBadgeHigh,
                  weather?.risk_level === "medio" && styles.riskBadgeMedium,
                ]}
              >
                <Text
                  style={[
                    styles.riskBadgeText,
                    weather?.risk_level === "alto" && styles.riskBadgeTextHigh,
                    weather?.risk_level === "medio" && styles.riskBadgeTextMedium,
                  ]}
                >
                  {weather ? `Riesgo ${weather.risk_level}` : "Consultando"}
                </Text>
              </View>
            </View>

            {isContextLoading && !weather ? (
              <Text style={styles.loadingText}>Consultando clima de la ruta...</Text>
            ) : weather ? (
              <>
                <View style={styles.weatherGrid}>
                  <WeatherMetric
                    icon="thermometer-outline"
                    label="Temp."
                    value={`${weather.temperature_c} C`}
                  />
                  <WeatherMetric
                    icon="cloud-outline"
                    label="Estado"
                    value={weather.condition}
                  />
                  <WeatherMetric
                    icon="leaf-outline"
                    label="Viento"
                    value={`${weather.wind_kmh} km/h`}
                  />
                  <WeatherMetric
                    icon="rainy-outline"
                    label="Lluvia"
                    value={`${weather.rain_probability}%`}
                  />
                </View>
                <Text style={styles.recommendationText}>{weather.recommendation}</Text>
                <Text style={styles.sourceText}>{weather.source}</Text>
              </>
            ) : (
              <Text style={styles.loadingText}>No pudimos consultar el clima.</Text>
            )}
          </InfoCard>
        ) : null}

        <InfoCard style={styles.previewCard}>
          <View style={styles.sectionHeader}>
            <View style={styles.sectionHeaderText}>
              <Text style={styles.cardTitle}>Reportes de usuarios</Text>
              <Text style={styles.cardText}>
                {reports.length > 0
                  ? `${reports.length} reportes recientes`
                  : "Sin reportes recientes"}
              </Text>
            </View>
            {hasBlockingReport || severeReports > 0 ? (
              <View style={[styles.riskBadge, styles.riskBadgeHigh]}>
                <Text style={[styles.riskBadgeText, styles.riskBadgeTextHigh]}>
                  revisar
                </Text>
              </View>
            ) : null}
          </View>

          {isContextLoading && reports.length === 0 ? (
            <Text style={styles.loadingText}>Cargando reportes del sendero...</Text>
          ) : reports.length > 0 ? (
            <View style={styles.reportList}>
              {reports.slice(0, 3).map((report) => (
                <View key={report.id} style={styles.reportItem}>
                  <View style={styles.reportIcon}>
                    <Ionicons
                      name={report.blocks_path ? "alert-circle-outline" : "chatbubble-outline"}
                      size={18}
                      color={report.blocks_path ? colors.danger : colors.green}
                    />
                  </View>
                  <View style={styles.reportText}>
                    <Text style={styles.reportTitle}>{report.issue_summary}</Text>
                    <Text style={styles.reportMeta}>
                      {report.trail_state} - Riesgo {report.severity}
                      {report.route_progress_meters !== null
                        ? ` - km ${(report.route_progress_meters / 1000).toLocaleString("es-AR", {
                            maximumFractionDigits: 1,
                          })}`
                        : ""}
                    </Text>
                    <Text style={styles.reportDate}>
                      {formatReportDateTime(report.created_at)}
                    </Text>
                    {report.details ? (
                      <Text numberOfLines={2} style={styles.reportDetails}>
                        {report.details}
                      </Text>
                    ) : null}
                  </View>
                </View>
              ))}
            </View>
          ) : (
            <Text style={styles.loadingText}>
              Todavia no hay avisos recientes para esta ruta.
            </Text>
          )}
        </InfoCard>

        <View style={styles.footer}>
          <PrimaryButton
            label="Iniciar recorrido"
            icon="navigate-outline"
            onPress={() =>
              router.push({
                pathname: "/trail-start",
                params: { id: String(trailId) },
              })
            }
          />
          <PrimaryButton
            label="Descargar mapa"
            icon="download-outline"
            tone="secondary"
            onPress={() =>
              router.push({
                pathname: "/offline-descarga",
                params: { id: String(trailId) },
              })
            }
          />
        </View>
      </ScrollView>
    </ScreenShell>
  );
}

function formatReportDateTime(value: string) {
  const normalizedValue = value.includes("T") ? value : `${value.replace(" ", "T")}Z`;
  const date = new Date(normalizedValue);

  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function WeatherMetric({
  icon,
  label,
  value,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: string;
}) {
  return (
    <View style={styles.weatherMetric}>
      <Ionicons name={icon} size={18} color={colors.green} />
      <Text style={styles.weatherLabel}>{label}</Text>
      <Text style={styles.weatherValue}>
        {value}
      </Text>
    </View>
  );
}

function WearableChip({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.wearableChip}>
      <Text style={styles.wearableChipLabel}>{label}</Text>
      <Text style={styles.wearableChipValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  activeShell: {
    backgroundColor: colors.softer,
    flex: 1,
  },
  activeHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    left: 14,
    position: "absolute",
    right: 14,
    zIndex: 20,
  },
  activeIconButton: {
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.96)",
    borderRadius: 18,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  activeTitleBox: {
    backgroundColor: "rgba(255,255,255,0.96)",
    borderRadius: 18,
    flex: 1,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  activeEyebrow: {
    color: colors.green,
    fontSize: 11,
    fontWeight: "900",
  },
  activeTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
    marginTop: 1,
  },
  activeStatus: {
    backgroundColor: "rgba(255,255,255,0.94)",
    borderRadius: 16,
    left: 14,
    paddingHorizontal: 12,
    paddingVertical: 9,
    position: "absolute",
    right: 14,
    zIndex: 20,
  },
  deviationBanner: {
    alignItems: "center",
    backgroundColor: "rgba(255,244,242,0.97)",
    borderColor: "rgba(216,76,63,0.24)",
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: "row",
    gap: 10,
    left: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
    position: "absolute",
    right: 14,
    zIndex: 21,
  },
  deviationText: {
    flex: 1,
  },
  deviationTitle: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "900",
  },
  deviationBody: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
    marginTop: 2,
  },
  deviationButton: {
    backgroundColor: colors.danger,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  deviationButtonText: {
    color: colors.white,
    fontSize: 12,
    fontWeight: "900",
  },
  testingBanner: {
    backgroundColor: "rgba(223,243,231,0.97)",
    borderColor: "rgba(13,122,69,0.24)",
    borderRadius: 16,
    borderWidth: 1,
    left: 14,
    paddingHorizontal: 12,
    paddingVertical: 9,
    position: "absolute",
    right: 14,
    zIndex: 21,
  },
  testingBannerHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  testingBannerTextBox: {
    flex: 1,
    minWidth: 0,
  },
  testingBannerText: {
    color: colors.greenDark,
    fontSize: 12,
    fontWeight: "900",
  },
  testingBannerHint: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "700",
    marginTop: 1,
  },
  testingSettingsButton: {
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.76)",
    borderRadius: 12,
    height: 32,
    justifyContent: "center",
    width: 32,
  },
  testingScenarioRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 7,
    marginTop: 9,
  },
  testingScenarioButton: {
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.78)",
    borderColor: colors.border,
    borderRadius: 12,
    borderWidth: 1,
    flexBasis: "22%",
    flexDirection: "row",
    flexGrow: 1,
    gap: 4,
    justifyContent: "center",
    minHeight: 34,
    minWidth: 72,
    paddingHorizontal: 6,
  },
  testingScenarioButtonSelected: {
    backgroundColor: colors.green,
    borderColor: colors.green,
  },
  testingScenarioButtonDisabled: {
    opacity: 0.68,
  },
  testingScenarioText: {
    color: colors.greenDark,
    fontSize: 11,
    fontWeight: "900",
  },
  testingScenarioTextSelected: {
    color: colors.white,
  },
  testingBannerStatus: {
    color: colors.greenDark,
    fontSize: 11,
    fontWeight: "800",
    marginTop: 8,
  },
  wearableAnalysisPanel: {
    backgroundColor: "rgba(255,255,255,0.96)",
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    marginBottom: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  wearableAnalysisHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 9,
  },
  wearableAnalysisIcon: {
    alignItems: "center",
    backgroundColor: "rgba(223,243,231,0.9)",
    borderRadius: 14,
    height: 36,
    justifyContent: "center",
    width: 36,
  },
  wearableBannerCaution: {
    backgroundColor: "rgba(255,244,216,0.97)",
    borderColor: "rgba(217,119,6,0.24)",
  },
  wearableBannerHigh: {
    backgroundColor: "rgba(255,244,242,0.97)",
    borderColor: "rgba(216,76,63,0.24)",
  },
  wearableText: {
    flex: 1,
    minWidth: 0,
  },
  wearableTitle: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "900",
  },
  wearableEyebrow: {
    color: colors.green,
    fontSize: 10,
    fontWeight: "900",
    marginBottom: 1,
    textTransform: "uppercase",
  },
  wearableBody: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "700",
    lineHeight: 15,
    marginTop: 8,
  },
  wearableMetricRow: {
    flexDirection: "row",
    gap: 7,
    marginTop: 9,
  },
  wearableChip: {
    backgroundColor: colors.page,
    borderColor: colors.border,
    borderRadius: 12,
    borderWidth: 1,
    flex: 1,
    minWidth: 0,
    paddingHorizontal: 8,
    paddingVertical: 7,
  },
  wearableChipLabel: {
    color: colors.muted,
    fontSize: 9,
    fontWeight: "900",
    textTransform: "uppercase",
  },
  wearableChipValue: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "900",
    marginTop: 2,
  },
  wearableFactorRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
    marginTop: 8,
  },
  wearableFactor: {
    backgroundColor: "rgba(223,243,231,0.82)",
    borderRadius: 999,
    color: colors.greenDark,
    flexShrink: 1,
    fontSize: 10,
    fontWeight: "900",
    maxWidth: "48%",
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  activeFooter: {
    backgroundColor: "rgba(246,250,247,0.96)",
    borderTopColor: colors.line,
    borderTopWidth: 1,
    bottom: 0,
    left: 0,
    padding: 14,
    position: "absolute",
    right: 0,
    zIndex: 20,
  },
  finishRouteButton: {
    alignItems: "center",
    backgroundColor: colors.primary,
    borderRadius: 20,
    flexDirection: "row",
    gap: 12,
    minHeight: 62,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  finishRouteIcon: {
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.18)",
    borderRadius: 16,
    height: 40,
    justifyContent: "center",
    width: 40,
  },
  finishRouteTextBox: {
    flex: 1,
    minWidth: 0,
  },
  finishRouteLabel: {
    color: colors.white,
    fontSize: 17,
    fontWeight: "900",
  },
  finishRouteHint: {
    color: "rgba(255,255,255,0.82)",
    fontSize: 12,
    fontWeight: "700",
    marginTop: 2,
  },
  quickActionsRow: {
    flexDirection: "row",
    gap: 8,
    marginTop: 10,
  },
  activeAction: {
    alignItems: "center",
    backgroundColor: colors.primarySoft,
    borderRadius: 16,
    flex: 1,
    gap: 4,
    justifyContent: "center",
    minHeight: 54,
    paddingHorizontal: 4,
  },
  activeDangerAction: {
    backgroundColor: colors.danger,
  },
  activeActionText: {
    color: colors.greenDark,
    fontSize: 11,
    fontWeight: "900",
  },
  activeDangerText: {
    color: colors.white,
    fontSize: 11,
    fontWeight: "900",
  },
  activeTelemetryRow: {
    flexDirection: "row",
    gap: 8,
    justifyContent: "space-between",
    marginTop: 9,
  },
  activeTelemetryText: {
    color: colors.muted,
    flexShrink: 1,
    fontSize: 11,
    fontWeight: "800",
  },
  statusText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 10,
  },
  scrollContent: {
    flexGrow: 1,
  },
  progressCard: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 12,
    marginBottom: 16,
    marginTop: 2,
  },
  previewCard: {
    marginBottom: 16,
  },
  sectionHeader: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
    marginBottom: 14,
  },
  sectionHeaderText: {
    flex: 1,
    minWidth: 0,
  },
  progressText: {
    flex: 1,
    minWidth: 0,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
    lineHeight: 23,
  },
  cardText: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21,
    marginTop: 4,
  },
  downloadBadge: {
    alignItems: "center",
    backgroundColor: colors.soft,
    borderRadius: 20,
    flexShrink: 0,
    height: 48,
    justifyContent: "center",
    marginTop: 3,
    width: 48,
  },
  riskBadge: {
    alignSelf: "flex-start",
    backgroundColor: colors.primarySoft,
    borderRadius: 999,
    flexShrink: 0,
    maxWidth: 104,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  riskBadgeMedium: {
    backgroundColor: "#FFF4D8",
  },
  riskBadgeHigh: {
    backgroundColor: colors.redSoft,
  },
  riskBadgeText: {
    color: colors.greenDark,
    fontSize: 10,
    fontWeight: "900",
    lineHeight: 13,
    textTransform: "uppercase",
  },
  riskBadgeTextMedium: {
    color: "#8A5A00",
  },
  riskBadgeTextHigh: {
    color: colors.danger,
  },
  loadingText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "700",
    lineHeight: 20,
  },
  weatherGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  weatherMetric: {
    backgroundColor: colors.page,
    borderColor: colors.border,
    borderRadius: 14,
    borderWidth: 1,
    flexBasis: "47%",
    flexGrow: 1,
    minHeight: 92,
    minWidth: 126,
    padding: 11,
  },
  weatherLabel: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "800",
    marginTop: 6,
  },
  weatherValue: {
    color: colors.ink,
    flexShrink: 1,
    fontSize: 13,
    fontWeight: "900",
    lineHeight: 17,
    marginTop: 2,
  },
  recommendationText: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "700",
    lineHeight: 19,
    marginTop: 12,
  },
  sourceText: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "700",
    marginTop: 8,
  },
  reportList: {
    gap: 10,
  },
  reportItem: {
    alignItems: "flex-start",
    backgroundColor: colors.page,
    borderColor: colors.border,
    borderRadius: 14,
    borderWidth: 1,
    flexDirection: "row",
    gap: 10,
    padding: 11,
  },
  reportIcon: {
    alignItems: "center",
    backgroundColor: colors.soft,
    borderRadius: 999,
    height: 34,
    justifyContent: "center",
    width: 34,
  },
  reportText: {
    flex: 1,
  },
  reportTitle: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "900",
    lineHeight: 18,
  },
  reportMeta: {
    color: colors.greenDark,
    fontSize: 12,
    fontWeight: "800",
    lineHeight: 16,
    marginTop: 3,
  },
  reportDate: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "800",
    lineHeight: 15,
    marginTop: 3,
  },
  reportDetails: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 17,
    marginTop: 5,
  },
  footer: {
    gap: 10,
    paddingTop: 6,
  },
});
