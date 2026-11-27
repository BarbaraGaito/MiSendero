import { ensureRouteSession, getRouteSession, getSimulatedRouteTrackingSummary, activeRouteSeconds, pauseRouteSession, resumeRouteSession } from "../../services/routeSession";
import { DepartureMessageRequiredError } from "../../services/departureMessages";
import { userMessage } from "../../services/userMessages";
import { Ionicons } from "@expo/vector-icons";
import * as Network from "expo-network";
import { router, useLocalSearchParams } from "expo-router";
import { useScreenFocused } from "../hooks/useScreenFocused";
import { ReportActions } from "../components/ReportActions";
import { FieldAssessmentPanel } from "../components/FieldAssessmentPanel";
import { ReportFeedbackControls } from "../components/ReportFeedbackControls";
import { buildReportRouteRanges, getUpcomingReport, isActiveReport } from "../../services/reportExperience";
import { OfflineConnectionBanner } from "../components/OfflineConnectionBanner";
import { useIsOffline } from "../../services/ConnectivityProvider";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View, Vibration } from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { getTrailById, getTrailReports, getTrailWeather } from "../../services/trailRepository";
import { getOfflineMapByTrailId, getVerifiedOfflineMapByTrailId } from "../../services/offlineMaps";
import {
  createDevelopmentMetricSequence,
  getWearableRuntimeStatus,
  syncNativeWearableSampleWithStatus,
} from "../../services/wearableMetrics";
import {
  Trail,
  TrailReport,
  TrailWeather,
  WearableRuntimeStatus,
  WearableSimulationScenario,
} from "../../types";
import { TrailMap } from "../components/TrailMap";
import { MiSenderoLogo } from "../components/MiSenderoLogo";
import { surfaceShadows } from "../components/surfaceShadows";
import { useDeviceLocation } from "../hooks/useDeviceLocation";
import { useFallDetection } from "../hooks/useFallDetection";
import { DeviceLocation } from "../../services/deviceLocation";
import {
  Coordinate,
  formatDistance,
  getDistanceToRouteMeters,
  getRouteLengthMeters,
  getRouteProgressMeters,
  getRouteStart,
  parseRouteCoordinates,
  ROUTE_DEVIATION_WARNING_METERS,
} from "../../services/geoUtils";
import { getRouteTrackingSummary } from "../../services/routeTracking";
import {
  InfoCard,
  PrimaryButton,
  ScreenShell,
  TopBar,
  colors,
} from "../components/MiSenderoUI";

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

const getNetworkStatus = async () => {
  const networkState = await Network.getNetworkStateAsync();
  const hasWifi =
    networkState.type === Network.NetworkStateType.WIFI &&
    networkState.isConnected !== false &&
    networkState.isInternetReachable !== false;
  const hasInternet =
    networkState.isConnected !== false &&
    networkState.isInternetReachable !== false;

  return { hasWifi, hasInternet };
};

const loadRouteContext = async (trailId: number, offlineOnly = false) => {
  const { hasWifi, hasInternet } = offlineOnly ? {hasWifi:false,hasInternet:false} : await getNetworkStatus();

  if (hasInternet) {
    const [trail, reports, offlineMap] = await Promise.all([
      getTrailById(trailId),
      getTrailReports(trailId).catch(() => []),
      getVerifiedOfflineMapByTrailId(trailId).catch(() => null),
    ]);

    return { trail, reports, hasWifi, hasInternet, isDownloaded: Boolean(offlineMap) };
  }

  const offlineMap = await getOfflineMapByTrailId(trailId);

  if (!offlineMap?.trail) {
    throw new Error("offline-map-not-found");
  }

  return {
    trail: offlineMap.trail,
    reports: offlineMap.reports,
    hasWifi: false,
    hasInternet: false,
    isDownloaded: offlineMap.status === "disponible",
  };
};

const loadFallbackRouteContext = async (trailId: number) => {
  const offlineMap = await getOfflineMapByTrailId(trailId).catch(() => null);

  return offlineMap?.trail
    ? {
        trail: offlineMap.trail,
        reports: offlineMap.reports,
        hasWifi: false,
        hasInternet: false,
        isDownloaded: offlineMap.status === "disponible",
        error: null,
      }
    : {
        trail: null,
        reports: [],
        hasWifi: false,
        hasInternet: false,
        isDownloaded: false,
        error: "No pudimos cargar el mapa de este sendero.",
      };
};

const getSimulatedRouteStart = (
  trail: Trail | null,
  routePoints: Coordinate[]
): Coordinate => {
  const fallbackCenter: Coordinate =
    typeof trail?.center_lat === "number" && typeof trail.center_lng === "number"
      ? [trail.center_lat, trail.center_lng]
      : [-41.1734, -71.4752];

  return getRouteStart(routePoints, fallbackCenter);
};

export default function Screen04RouteMap() {
  const insets = useSafeAreaInsets();
  const isOffline = useIsOffline();
  const [offlineBannerHeight, setOfflineBannerHeight] = useState(48);
  const isFocused = useScreenFocused();
  const [activeSeconds, setActiveSeconds] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const { active, id, startedAt, offline } = useLocalSearchParams<{
    active?: string;
    id?: string;
    startedAt?: string;
    offline?: string;
  }>();
  const trailId = Number(id) || 1;
  const isActiveRoute = active === "1";
  const fallbackStartedAt = useMemo(() => Date.now(), []);
  const startedAtMs = Number(startedAt) || fallbackStartedAt;
  const [trail, setTrail] = useState<Trail | null>(null);
  const [weather, setWeather] = useState<TrailWeather | null>(null);
  const [reports, setReports] = useState<TrailReport[]>([]);
  const [showAllReports, setShowAllReports] = useState(false);
  const [isWifiConnected, setIsWifiConnected] = useState(false);
  const [hasInternetConnection, setHasInternetConnection] = useState(false);
  const [isContextLoading, setIsContextLoading] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [isMapInteracting, setIsMapInteracting] = useState(false);
  const [mapFooterHeight, setMapFooterHeight] = useState(250);
  const [focusedReportId, setFocusedReportId] = useState<number | null>(null);
  const [isChoosingReportLocation, setIsChoosingReportLocation] = useState(false);
  const [dismissedReportKey, setDismissedReportKey] = useState<string | null>(null);
  const [proximityHeight, setProximityHeight] = useState(110);
  const navigationProgressRef = useRef<{ context: string; progress: number | null; direction: 1 | -1 }>({ context: "", progress: null, direction: 1 });
  const announcedReportsRef = useRef(new Set<string>());
  const [isDownloaded, setIsDownloaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wearableRuntime, setWearableRuntime] =
    useState<WearableRuntimeStatus | null>(null);
  const [testingWearableScenario, setTestingWearableScenario] =
    useState<WearableSimulationScenario>("esfuerzo_moderado");
  const [testingWearableMessage, setTestingWearableMessage] = useState<string | null>(null);
  const [isSimulatingWearable, setIsSimulatingWearable] = useState(false);
  const [showWearablePanel, setShowWearablePanel] = useState(false);
  const [showCriticalWearableAlert, setShowCriticalWearableAlert] = useState(false);
  const [trackedDistanceMeters, setTrackedDistanceMeters] = useState(0);
  const [lastGpsRecordedAt, setLastGpsRecordedAt] = useState<number | null>(null);
  const [simulatedLiveLocation, setSimulatedLiveLocation] = useState<DeviceLocation | null>(null);
  const trackedDistanceMetersRef = useRef(0);

  useEffect(() => { setIsChoosingReportLocation(false); }, [trailId, startedAtMs, isActiveRoute]);

  useEffect(() => {
    let isMounted = true;

    const load = async () => {
      setIsLoading(true);
      setIsContextLoading(true);

      try {
        if (!isMounted) return;
        const context = await loadRouteContext(trailId, offline === "1");
        if (!isMounted) return;

        setTrail(context.trail);
        setReports(context.reports);
        setIsWifiConnected(context.hasWifi);
        setHasInternetConnection(context.hasInternet);
        setIsDownloaded(context.isDownloaded);
        setError(null);

        if (!context.hasInternet) {
          setWeather(null);
          return;
        }

        const weatherData = await getTrailWeather(trailId).catch(() => null);

        if (isMounted) {
          setWeather(weatherData);
        }
      } catch {
        if (!isMounted) return;

        const fallbackContext = await loadFallbackRouteContext(trailId);
        if (!isMounted) return;
        setTrail(fallbackContext.trail);
        setReports(fallbackContext.reports);
        setIsWifiConnected(fallbackContext.hasWifi);
        setHasInternetConnection(fallbackContext.hasInternet);
        setIsDownloaded(fallbackContext.isDownloaded);
        setWeather(null);
        setError(fallbackContext.error);
      } finally {
        if (!isMounted) return;

        setIsLoading(false);
        setIsContextLoading(false);
      }
    };

    void load().catch(() => {
      if (isMounted) setError("No pudimos cargar el mapa de este sendero.");
    });

    return () => {
      isMounted = false;
    };
  }, [trailId, offline]);

  // Refresh on return from a report and while the map is in the foreground.
  useEffect(() => {
    if (!isFocused || !trail || trail.id !== trailId || !hasInternetConnection || offline === "1" || isOffline) return;
    let active = true;
    let refreshing = false;
    const refresh = async () => {
      if (refreshing) return;
      refreshing = true;
      try {
        const fresh = await getTrailReports(trailId);
        if (active) setReports(fresh);
      } catch { /* Keep the last reports when the connection drops. */ }
      finally { refreshing = false; }
    };
    void refresh();
    const timer = setInterval(() => { void refresh(); }, 30000);
    return () => { active = false; clearInterval(timer); };
  }, [isFocused, trail?.id, trailId, hasInternetConnection, offline, isOffline]);

  useEffect(() => {
    if (!isFocused || !trail || !hasInternetConnection || isOffline || offline === "1") return;
    let active = true;
    const timer = setInterval(() => {
      void getTrailWeather(trailId).then(value => { if (active) setWeather(value); }).catch(() => { if (active) setWeather(null); });
    }, 15 * 60 * 1000);
    return () => { active = false; clearInterval(timer); };
  }, [isFocused, trail?.id, trailId, hasInternetConnection, isOffline, offline]);

  const reportAtCoordinate = ({ coordinate, perspective }: { coordinate: Coordinate; perspective: boolean }) => {
    setIsChoosingReportLocation(false);
    router.push({ pathname: "/reportar-terreno", params: {
      id: String(trailId), ...(isActiveRoute ? { startedAt: String(startedAtMs) } : {}),
      latitude: String(coordinate[0]), longitude: String(coordinate[1]), perspective: perspective ? "1" : "0",
    } });
  };

  const refreshWearableMetrics = useCallback(async () => {
    const state = await getRouteSession(trailId, startedAtMs);
    const elapsedMinutes = state ? Math.floor(activeRouteSeconds(state) / 60) : 0;
    const currentStatus = await getWearableRuntimeStatus(elapsedMinutes).catch(
      () => null
    );

    if (
      currentStatus?.connection.linked &&
      currentStatus.connection.provider !== "development_simulator"
    ) {
      await syncNativeWearableSampleWithStatus({
        startAt: startedAtMs,
        requireHeartRate: true,
      }).catch(() => null);
    }

    const nextStatus = await getWearableRuntimeStatus(elapsedMinutes).catch(
      () => currentStatus
    );

    return nextStatus;
  }, [startedAtMs, trailId]);

  useEffect(() => {
    if (!isActiveRoute) {
      setWearableRuntime(null);
      setShowCriticalWearableAlert(false);
      return;
    }

    let isMounted = true;

    const refreshIfMounted = () => {
      void refreshWearableMetrics().then((status) => {
        if (isMounted) setWearableRuntime(status);
      }).catch(() => {
        if (isMounted) setWearableRuntime(null);
      });
    };

    refreshIfMounted();
    const interval = setInterval(refreshIfMounted, 5_000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [isActiveRoute, refreshWearableMetrics]);

  useEffect(() => {
    if (wearableRuntime?.prediction?.level === "high") {
      setShowCriticalWearableAlert(true);
    }
  }, [wearableRuntime?.prediction?.level]);

  const routePoints = useMemo(
    () => parseRouteCoordinates(trail?.route_coordinates),
    [trail?.route_coordinates]
  );
  const simulatedStartLocation = useMemo(
    () => getSimulatedRouteStart(trail, routePoints),
    [routePoints, trail]
  );
  const {
    location: deviceLocation,
    isLoading: locationLoading,
    permissionDenied: locationPermissionDenied,
    isTestingLocation,
  } = useDeviceLocation(isActiveRoute, simulatedStartLocation);
  const location = isTestingLocation ? simulatedLiveLocation ?? deviceLocation : deviceLocation;
  const [isFallCheckVisible, setIsFallCheckVisible] = useState(false);
  useFallDetection(isActiveRoute && isFocused && !isPaused && !isFallCheckVisible, () => {
    Vibration.vibrate([0, 500, 250, 500]);
    setIsFallCheckVisible(true);
  });
  const openSosAfterFall = () => {
    setIsFallCheckVisible(false);
    router.push({
      pathname: "/confirmar-sos",
      params: { id: String(trailId), startedAt: String(startedAtMs), sendSms: "1",
        ...(isTestingLocation ? { simulated: "1" } : {}) },
    });
  };

  useEffect(() => {
    trackedDistanceMetersRef.current = trackedDistanceMeters;
  }, [trackedDistanceMeters]);

  useEffect(() => {
    if (!isActiveRoute || !isFocused || locationLoading) return;
    let mounted = true;
    const refresh = async () => {
      const state = await getRouteSession(trailId, startedAtMs);
      const summary = state?.simulated
        ? getSimulatedRouteTrackingSummary(trailId, startedAtMs)
        : await getRouteTrackingSummary(trailId, startedAtMs);
      if (!mounted) return;
      setTrackedDistanceMeters(summary.distanceMeters);
      trackedDistanceMetersRef.current = summary.distanceMeters;
      setLastGpsRecordedAt(summary.lastRecordedAt);
      if (summary.lastPoint?.simulated) setSimulatedLiveLocation({ coordinate: [summary.lastPoint.latitude, summary.lastPoint.longitude], accuracy: 0, timestamp: summary.lastPoint.recordedAt });
      if (state) { setActiveSeconds(activeRouteSeconds(state)); setIsPaused(state.state === "paused"); }
      if (state?.state === "completed") router.replace("/mis-actividades");
    };
    void ensureRouteSession(trailId, startedAtMs, isTestingLocation).then(refresh).catch((error) => {
      if (error instanceof DepartureMessageRequiredError) router.replace({ pathname: "/trail-start", params: { id: String(trailId) } });
      else setError(userMessage(error, "No pudimos cargar el recorrido. Intentá nuevamente."));
    });
    const timer = setInterval(() => { void refresh().catch(() => undefined); }, 1000);
    return () => { mounted = false; clearInterval(timer); };
  }, [isActiveRoute, isFocused, startedAtMs, trailId, isTestingLocation, locationLoading]);

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
    return getRouteProgressMeters(location.coordinate, routePoints,
      trail?.provenance?.route_type === "out_and_back" ? trackedDistanceMeters : undefined);
  }, [isActiveRoute, location, routePoints, trackedDistanceMeters, trail?.provenance?.route_type]);
  const completedDistanceMeters = trackedDistanceMeters;
  const isOffRoute =
    !isTestingLocation &&
    routeDeviationMeters !== null &&
    routeDeviationMeters > ROUTE_DEVIATION_WARNING_METERS;
  const reportRanges = useMemo(() => buildReportRouteRanges(reports, trailId, routePoints), [reports, trailId, routePoints]);
  const progressContext = `${trailId}:${startedAtMs}`;
  const previousNavigation = navigationProgressRef.current;
  const previousProgress = previousNavigation.context === progressContext ? previousNavigation.progress : null;
  const direction: 1 | -1 = previousProgress != null && traveledMeters != null && Math.abs(traveledMeters - previousProgress) >= 10
    ? traveledMeters >= previousProgress ? 1 : -1 : previousNavigation.context === progressContext ? previousNavigation.direction : 1;
  useEffect(() => {
    const previous = navigationProgressRef.current;
    const keepAnchor = previous.context === progressContext && previous.progress != null && traveledMeters != null && Math.abs(traveledMeters - previous.progress) < 10;
    navigationProgressRef.current = { context: progressContext, progress: keepAnchor ? previous.progress : traveledMeters, direction };
  }, [progressContext, traveledMeters, direction]);
  const upcomingReport = useMemo(() => getUpcomingReport(reportRanges, traveledMeters, direction), [reportRanges, traveledMeters, direction]);
  const upcomingKey = upcomingReport ? `${progressContext}:${upcomingReport.report.id}:${upcomingReport.occurrence}:${direction}` : null;
  const showUpcomingReport = Boolean(upcomingReport && isActiveRoute && isFocused && !isPaused && !isOffRoute &&
    !isLoading && (location?.accuracy == null || location.accuracy <= 80) && dismissedReportKey !== upcomingKey);
  useEffect(() => {
    if (!showUpcomingReport || !upcomingReport || !upcomingKey || announcedReportsRef.current.has(upcomingKey) || isTestingLocation) return;
    announcedReportsRef.current.add(upcomingKey);
    if (upcomingReport.report.blocks_path || ["Alta", "Critica"].includes(upcomingReport.report.severity)) Vibration.vibrate(180);
  }, [showUpcomingReport, upcomingKey, upcomingReport, isTestingLocation]);
  const refreshReports = async () => setReports(await getTrailReports(trailId));
  const simulateWearableScenario = async (scenario: WearableSimulationScenario) => {
    if (isSimulatingWearable) return;

    if (wearableRuntime?.status === "requires_consent") {
      setTestingWearableMessage("Activa datos sensibles en Perfil para ver el análisis de lecturas.");
      return;
    }

    setTestingWearableScenario(scenario);
    setIsSimulatingWearable(true);
    try {
      await createDevelopmentMetricSequence(scenario, 8);
      const status = await refreshWearableMetrics();
      setWearableRuntime(status);
      setTestingWearableMessage(
        `Simulacion ${routeSimulationOptions.find((option) => option.id === scenario)?.title.toLowerCase()} aplicada (solo en memoria, no se guarda).`
      );
    } catch {
      setTestingWearableMessage("No pudimos generar la simulacion wearable.");
    } finally {
      setIsSimulatingWearable(false);
    }
  };
  const activeTop = Math.max(22, insets.top + 14) + (isOffline ? offlineBannerHeight + 8 : 0);
  const activeBannerTop = activeTop + 68;
  const hasStatusBanner =
    isLoading || Boolean(error) || (!isLoading && !error && locationPermissionDenied);
  const primaryBannerHeight = isOffRoute ? 76 : hasStatusBanner ? 64 : 0;
  const testingBannerTop = activeBannerTop + primaryBannerHeight + 10;
  const testingBannerHeight = isTestingLocation ? 158 : 0;
  const mapControlsTop =
    activeBannerTop + primaryBannerHeight + testingBannerHeight + 18 + (showUpcomingReport ? proximityHeight + 8 : 0);
  const proximityTop = activeBannerTop + primaryBannerHeight + testingBannerHeight + 10;
  const hasBlockingReport = reports.some((report) => isActiveReport(report) && report.blocks_path);
  const severeReports = reports.filter(isActiveReport).filter((report) =>
    ["Alta", "Critica"].includes(report.severity)
  ).length;
  const simulatedWearableLabel = wearableRuntime?.latestSample?.simulated ? " (simulado)" : "";

  if (isActiveRoute) {
    return (
      <SafeAreaView edges={["top", "bottom"]} style={styles.activeShell}>
        {isOffline ? <View
          style={{ position: "absolute", top: insets.top + 4, left: 14, right: 14, zIndex: 30 }}
          onLayout={event => setOfflineBannerHeight(event.nativeEvent.layout.height)}
        >
          <OfflineConnectionBanner style={{ marginHorizontal: 0, marginBottom: 0 }} />
        </View> : null}
        <TrailMap
          offlineOnly={offline === "1"}
          trail={trail}
          reports={reports}
          focusedReportId={focusedReportId}
          onReportClosed={() => setFocusedReportId(null)}
          onReportsChanged={refreshReports}
          onReportCoordinate={reportAtCoordinate}
          reportSelectionActive={isChoosingReportLocation}
          weather={weather}
          fitRoute
          immersive
          initialPerspective={false}
          navigationMode
          bottomOverlayInset={mapFooterHeight + 8}
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
            <View style={styles.activeTitleCopy}>
              <Text style={styles.activeEyebrow}>{isPaused ? "Ruta en pausa" : `En curso · ${Math.floor(activeSeconds / 60)} min activos`}</Text>
              <Text numberOfLines={1} style={styles.activeTitle}>
                {trail?.name || "Mapa del recorrido"}
              </Text>
            </View>
            <MiSenderoLogo tone="dark" markSize={28} showWordmark={false} />
          </View>
        </View>
        {showUpcomingReport && upcomingReport ? <View accessibilityLiveRegion="polite" onLayout={event => setProximityHeight(event.nativeEvent.layout.height)}
          style={[styles.proximityBanner, { top: proximityTop }]}>
          <View style={styles.proximityContent}>
            <Ionicons aria-hidden accessible={false} name="warning" size={22} color={upcomingReport.report.blocks_path ? colors.danger : colors.orange} />
            <View style={styles.proximityCopy}>
              <Text accessibilityRole="alert" style={styles.proximityTitle}>{upcomingReport.report.blocks_path ? "Aviso de paso bloqueado" : "Aviso en tu recorrido"}</Text>
              <Text style={styles.proximityBody}>{upcomingReport.distanceMeters === 0 ? "Entrando en la zona reportada" : `A unos ${formatDistance(upcomingReport.distanceMeters)} por el sendero`} · ubicación aproximada</Text>
              <Text style={styles.proximityBody}>{upcomingReport.report.issue_summary}</Text>
            </View>
          </View>
          <View style={styles.proximityActions}>
            <Pressable accessibilityRole="button" onPress={() => setFocusedReportId(upcomingReport.report.id)} style={styles.proximityButton}><Text style={styles.proximityButtonText}>Ver aviso</Text></Pressable>
            <Pressable accessibilityRole="button" accessibilityLabel="Ocultar aviso cercano" onPress={() => setDismissedReportKey(upcomingKey)} style={styles.proximityButton}><Text style={styles.proximityButtonText}>Ocultar</Text></Pressable>
          </View>
        </View> : null}

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
                  Modo prueba activo
                </Text>
                <Text style={styles.testingBannerHint}>
                  Ubicacion y reloj simulados: no se guardan.
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
                : testingWearableMessage || "Tocá un escenario para probar los avisos de lectura."}
            </Text>
          </View>
        ) : null}

        {wearableRuntime?.prediction && wearableRuntime.latestSample && !showWearablePanel ? (
          <Pressable
            accessibilityLabel="Ver metricas del reloj"
            accessibilityRole="button"
            onPress={() => setShowWearablePanel(true)}
            style={[
              styles.wearableBanner,
              wearableRuntime.prediction.level === "high" && styles.wearableBannerHigh,
              wearableRuntime.prediction.level === "caution" && styles.wearableBannerCaution,
              { bottom: Math.max(92, insets.bottom + 86) },
            ]}
          >
            <Ionicons
              name="pulse-outline"
              size={18}
              color={
                wearableRuntime.prediction.level === "high"
                  ? colors.danger
                  : colors.green
              }
            />
            <View style={styles.wearableText}>
              <Text style={styles.wearableTitle}>
                {wearableRuntime.prediction.coverage === "oxygen_only" ? `${wearableRuntime.latestSample.oxygenSaturation}% SpO₂` : `${wearableRuntime.latestSample.heartRateBpm} bpm`}{simulatedWearableLabel} - {wearableRuntime.prediction.title}
              </Text>
              <Text numberOfLines={2} style={styles.wearableBody}>
                {wearableRuntime.prediction.message}
              </Text>
            </View>
          </Pressable>
        ) : null}

        <CriticalWearableModal
          isVisible={
            showCriticalWearableAlert &&
            wearableRuntime?.prediction?.level === "high"
          }
          message={wearableRuntime?.prediction?.message}
          onSendSos={() =>
            {
              setShowCriticalWearableAlert(false);
              router.push({
              pathname: "/confirmar-sos",
              // An alert raised by simulated data opens the SOS in test mode (nothing is sent).
              params: { id: String(trailId), startedAt: String(startedAtMs), sendSms: "1",
                ...(wearableRuntime?.latestSample?.simulated ? { simulated: "1" } : {}) },
              });
            }
          }
          simulated={Boolean(wearableRuntime?.latestSample?.simulated) || isTestingLocation}
          title={wearableRuntime?.prediction?.title && `${wearableRuntime.prediction.title}${simulatedWearableLabel}`}
        />

        <FallCheckModal
          isVisible={isFallCheckVisible}
          onOk={() => setIsFallCheckVisible(false)}
          onSendSos={openSosAfterFall}
          simulated={isTestingLocation}
        />

        {showWearablePanel ? (
          <WearableRealtimePanel
            bottom={Math.max(190, insets.bottom + 184)}
            runtime={wearableRuntime}
            onClose={() => setShowWearablePanel(false)}
          />
        ) : null}

        <View onLayout={event => setMapFooterHeight(event.nativeEvent.layout.height)} style={[styles.activeFooter, { paddingBottom: Math.max(16, insets.bottom + 10) }]}>
          <FieldAssessmentPanel trailId={trailId} startedAt={startedAtMs} simulated={isTestingLocation} compact />
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
                  <Text style={styles.wearableEyebrow}>
                    {wearableRuntime.latestSample.simulated ? "Actividad · datos de prueba" : "Resumen de actividad"}
                  </Text>
                  <Text style={styles.wearableTitle}>
                    {wearableRuntime.prediction.coverage === "oxygen_only" ? `${wearableRuntime.latestSample.oxygenSaturation}% SpO₂` : `${wearableRuntime.latestSample.heartRateBpm} bpm`}{simulatedWearableLabel} - {wearableRuntime.prediction.title}
                  </Text>
                </View>
              </View>
              <View style={styles.wearableMetricRow}>
                <WearableChip label="Avisos de lectura" value={wearableRuntime.prediction.readingAlert} />
                {wearableRuntime.prediction.cardiacLoad ? <WearableChip label="Carga por pulso" value={wearableRuntime.prediction.cardiacLoad} /> : null}
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
                    String(Math.round(trackedDistanceMeters)),
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
              <Text style={styles.finishRouteHint}>
                {isTestingLocation ? "Simulacion: no se guarda como actividad" : "Guardar actividad y dejar opinion"}
              </Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.white} />
          </Pressable>

          <Pressable
            onPress={() => router.push("/reloj-salud")}
            style={[
              styles.wearableActionButton,
              getWearableActionToneStyle(wearableRuntime),
            ]}
          >
            <View style={styles.wearableActionIcon}>
              <Ionicons
                name="watch-outline"
                size={21}
                color={getWearableActionIconColor(wearableRuntime)}
              />
            </View>
            <View style={styles.wearableActionTextBox}>
              <Text
                style={[
                  styles.wearableActionLabel,
                  wearableRuntime?.prediction?.level === "high" && styles.wearableActionLabelDanger,
                ]}
              >
                Reloj
              </Text>
              <Text
                style={[
                  styles.wearableActionHint,
                  wearableRuntime?.prediction?.level === "high" && styles.wearableActionHintDanger,
                ]}
              >
                {getWearableActionHint(wearableRuntime)}
              </Text>
            </View>
            <Ionicons
              name="chevron-forward"
              size={18}
              color={getWearableActionIconColor(wearableRuntime)}
            />
          </Pressable>

          <View style={styles.quickActionsRow}>
            <Pressable
              onPress={() => {
                if (isPaused) { void resumeRouteSession(trailId, startedAtMs); return; }
                void pauseRouteSession(trailId, startedAtMs).then(() =>
                router.push({
                  pathname: "/descanso",
                  params: {
                    id: String(trailId),
                    startedAt: String(startedAtMs),
                    traveledMeters: String(Math.round(trackedDistanceMeters)),
                    routeProgressMeters: traveledMeters !== null ? String(Math.round(traveledMeters)) : "",
                    totalMeters:
                      totalRouteMeters > 0 ? String(Math.round(totalRouteMeters)) : "",
                  },
                })).catch(() => setError("No pudimos guardar la pausa."));
              }}
              style={styles.activeAction}
            >
              <Ionicons name="pause-outline" size={20} color={colors.greenDark} />
              <Text style={styles.activeActionText}>{isPaused ? "Reanudar" : "Pausa"}</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={isChoosingReportLocation ? "Cancelar selección del reporte" : "Seleccionar punto para reportar"}
              accessibilityState={{ selected: isChoosingReportLocation }}
              disabled={routePoints.length < 2}
              onPress={() => {
                setFocusedReportId(null);
                setIsChoosingReportLocation(value => !value);
              }}
              style={[styles.activeAction, isChoosingReportLocation && styles.activeActionSelected,
                routePoints.length < 2 && { opacity: 0.5 }]}
            >
              <Ionicons name={isChoosingReportLocation ? "close-outline" : "megaphone-outline"} size={20} color={colors.greenDark} />
              <Text style={styles.activeActionText}>{isChoosingReportLocation ? "Cancelar" : "Reporte"}</Text>
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
                  params: { id: String(trailId), startedAt: String(startedAtMs), sendSms: "1" },
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
              {isTestingLocation ? "GPS simulado" : "GPS"}: {formatDistance(trackedDistanceMeters)}
            </Text>
            <Text style={styles.activeTelemetryText}>
              {lastGpsRecordedAt ? (isTestingLocation ? "Punto simulado (no se guarda)" : "Ultimo punto guardado") : "Esperando punto GPS"}
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
        scrollEnabled={!isMapInteracting}
        contentContainerStyle={[
          styles.scrollContent,
          { paddingBottom: Math.max(24, insets.bottom + 18) },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {isLoading ? <Text style={styles.statusText}>Cargando mapa...</Text> : null}
        {error ? <Text style={styles.statusText}>{error}</Text> : null}

        <TrailMap
          offlineOnly={offline === "1"}
          trail={trail}
          reports={reports}
          onReportsChanged={refreshReports}
          weather={weather}
          allowSatellite={hasInternetConnection}
          onInteractionChange={setIsMapInteracting}
        />

        <InfoCard style={styles.progressCard} icon="map-outline">
          <Text style={styles.cardTitle}>Ruta lista</Text>
          <Text style={styles.cardText}>
            Usa Terreno para ver curvas de nivel o 3D para revisar la ruta con relieve.
          </Text>
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
                  {weather ? `Riesgo ${weather.risk_level}` : isContextLoading ? "Consultando" : "Pronóstico no disponible"}
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
              {(showAllReports ? reports : reports.slice(0, 3)).map((report) => (
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
                      Observado: {formatReportDateTime(report.observed_at || report.created_at)}
                      {" · Recibido: "}{formatReportDateTime(report.received_at || report.created_at)}
                    </Text>
                    {report.details ? (
                      <Text numberOfLines={2} style={styles.reportDetails}>
                        {report.details}
                      </Text>
                    ) : null}
                    <ReportFeedbackControls report={report} onChanged={refreshReports} />
                    <ReportActions report={report} onChanged={async () => setReports(await getTrailReports(trailId))} />
                  </View>
                </View>
              ))}
              {reports.length > 3 ? <PrimaryButton tone="secondary"
                label={showAllReports ? "Ver menos reportes" : `Ver todos los reportes (${reports.length})`}
                onPress={() => setShowAllReports(value => !value)} /> : null}
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
            disabled={trail?.provenance?.mapping?.navigation_ready === false}
            onPress={() =>
              router.push({
                pathname: "/trail-start",
                params: { id: String(trailId) },
              })
            }
          />
          <PrimaryButton
            label="Reloj y salud"
            icon="watch-outline"
            tone="secondary"
            onPress={() => router.push("/reloj-salud")}
          />
          {!isDownloaded ? (
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
          ) : null}
        </View>
      </ScrollView>
    </ScreenShell>
  );
}

function WearableRealtimePanel({
  bottom,
  onClose,
  runtime,
}: {
  bottom: number;
  onClose: () => void;
  runtime: WearableRuntimeStatus | null;
}) {
  const latest = runtime?.latestSample ?? null;
  const prediction = runtime?.prediction ?? null;

  return (
    <View style={[styles.wearablePanel, { bottom }]}>
      <View style={styles.wearablePanelHeader}>
        <View style={styles.wearablePanelTitleBox}>
          <Ionicons name="pulse-outline" size={18} color={colors.green} />
          <Text style={styles.wearablePanelTitle}>
            {latest?.simulated ? "Metricas simuladas (pruebas)" : "Metricas del reloj"}
          </Text>
        </View>
        <Pressable
          accessibilityLabel="Cerrar metricas del reloj"
          accessibilityRole="button"
          onPress={onClose}
          style={styles.wearableCloseButton}
        >
          <Ionicons name="close" size={18} color={colors.ink} />
        </Pressable>
      </View>

      <Text style={styles.wearablePanelStatus}>
        {getWearableRealtimeStatus(runtime)}
      </Text>

      {latest ? (
        <View style={styles.wearableMetricGrid}>
          <WearableMetric label="FC" value={`${latest.heartRateBpm ?? "--"} bpm`} />
          <WearableMetric
            label="Velocidad"
            value={latest.speedKmh !== null ? `${latest.speedKmh} km/h` : "--"}
          />
          <WearableMetric
            label="Oxigeno"
            value={
              latest.oxygenSaturation !== null ? `${latest.oxygenSaturation}%` : "--"
            }
          />
          <WearableMetric label="Pasos" value={latest.steps ? String(latest.steps) : "--"} />
        </View>
      ) : null}

      <View
        style={[
          styles.wearableWarningBox,
          prediction?.level === "high" && styles.wearableWarningHigh,
          prediction?.level === "caution" && styles.wearableWarningCaution,
        ]}
      >
        <Ionicons
          name={prediction?.level === "high" ? "alert-circle-outline" : "information-circle-outline"}
          size={18}
          color={prediction?.level === "high" ? colors.danger : colors.green}
        />
        <View style={styles.wearableWarningText}>
          <Text style={styles.wearableWarningTitle}>
            {prediction?.title ?? "Esperando lecturas recientes"}
          </Text>
          <Text style={styles.wearableWarningBody}>
            {prediction?.message ??
              "Cuando haya metricas autorizadas, la app va a mostrar alertas de esfuerzo durante la ruta."}
          </Text>
        </View>
      </View>
    </View>
  );
}

function CriticalWearableModal({
  isVisible,
  message,
  onSendSos,
  simulated,
  title,
}: {
  isVisible: boolean;
  message?: string;
  onSendSos: () => void;
  simulated: boolean;
  title?: string;
}) {
  return (
    <Modal animationType="fade" transparent visible={isVisible}>
      <View style={styles.criticalModalOverlay}>
        <View style={styles.criticalModalCard}>
          <View style={styles.criticalModalIcon}>
            <Ionicons name="alert-circle-outline" size={34} color={colors.danger} />
          </View>
          <Text style={styles.criticalModalTitle}>
            {title ?? "Situacion critica"}
          </Text>
          <Text style={styles.criticalModalBody}>
            {message ??
              "Las metricas del reloj muestran una senal critica. Detenete en un lugar seguro y evalua pedir ayuda."}
          </Text>
          {simulated ? (
            <Text style={styles.criticalModalBody}>Modo prueba: el SOS no se envía.</Text>
          ) : null}
          <View style={styles.criticalModalActions}>
            <Pressable onPress={onSendSos} style={styles.criticalModalPrimary}>
              <Ionicons name="alert-circle-outline" size={18} color={colors.white} />
              <Text style={styles.criticalModalPrimaryText}>
                {simulated ? "Probar SOS (no se envía)" : "Enviar mensaje de ayuda"}
              </Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

export const FALL_CHECK_SECONDS = 30;

function FallCheckModal({
  isVisible,
  onOk,
  onSendSos,
  simulated,
}: {
  isVisible: boolean;
  onOk: () => void;
  onSendSos: () => void;
  simulated: boolean;
}) {
  const [secondsLeft, setSecondsLeft] = useState(FALL_CHECK_SECONDS);
  const sendSos = useRef(onSendSos);
  sendSos.current = onSendSos;
  useEffect(() => {
    if (!isVisible) { setSecondsLeft(FALL_CHECK_SECONDS); return; }
    const timer = setInterval(() => setSecondsLeft((value) => value - 1), 1000);
    return () => clearInterval(timer);
  }, [isVisible]);
  // Without an answer, open the SOS so the message to the contact is ready to send.
  useEffect(() => { if (isVisible && secondsLeft <= 0) sendSos.current(); }, [isVisible, secondsLeft]);
  return (
    <Modal animationType="fade" transparent visible={isVisible}>
      <View style={styles.criticalModalOverlay}>
        <View style={styles.criticalModalCard}>
          <View style={styles.criticalModalIcon}>
            <Ionicons name="alert-circle-outline" size={34} color={colors.danger} />
          </View>
          <Text accessibilityRole="alert" style={styles.criticalModalTitle}>¿Estás bien?</Text>
          <Text style={styles.criticalModalBody}>
            {`Detectamos un posible golpe seguido de inmovilidad. Si no respondés en ${Math.max(0, secondsLeft)} s, se abre el SOS con el mensaje para tu contacto.`}
          </Text>
          {simulated ? (
            <Text style={styles.criticalModalBody}>Modo prueba: el SOS no se envía.</Text>
          ) : null}
          <View style={styles.criticalModalActions}>
            <Pressable accessibilityRole="button" onPress={onSendSos} style={styles.criticalModalPrimary}>
              <Ionicons name="alert-circle-outline" size={18} color={colors.white} />
              <Text style={styles.criticalModalPrimaryText}>Pedir ayuda</Text>
            </Pressable>
            <Pressable accessibilityRole="button" onPress={onOk} style={styles.fallModalSecondary}>
              <Text style={styles.fallModalSecondaryText}>Estoy bien</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

function WearableMetric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.wearableMetricItem}>
      <Text style={styles.wearableMetricLabel}>{label}</Text>
      <Text style={styles.wearableMetricValue}>{value}</Text>
    </View>
  );
}

function getWearableRealtimeStatus(runtime: WearableRuntimeStatus | null) {
  if (!runtime) return "Buscando tu reloj...";
  if (runtime.status === "requires_consent") {
    return "Activa Usar datos sensibles en Privacidad e IA.";
  }
  if (runtime.status === "not_linked") {
    return "No hay reloj o sensor vinculado para esta cuenta.";
  }
  if (runtime.status === "stale_data") return "Lectura anterior: no se usa para estimar tu estado actual.";
  if (runtime.status === "waiting_for_native_data") {
    return "Conexion habilitada. Esperando una lectura reciente.";
  }

  return `${runtime.displayName} conectado. Actualizando durante la ruta.`;
}

function getWearableActionHint(runtime: WearableRuntimeStatus | null) {
  if (!runtime) return "Consultando conexion";
  if (runtime.status === "linked" && runtime.latestSample?.heartRateBpm) {
    return `${runtime.latestSample.heartRateBpm} bpm - ${runtime.displayName}`;
  }
  if (runtime.status === "requires_consent") return "Requiere permiso";
  if (runtime.status === "not_linked") return "No vinculado";
  if (runtime.status === "stale_data") return "Datos desactualizados";
  if (runtime.status === "waiting_for_native_data") return "Esperando metricas";
  return runtime.displayName;
}

function getWearableActionToneStyle(runtime: WearableRuntimeStatus | null) {
  if (runtime?.prediction?.level === "high") return styles.wearableActionButtonDanger;
  if (runtime?.prediction?.level === "caution") return styles.wearableActionButtonCaution;
  if (runtime?.prediction?.level === "normal") return styles.wearableActionButtonNormal;
  return null;
}

function getWearableActionIconColor(runtime: WearableRuntimeStatus | null) {
  if (runtime?.prediction?.level === "high") return colors.danger;
  if (runtime?.prediction?.level === "caution") return "#D97706";
  return colors.greenDark;
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
      <Ionicons aria-hidden accessible={false} name={icon} size={18} color={colors.green} />
      <View style={styles.weatherMetricCopy}>
        <Text style={styles.weatherLabel}>{label}</Text>
        <Text style={styles.weatherValue}>{value}</Text>
      </View>
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
  proximityBanner: { ...surfaceShadows.floating, position: "absolute", left: 14, right: 14, borderRadius: 17, padding: 12, gap: 6,
    backgroundColor: "#FFF7E5", zIndex: 15 },
  proximityContent: { flexDirection: "row", alignItems: "flex-start", gap: 8 },
  proximityCopy: { flex: 1, minWidth: 0, gap: 2 },
  proximityTitle: { fontSize: 14, fontWeight: "800", color: colors.ink },
  proximityBody: { fontSize: 12, lineHeight: 17, color: colors.ink },
  proximityActions: { flexDirection: "row", gap: 8 },
  proximityButton: { minHeight: 44, paddingHorizontal: 15, borderRadius: 12, backgroundColor: "#FFFFFF", justifyContent: "center" },
  proximityButtonText: { color: colors.greenDark, fontWeight: "800", fontSize: 12 },
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
    ...surfaceShadows.floating,
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.96)",
    borderRadius: 18,
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  activeTitleBox: {
    ...surfaceShadows.floating,
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.96)",
    borderRadius: 18,
    flex: 1,
    flexDirection: "row",
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  activeTitleCopy: { flex: 1, minWidth: 0 },
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
    ...surfaceShadows.floating,
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
    ...surfaceShadows.floating,
    alignItems: "center",
    backgroundColor: "rgba(255,244,242,0.97)",
    borderRadius: 18,
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
    ...surfaceShadows.floating,
    backgroundColor: "rgba(223,243,231,0.97)",
    borderRadius: 16,
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
    borderRadius: 12,
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
    borderRadius: 16,
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
  wearableBanner: {
    ...surfaceShadows.floating,
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.96)",
    borderRadius: 16,
    flexDirection: "row",
    gap: 9,
    left: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
    position: "absolute",
    right: 14,
    zIndex: 19,
  },
  wearableBannerCaution: {
    backgroundColor: "rgba(255,244,216,0.97)",
  },
  wearableBannerHigh: {
    backgroundColor: "rgba(255,244,242,0.97)",
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
    backgroundColor: colors.soft,
    borderRadius: 12,
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
  wearablePanel: {
    ...surfaceShadows.floating,
    backgroundColor: "rgba(255,255,255,0.98)",
    borderRadius: 18,
    left: 14,
    padding: 12,
    position: "absolute",
    right: 14,
    zIndex: 22,
  },
  wearablePanelHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  wearablePanelTitleBox: {
    alignItems: "center",
    flex: 1,
    flexDirection: "row",
    gap: 7,
    minWidth: 0,
  },
  wearablePanelTitle: {
    color: colors.ink,
    flex: 1,
    fontSize: 15,
    fontWeight: "900",
  },
  wearableCloseButton: {
    alignItems: "center",
    backgroundColor: colors.page,
    borderRadius: 14,
    height: 32,
    justifyContent: "center",
    width: 32,
  },
  wearablePanelStatus: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "800",
    lineHeight: 17,
    marginTop: 7,
  },
  wearableMetricGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 10,
  },
  wearableMetricItem: {
    backgroundColor: colors.soft,
    borderRadius: 12,
    flexBasis: "47%",
    flexGrow: 1,
    minHeight: 54,
    minWidth: 118,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  wearableMetricLabel: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "800",
  },
  wearableMetricValue: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
    marginTop: 3,
  },
  wearableWarningBox: {
    alignItems: "flex-start",
    backgroundColor: colors.primarySoft,
    borderRadius: 14,
    flexDirection: "row",
    gap: 8,
    marginTop: 10,
    padding: 10,
  },
  wearableWarningCaution: {
    backgroundColor: "rgba(255,244,216,0.97)",
  },
  wearableWarningHigh: {
    backgroundColor: "rgba(255,244,242,0.97)",
  },
  wearableWarningText: {
    flex: 1,
    minWidth: 0,
  },
  wearableWarningTitle: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "900",
  },
  wearableWarningBody: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "700",
    lineHeight: 16,
    marginTop: 3,
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
  wearableActionButton: {
    alignItems: "center",
    backgroundColor: colors.primarySoft,
    borderColor: colors.border,
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: "row",
    gap: 10,
    marginTop: 10,
    minHeight: 56,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  wearableActionButtonActive: {
    backgroundColor: colors.mint,
    borderColor: colors.green,
  },
  wearableActionButtonNormal: {
    backgroundColor: colors.mint,
    borderColor: colors.green,
  },
  wearableActionButtonCaution: {
    backgroundColor: "rgba(255,244,216,0.98)",
    borderColor: "rgba(217,119,6,0.44)",
  },
  wearableActionButtonDanger: {
    backgroundColor: "rgba(255,244,242,0.98)",
    borderColor: "rgba(216,76,63,0.54)",
  },
  wearableActionIcon: {
    alignItems: "center",
    backgroundColor: colors.white,
    borderRadius: 15,
    height: 36,
    justifyContent: "center",
    width: 36,
  },
  wearableActionTextBox: {
    flex: 1,
    minWidth: 0,
  },
  wearableActionLabel: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "900",
  },
  wearableActionHint: {
    color: colors.greenDark,
    fontSize: 11,
    fontWeight: "800",
    marginTop: 2,
  },
  wearableActionLabelDanger: {
    color: colors.danger,
  },
  wearableActionHintDanger: {
    color: colors.danger,
  },
  criticalModalOverlay: {
    alignItems: "center",
    backgroundColor: "rgba(16,24,20,0.52)",
    flex: 1,
    justifyContent: "center",
    padding: 20,
  },
  criticalModalCard: {
    alignItems: "center",
    backgroundColor: colors.white,
    borderRadius: 22,
    maxWidth: 420,
    padding: 18,
    width: "100%",
  },
  criticalModalIcon: {
    alignItems: "center",
    backgroundColor: "rgba(255,244,242,1)",
    borderRadius: 999,
    height: 62,
    justifyContent: "center",
    width: 62,
  },
  criticalModalTitle: {
    color: colors.danger,
    fontSize: 20,
    fontWeight: "900",
    marginTop: 12,
    textAlign: "center",
  },
  criticalModalBody: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "700",
    lineHeight: 20,
    marginTop: 8,
    textAlign: "center",
  },
  criticalModalActions: {
    alignSelf: "stretch",
    gap: 9,
    marginTop: 16,
  },
  criticalModalPrimary: {
    alignItems: "center",
    backgroundColor: colors.danger,
    borderRadius: 17,
    flexDirection: "row",
    gap: 7,
    justifyContent: "center",
    minHeight: 50,
  },
  criticalModalPrimaryText: {
    color: colors.white,
    fontSize: 15,
    fontWeight: "900",
  },
  fallModalSecondary: {
    alignItems: "center",
    borderColor: colors.ink,
    borderRadius: 17,
    borderWidth: 1.5,
    justifyContent: "center",
    minHeight: 50,
  },
  fallModalSecondaryText: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
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
  activeActionSelected: {
    backgroundColor: colors.mint,
    borderColor: colors.green,
    borderWidth: 1,
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
    marginBottom: 12,
    marginTop: 2,
  },
  previewCard: {
    marginBottom: 12,
    padding: 14,
  },
  sectionHeader: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 12,
    justifyContent: "space-between",
    marginBottom: 10,
  },
  sectionHeaderText: {
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
    alignItems: "center",
    backgroundColor: colors.soft,
    borderRadius: 14,
    flexBasis: "47%",
    flexDirection: "row",
    flexGrow: 1,
    gap: 8,
    minWidth: 110,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  weatherMetricCopy: {
    flex: 1,
    minWidth: 0,
  },
  weatherLabel: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "800",
  },
  weatherValue: {
    color: colors.ink,
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
    borderRadius: 14,
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
