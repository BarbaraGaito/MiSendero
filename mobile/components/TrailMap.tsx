import { useNetworkState } from "expo-network";
import { router } from "expo-router";
import { getOfflineTilePlanForTrail } from "../../services/mapTileCache";
﻿import { Ionicons } from "@expo/vector-icons";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Image,
  LayoutChangeEvent,
  PanResponder,
  Pressable,
  StyleSheet,
  Text,
  View,
  ViewStyle,
} from "react-native";
import Svg, { Circle, Path } from "react-native-svg";
import { Trail, TrailReport, TrailWeather } from "../../types";
import { getReportMapMarkers } from "../../services/reportMapMarkers";
import {
  Coordinate,
  formatKilometers,
  getClosestPointOnRoute,
  getRouteStart,
  parseRouteCoordinates,
} from "../../services/geoUtils";
import {
  getTileRemoteUrl,
  resolveCachedTileUri,
} from "../../services/mapTileCache";
import {
  MAX_TERRAIN_SCALE,
  MIN_TERRAIN_SCALE,
  clampTerrainScale,
  getPinchZoomDelta,
} from "../../services/mapGestures";
import { OPEN_METEO_ELEVATION_ATTRIBUTION } from "../../services/terrainElevation";
import { useDeviceLocation } from "../hooks/useDeviceLocation";
import {
  TerrainElevationState,
  useTerrainElevation,
} from "../hooks/useTerrainElevation";
import { colors } from "./MiSenderoUI";
import { Terrain3DScene, Terrain3DSceneHandle, TerrainMapMarker } from "./Terrain3DScene";
import { buildTerrainSceneModel, coordinateToTerrainScenePoint } from "./terrainSceneModel";
import { BasicOfflineMap, containsMapCoordinate, readBasicOfflineMap } from "../../services/basicOfflineMap";
import { BasicMapLayer } from "./BasicMapLayer";

type MapLayer = "standard" | "terrain" | "satellite";

type MapTile = {
  key: string;
  url: string;
  left: number;
  top: number;
  layer: MapLayer;
  zoom: number;
  x: number;
  y: number;
};

type MapTouch = {
  pageX: number;
  pageY: number;
};

type ScreenPoint = {
  x: number;
  y: number;
};

type TerrainPath = {
  key: string;
  path: string;
  color: string;
  opacity: number;
  width: number;
  dash?: string;
};

type TerrainLabel = ScreenPoint & {
  key: string;
  text: string;
  angle?: string;
  variant: "route" | "peak" | "elevation";
};

type TrailMapProps = {
  trail: Trail | null;
  reports?: TrailReport[];
  weather?: TrailWeather | null;
  fitRoute?: boolean;
  immersive?: boolean;
  initialPerspective?: boolean;
  showDetailsCard?: boolean;
  showUserLocation?: boolean;
  showMapNotices?: boolean;
  controlsTopOffset?: number;
  allowSatellite?: boolean;
  selectedCoordinate?: Coordinate | null;
  selectionToleranceMeters?: number;
  onSelectCoordinate?: (selection: {
    coordinate: Coordinate;
    distanceToRouteMeters: number;
    routeProgressMeters: number;
  }) => void;
  onSelectionRejected?: (distanceToRouteMeters: number | null) => void;
  onReportCoordinate?: (selection: {
    coordinate: Coordinate;
    routeProgressMeters: number;
    perspective: boolean;
  }) => void;
  onInteractionChange?: (isInteracting: boolean) => void;
  navigationMode?: boolean;
  offlineOnly?: boolean;
  bottomOverlayInset?: number;
};

const TILE_SIZE = 256;
const EMPTY_REPORTS: TrailReport[] = [];
const DEFAULT_ZOOM = 13;
const DEFAULT_CENTER: Coordinate = [-41.1734, -71.4752];
const MIN_ZOOM = 10;
const MAX_ZOOM_BY_LAYER: Record<MapLayer, number> = {
  standard: 18,
  terrain: 17,
  satellite: 19,
};
const mapGestureSurfaceStyle = { touchAction: "none" } as unknown as ViewStyle;

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));

const getTouchDistance = (touches: readonly MapTouch[]) => {
  if (touches.length < 2) return null;

  const [firstTouch, secondTouch] = touches;
  const dx = firstTouch.pageX - secondTouch.pageX;
  const dy = firstTouch.pageY - secondTouch.pageY;

  return Math.sqrt(dx * dx + dy * dy);
};

const project = ([latitude, longitude]: Coordinate, zoom: number) => {
  const latRad = (latitude * Math.PI) / 180;
  const scale = TILE_SIZE * 2 ** zoom;

  return {
    x: ((longitude + 180) / 360) * scale,
    y:
      ((1 -
        Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) /
        2) *
      scale,
  };
};

const unproject = ({ x, y }: { x: number; y: number }, zoom: number): Coordinate => {
  const scale = TILE_SIZE * 2 ** zoom;
  const longitude = (x / scale) * 360 - 180;
  const n = Math.PI - (2 * Math.PI * y) / scale;
  const latitude = (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));

  return [Math.max(-85, Math.min(85, latitude)), longitude];
};

const formatPathValue = (value: number) => Number(value.toFixed(1));

const pointsToSvgPath = (points: ScreenPoint[]) => {
  if (points.length === 0) return "";

  return points
    .map((point, index) => {
      const command = index === 0 ? "M" : "L";
      return `${command}${formatPathValue(point.x)} ${formatPathValue(point.y)}`;
    })
    .join(" ");
};

const getRouteBounds = (points: ScreenPoint[]) => {
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);

  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
};

const getPointAtRouteFraction = (
  points: ScreenPoint[],
  fraction: number
): (ScreenPoint & { angle: string }) | null => {
  if (points.length < 2) return null;

  const lengths = points.slice(0, -1).map((point, index) => {
    const nextPoint = points[index + 1];
    return Math.hypot(nextPoint.x - point.x, nextPoint.y - point.y);
  });
  const totalLength = lengths.reduce((total, length) => total + length, 0);
  if (totalLength <= 0) return null;

  const targetLength = totalLength * clamp(fraction, 0, 1);
  let traversed = 0;

  for (let index = 0; index < lengths.length; index += 1) {
    const length = lengths[index];
    const nextTraversed = traversed + length;

    if (targetLength <= nextTraversed || index === lengths.length - 1) {
      const start = points[index];
      const end = points[index + 1];
      const localProgress = length > 0 ? (targetLength - traversed) / length : 0;

      return {
        x: start.x + (end.x - start.x) * localProgress,
        y: start.y + (end.y - start.y) * localProgress,
        angle: `${Math.atan2(end.y - start.y, end.x - start.x)}rad`,
      };
    }

    traversed = nextTraversed;
  }

  return null;
};

const shortenTrailName = (name: string | null | undefined) => {
  const resolvedName = name?.trim() || "Sendero principal";
  return resolvedName.length > 22 ? `${resolvedName.slice(0, 21)}...` : resolvedName;
};

const getFittedView = (
  points: Coordinate[],
  layout: { width: number; height: number },
  maxZoom: number,
  fallbackCenter: Coordinate,
  fallbackZoom: number,
  minZoom = MIN_ZOOM
) => {
  if (points.length < 2 || !layout.width || !layout.height) {
    return { center: fallbackCenter, zoom: fallbackZoom };
  }

  for (let candidateZoom = maxZoom; candidateZoom >= minZoom; candidateZoom -= 1) {
    const projectedPoints = points.map((point) => project(point, candidateZoom));
    const xs = projectedPoints.map((point) => point.x);
    const ys = projectedPoints.map((point) => point.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const routeWidth = maxX - minX;
    const routeHeight = maxY - minY;

    if (routeWidth <= layout.width * 0.72 && routeHeight <= layout.height * 0.58) {
      return {
        center: unproject({ x: (minX + maxX) / 2, y: (minY + maxY) / 2 }, candidateZoom),
        zoom: candidateZoom,
      };
    }
  }

  const projectedPoints = points.map((point) => project(point, minZoom));
  const xs = projectedPoints.map((point) => point.x);
  const ys = projectedPoints.map((point) => point.y);

  return {
    center: unproject(
      {
        x: (Math.min(...xs) + Math.max(...xs)) / 2,
        y: (Math.min(...ys) + Math.max(...ys)) / 2,
      },
      minZoom
    ),
    zoom: minZoom,
  };
};

const getMapState = ({
  activeCenter,
  isPerspective,
  layer,
  layout,
  locationCoordinate,
  routePoints,
  selectedCoordinate,
  zoom,
}: {
  activeCenter: Coordinate;
  isPerspective: boolean;
  layer: MapLayer;
  layout: { width: number; height: number };
  locationCoordinate: Coordinate | null;
  routePoints: Coordinate[];
  selectedCoordinate: Coordinate | null;
  zoom: number;
}) => {
  if (!layout.width || !layout.height || isPerspective) {
    return {
      tiles: [] as MapTile[],
      points: [] as ScreenPoint[],
      selectedPoint: null as ScreenPoint | null,
      userPoint: null as ScreenPoint | null,
    };
  }

  const centerPixel = project(activeCenter, zoom);
  const topLeft = {
    x: centerPixel.x - layout.width / 2,
    y: centerPixel.y - layout.height / 2,
  };
  const minTileX = Math.floor(topLeft.x / TILE_SIZE);
  const maxTileX = Math.floor((topLeft.x + layout.width) / TILE_SIZE);
  const minTileY = Math.floor(topLeft.y / TILE_SIZE);
  const maxTileY = Math.floor((topLeft.y + layout.height) / TILE_SIZE);
  const tileBuffer = layer === "terrain" ? 0 : 1;
  const tiles = getVisibleTiles(layer, zoom, topLeft, {
    minTileX,
    maxTileX,
    minTileY,
    maxTileY,
    tileBuffer,
  });
  const points = routePoints.map((point) => {
    const pixel = project(point, zoom);

    return {
      x: pixel.x - topLeft.x,
      y: pixel.y - topLeft.y,
    };
  });
  const userPoint = locationCoordinate
    ? {
        x: project(locationCoordinate, zoom).x - topLeft.x,
        y: project(locationCoordinate, zoom).y - topLeft.y,
      }
    : null;
  const selectedPoint = selectedCoordinate
    ? {
        x: project(selectedCoordinate, zoom).x - topLeft.x,
        y: project(selectedCoordinate, zoom).y - topLeft.y,
      }
    : null;

  return { tiles, points, selectedPoint, userPoint };
};

const getVisibleTiles = (
  layer: MapLayer,
  zoom: number,
  topLeft: ScreenPoint,
  bounds: {
    minTileX: number;
    maxTileX: number;
    minTileY: number;
    maxTileY: number;
    tileBuffer: number;
  }
) => {
  const tiles: MapTile[] = [];

  for (let x = bounds.minTileX - bounds.tileBuffer; x <= bounds.maxTileX + bounds.tileBuffer; x += 1) {
    for (let y = bounds.minTileY - bounds.tileBuffer; y <= bounds.maxTileY + bounds.tileBuffer; y += 1) {
      if (y < 0 || y >= 2 ** zoom) continue;

      tiles.push({
        key: `${layer}-${zoom}-${x}-${y}`,
        url: getTileRemoteUrl(layer, zoom, x, y),
        left: x * TILE_SIZE - topLeft.x,
        top: y * TILE_SIZE - topLeft.y,
        layer,
        zoom,
        x,
        y,
      });
    }
  }

  return tiles;
};

const getMapAttribution = (layer: MapLayer) => {
  if (layer === "standard" && process.env.EXPO_PUBLIC_OFFLINE_TILE_ATTRIBUTION) return process.env.EXPO_PUBLIC_OFFLINE_TILE_ATTRIBUTION;
  if (layer === "terrain" || layer === "satellite") return "© Esri · © OpenStreetMap contributors";
  return "© OpenStreetMap contributors";
};

const getTerrainUnavailableMessage = (state: TerrainElevationState) => {
  if (state.status === "loading") {
    return "Cargando el relieve del recorrido...";
  }
  if (state.status === "unavailable" && state.reason === "no-route") {
    return "El relieve de este sendero no está disponible. Podés consultar la información del recorrido en su ficha.";
  }
  if (state.status === "unavailable" && state.reason === "offline") {
    return "Conectate a Internet para cargar el relieve. Si ya descargaste el mapa, podés seguir usándolo sin conexión.";
  }
  return "No pudimos cargar el relieve. Intentá nuevamente más tarde o usá la vista de mapa.";
};

const getMapDecorations = ({ points, trailName }: {
  points: ScreenPoint[];
  trailName: string | null | undefined;
}) => {
  const routeLabel = getPointAtRouteFraction(points, 0.5);
  return {
    labels: routeLabel ? [{ ...routeLabel, key: "route", text: shortenTrailName(trailName), variant: "route" as const }] : [],
    routePath: pointsToSvgPath(points),
  };
};

export function TrailMap({
  trail,
  reports = EMPTY_REPORTS,
  weather = null,
  fitRoute = false,
  immersive = false,
  initialPerspective = false,
  showDetailsCard = true,
  showUserLocation = true,
  showMapNotices = true,
  controlsTopOffset = 12,
  allowSatellite = true,
  selectedCoordinate = null,
  selectionToleranceMeters = 80,
  onSelectCoordinate,
  onSelectionRejected,
  onReportCoordinate,
  onInteractionChange,
  navigationMode = false,
  offlineOnly = false,
  bottomOverlayInset = 28,
}: TrailMapProps) {
  const network = useNetworkState();
  const offline = offlineOnly || network.isConnected === false || network.isInternetReachable === false;
  const [basicMap, setBasicMap] = useState<BasicOfflineMap | null>(null);
  const [layout, setLayout] = useState({ width: 0, height: 0 });
  const [selectedLayer, setLayer] = useState<MapLayer>("terrain");
  const layer = offline ? "standard" : selectedLayer;
  const [perspectiveEnabled, setIsPerspective] = useState(initialPerspective);
  const [terrainRenderFailed, setTerrainRenderFailed] = useState(false);
  const isPerspective = !offline && perspectiveEnabled;
  const [activeZoom, setActiveZoom] = useState(trail?.map_zoom || DEFAULT_ZOOM);
  const [activeCenter, setActiveCenter] = useState<Coordinate>(DEFAULT_CENTER);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [terrainOffset, setTerrainOffset] = useState({ x: 0, y: 0 });
  const [terrainScale, setTerrainScale] = useState(1);
  const [terrainStyle, setTerrainStyle] = useState<"natural" | "relief">("natural");
  const [pinchPreviewScale, setPinchPreviewScale] = useState(1);
  const [cachedTiles, setCachedTiles] = useState<MapTile[]>([]);
  const [tileUriOverrides, setTileUriOverrides] = useState<Record<string, string>>({});
  const [isTileLoading, setIsTileLoading] = useState(false);
  const [isChoosingReportLocation, setIsChoosingReportLocation] = useState(false);
  const [activeReportId, setActiveReportId] = useState<number | null>(null);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const terrainSceneRef = useRef<Terrain3DSceneHandle | null>(null);
  const isSelecting = Boolean(onSelectCoordinate || (isChoosingReportLocation && onReportCoordinate));
  const centerRef = useRef(activeCenter);
  const zoomRef = useRef(activeZoom);
  const maxZoomRef = useRef(MAX_ZOOM_BY_LAYER.terrain);
  const minZoomRef = useRef(MIN_ZOOM);
  const isPerspectiveRef = useRef(isPerspective);
  const panOffsetRef = useRef(panOffset);
  const layoutRef = useRef(layout);
  const terrainOffsetRef = useRef(terrainOffset);
  const terrainScaleRef = useRef(terrainScale);
  const isPinchingRef = useRef(false);
  const pinchStartDistanceRef = useRef<number | null>(null);
  const pinchStartZoomRef = useRef(activeZoom);
  const pinchStartTerrainScaleRef = useRef(terrainScale);
  const lastPinchRatioRef = useRef(1);
  const tileLoadRef = useRef(0);
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);
  const touchMovedRef = useRef(false);
  const onInteractionChangeRef = useRef(onInteractionChange);
  const centerLat = trail?.center_lat;
  const centerLng = trail?.center_lng;
  const hasRealCenter =
    typeof centerLat === "number" && typeof centerLng === "number";
  const trailCenter: Coordinate = hasRealCenter ? [centerLat, centerLng] : DEFAULT_CENTER;
  const route = useMemo(
    () => parseRouteCoordinates(trail?.route_coordinates),
    [trail?.route_coordinates]
  );
  const routePoints = useMemo(
    () => (route.length > 1 ? route : [trailCenter]),
    [route, trailCenter[0], trailCenter[1]]
  );
  const reportMarkers = useMemo(() => getReportMapMarkers(reports, trail?.id ?? 0, route), [reports, trail?.id, route]);
  const activeReport = reportMarkers.find(marker => marker.report.id === activeReportId);
  const sceneMarkers = useMemo<TerrainMapMarker[]>(() => [
    ...reportMarkers.map(marker => ({ id: String(marker.report.id), coordinate: marker.coordinate,
      color: marker.color, precisionMeters: marker.precisionMeters, issueSummary: marker.report.issue_summary })),
    ...(selectedCoordinate ? [{ id: "selected", coordinate: selectedCoordinate, color: "#087F4F", precisionMeters: 0, selected: true }] : []),
  ], [reportMarkers, selectedCoordinate]);
  const simulatedStartLocation = useMemo(
    () => getRouteStart(route, trailCenter),
    [route, trailCenter[0], trailCenter[1]]
  );
  const { location, permissionDenied, error: locationError, isTestingLocation } =
    useDeviceLocation(showUserLocation, simulatedStartLocation);
  useEffect(() => {
    let active = true;
    setBasicMap(null);
    if (trail) void readBasicOfflineMap(trail).then(value => { if (active) setBasicMap(value); });
    return () => { active = false; };
  }, [trail?.id, trail?.route_coordinates, trail?.center_lat, trail?.center_lng]);
  const showBasicMap = Boolean(basicMap && layer === "standard" && !isPerspective);
  const terrainElevation = useTerrainElevation(trail?.id ?? 0, route, {
    enabled: isPerspective,
    offline,
  });
  const terrainModel = useMemo(
    () =>
      terrainElevation.status === "ready"
        ? buildTerrainSceneModel(terrainElevation.data.grid, route)
        : null,
    [terrainElevation, route]
  );
  const savedZooms = useMemo(() => trail ? [...new Set(getOfflineTilePlanForTrail(trail).map((tile) => tile.zoom))] : [], [trail]);
  const maxZoom = offline && !basicMap && savedZooms.length ? Math.max(...savedZooms) : MAX_ZOOM_BY_LAYER[layer];
  const minZoom = offline && !basicMap && savedZooms.length ? Math.min(...savedZooms) : MIN_ZOOM;
  useEffect(() => {
    if (offline) { setLayer("standard"); setIsPerspective(false); }
  }, [offline]);
  const zoom = clamp(activeZoom, minZoom, maxZoom);
  const getInitialView = () =>
    fitRoute
      ? getFittedView(
          routePoints,
          layout,
          maxZoom,
          trailCenter,
          clamp(trail?.map_zoom || DEFAULT_ZOOM, minZoom, maxZoom),
          minZoom
        )
      : {
          center: trailCenter,
          zoom: clamp(trail?.map_zoom || DEFAULT_ZOOM, minZoom, maxZoom),
        };

  useEffect(() => {
    onInteractionChangeRef.current = onInteractionChange;
  }, [onInteractionChange]);

  useEffect(() => {
    const nextView = getInitialView();

    setActiveCenter(nextView.center);
    setActiveZoom(nextView.zoom);
    setPanOffset({ x: 0, y: 0 });
    setTerrainOffset({ x: 0, y: 0 });
    setTerrainScale(1);
    setPinchPreviewScale(1);
  }, [trail?.id, trailCenter[0], trailCenter[1], layout.width, layout.height, fitRoute, layer, maxZoom, minZoom]);

  useEffect(() => {
    setActiveReportId(null);
    setIsChoosingReportLocation(false);
    setSelectionError(null);
  }, [trail?.id]);

  useEffect(() => {
    centerRef.current = activeCenter;
    zoomRef.current = zoom;
    panOffsetRef.current = panOffset;
    layoutRef.current = layout;
    maxZoomRef.current = maxZoom;
    minZoomRef.current = minZoom;
    isPerspectiveRef.current = isPerspective;
    terrainOffsetRef.current = terrainOffset;
    terrainScaleRef.current = terrainScale;
  }, [activeCenter, isPerspective, layout, maxZoom, minZoom, panOffset, terrainOffset, terrainScale, zoom]);

  useEffect(() => {
    if (activeZoom > maxZoom) {
      setActiveZoom(maxZoom);
    }
  }, [activeZoom, maxZoom]);

  useEffect(() => {
    if (!allowSatellite && layer === "satellite") {
      setLayer("terrain");
    }
  }, [allowSatellite, layer]);

  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: (event) => event.nativeEvent.touches.length > 1,
        onMoveShouldSetPanResponder: (event, gesture) =>
          event.nativeEvent.touches.length > 1 ||
          Math.abs(gesture.dx) > 5 ||
          Math.abs(gesture.dy) > 5,
        onMoveShouldSetPanResponderCapture: (event, gesture) => event.nativeEvent.touches.length > 1 || Math.abs(gesture.dx) > 8 || Math.abs(gesture.dy) > 8,
        onPanResponderTerminationRequest: () => false,
        onShouldBlockNativeResponder: () => true,
        onPanResponderGrant: (event) => {
          onInteractionChangeRef.current?.(true);
          const distance = getTouchDistance(event.nativeEvent.touches);

          if (!distance) return;

          touchMovedRef.current = true;
          touchStartRef.current = null;
          isPinchingRef.current = true;
          pinchStartDistanceRef.current = distance;
          pinchStartZoomRef.current = zoomRef.current;
          pinchStartTerrainScaleRef.current = terrainScaleRef.current;
          lastPinchRatioRef.current = 1;
          setPanOffset({ x: 0, y: 0 });
          setPinchPreviewScale(1);
        },
        onPanResponderMove: (event, gesture) => {
          const distance = getTouchDistance(event.nativeEvent.touches);

          if (distance && !pinchStartDistanceRef.current) {
            touchMovedRef.current = true;
            touchStartRef.current = null;
            isPinchingRef.current = true;
            pinchStartDistanceRef.current = distance;
            pinchStartZoomRef.current = zoomRef.current;
            pinchStartTerrainScaleRef.current = terrainScaleRef.current;
            lastPinchRatioRef.current = 1;
            setPanOffset({ x: 0, y: 0 });
            setPinchPreviewScale(1);
            return;
          }

          if (distance && pinchStartDistanceRef.current) {
            const ratio = distance / pinchStartDistanceRef.current;
            isPinchingRef.current = true;
            lastPinchRatioRef.current = ratio;
            setPanOffset({ x: 0, y: 0 });

            if (isPerspectiveRef.current) {
              setTerrainScale(
                Number(
                  clampTerrainScale(pinchStartTerrainScaleRef.current * ratio).toFixed(2)
                )
              );
              return;
            }

            setPinchPreviewScale(Number(clamp(ratio, 0.68, 1.55).toFixed(2)));
            return;
          }

          if (isPinchingRef.current) return;

          if (Math.hypot(gesture.dx, gesture.dy) > 8) touchMovedRef.current = true;
          setPanOffset({ x: gesture.dx, y: gesture.dy });
        },
        onPanResponderRelease: (_, gesture) => {
          onInteractionChangeRef.current?.(false);
          if (isPinchingRef.current) {
            if (!isPerspectiveRef.current) {
              const ratio = lastPinchRatioRef.current;
              const zoomDelta = getPinchZoomDelta(ratio);
              const nextZoom = clamp(
                pinchStartZoomRef.current + zoomDelta,
                minZoomRef.current,
                maxZoomRef.current
              );

              setActiveZoom(nextZoom);
            }

            isPinchingRef.current = false;
            pinchStartDistanceRef.current = null;
            lastPinchRatioRef.current = 1;
            setPanOffset({ x: 0, y: 0 });
            setPinchPreviewScale(1);
            return;
          }

          if (Math.hypot(gesture.dx, gesture.dy) <= 8) {
            setPanOffset({ x: 0, y: 0 });
            return;
          }
          if (isPerspectiveRef.current) {
            const currentOffset = terrainOffsetRef.current;

            setTerrainOffset({
              x: currentOffset.x + gesture.dx,
              y: currentOffset.y + gesture.dy,
            });
            setPanOffset({ x: 0, y: 0 });
            return;
          }

          const centerPixel = project(centerRef.current, zoomRef.current);

          setActiveCenter(
            unproject(
              {
                x: centerPixel.x - gesture.dx,
                y: centerPixel.y - gesture.dy,
              },
              zoomRef.current
            )
          );
          setPanOffset({ x: 0, y: 0 });
        },
        onPanResponderTerminate: () => {
          onInteractionChangeRef.current?.(false);
          isPinchingRef.current = false;
          pinchStartDistanceRef.current = null;
          lastPinchRatioRef.current = 1;
          setPanOffset({ x: 0, y: 0 });
          setPinchPreviewScale(1);
        },
      }),
    []
  );

  const changeZoom = (delta: number) => {
    if (isPerspective) {
      setTerrainScale((currentScale) =>
        Number(clampTerrainScale(currentScale + delta * 0.16).toFixed(2))
      );
      return;
    }

    setActiveZoom((currentZoom) =>
      Math.max(minZoom, Math.min(maxZoom, currentZoom + delta))
    );
  };

  const resetView = () => {
    const nextView = getInitialView();

    setActiveCenter(nextView.center);
    setActiveZoom(nextView.zoom);
    setPanOffset({ x: 0, y: 0 });
    setTerrainOffset({ x: 0, y: 0 });
    setTerrainScale(1);
    setPinchPreviewScale(1);
  };

  const centerOnUser = () => {
    if (!location) {
      resetView();
      return;
    }

    setActiveCenter(location.coordinate);
    setActiveZoom((currentZoom) => Math.max(currentZoom, Math.min(16, maxZoom)));
    setPanOffset({ x: 0, y: 0 });
    setTerrainOffset({ x: 0, y: 0 });
    setTerrainScale(1);
    setPinchPreviewScale(1);
  };

  const mapState = useMemo(
    () =>
      getMapState({
        activeCenter,
        isPerspective,
        layer,
        layout,
        locationCoordinate: location?.coordinate ?? null,
        routePoints,
        selectedCoordinate,
        zoom,
      }),
    [activeCenter, isPerspective, layer, layout, location, routePoints, selectedCoordinate, zoom]
  );

  const reportScreenPoints = useMemo(() => {
    const center = project(activeCenter, zoom);
    return reportMarkers.map(marker => {
      const pixel = project(marker.coordinate, zoom);
      return { ...marker, x: pixel.x - center.x + layout.width / 2, y: pixel.y - center.y + layout.height / 2,
        radius: marker.precisionMeters / (156543.03392 * Math.cos(marker.coordinate[0] * Math.PI / 180) / 2 ** zoom) };
    });
  }, [reportMarkers, activeCenter, zoom, layout]);

  const openReport = (reportId: number) => {
    const marker = reportMarkers.find(item => item.report.id === reportId);
    if (!marker) return;
    setActiveReportId(reportId);
    if (!isPerspectiveRef.current || !terrainModel || !coordinateToTerrainScenePoint(terrainModel, marker.coordinate)) {
      if (isPerspectiveRef.current) setIsPerspective(false);
      const nextZoom = clamp(Math.max(zoomRef.current, 15), minZoom, maxZoom);
      const pixel = project(marker.coordinate, nextZoom);
      // Leave room below the point for the embedded report card.
      setActiveCenter(unproject({ x: pixel.x, y: pixel.y + (immersive ? 0 : layout.height * 0.18) }, nextZoom));
      setActiveZoom(nextZoom);
    }
  };

  const handleMapPress = (x: number, y: number) => {
    const currentLayout = layoutRef.current;
    if (!currentLayout.width || !currentLayout.height) return;
    let touchCoordinate: Coordinate | null = null;
    if (isPerspectiveRef.current) {
      const hit = terrainSceneRef.current?.pick(x / currentLayout.width * 2 - 1, 1 - y / currentLayout.height * 2);
      if (!isSelecting && hit?.markerId && hit.markerId !== "selected") {
        openReport(Number(hit.markerId));
        return;
      }
      touchCoordinate = hit?.coordinate ?? null;
    } else {
      if (!isSelecting) {
        const nearby = reportScreenPoints.filter(marker => Math.hypot(marker.x - x, marker.y - y) <= 26)
          .sort((a, b) => Math.hypot(a.x - x, a.y - y) - Math.hypot(b.x - x, b.y - y))[0];
        if (nearby) openReport(nearby.report.id);
        return;
      }
      const currentZoom = zoomRef.current;
      const centerPixel = project(centerRef.current, currentZoom);
      const currentPanOffset = panOffsetRef.current;
      touchCoordinate = unproject({
        x: centerPixel.x - currentLayout.width / 2 + x - currentPanOffset.x,
        y: centerPixel.y - currentLayout.height / 2 + y - currentPanOffset.y,
      }, currentZoom);
    }
    if (!isSelecting) return;
    const reject = (distance: number | null) => {
      setSelectionError("Tocá el sendero marcado para ubicar el reporte.");
      onSelectionRejected?.(distance);
    };
    if (!touchCoordinate || route.length < 2) { reject(null); return; }
    const closest = getClosestPointOnRoute(touchCoordinate, route);

    if (!closest) {
      reject(null);
      return;
    }

    if (closest.distanceMeters > selectionToleranceMeters) {
      reject(closest.distanceMeters);
      return;
    }

    setSelectionError(null);
    const selection = {
      coordinate: closest.coordinate,
      distanceToRouteMeters: closest.distanceMeters,
      routeProgressMeters: closest.progressMeters,
    };
    if (onSelectCoordinate) onSelectCoordinate(selection);
    else {
      onReportCoordinate?.({ ...selection, perspective: isPerspectiveRef.current });
      setIsChoosingReportLocation(false);
    }
  };

  const tileSignature = useMemo(
    () => mapState.tiles.map((tile) => tile.key).join("|"),
    [mapState.tiles]
  );

  useEffect(() => {
    if (isPerspective || showBasicMap || mapState.tiles.length === 0) {
      setIsTileLoading(false);
      return;
    }

    const nextTiles = mapState.tiles;
    if (offline) {
      setCachedTiles(nextTiles);
      setIsTileLoading(false);
      return;
    }
    const generation = tileLoadRef.current + 1;
    tileLoadRef.current = generation;
    setIsTileLoading(true);
    setCachedTiles((currentTiles) => (currentTiles.length > 0 ? currentTiles : nextTiles));

    Promise.all(nextTiles.map((tile) => Image.prefetch(tile.url).catch(() => false)))
      .then(() => {
        if (tileLoadRef.current === generation) {
          setCachedTiles(nextTiles);
        }
      })
      .finally(() => {
        if (tileLoadRef.current === generation) {
          setIsTileLoading(false);
        }
      });
    return () => { tileLoadRef.current += 1; };
  }, [isPerspective, tileSignature, offline, showBasicMap]);

  useEffect(() => {
    let isMounted = true;
    if (showBasicMap) {
      setTileUriOverrides({});
      return;
    }

    const loadLocalTileUris = async () => {
      const entries = await Promise.all(
        mapState.tiles.map(async (tile) => {
          const localUri = await resolveCachedTileUri(
            tile.layer,
            tile.zoom,
            tile.x,
            tile.y
          );

          return localUri ? [tile.key, localUri] : null;
        })
      );

      if (!isMounted) return;

      setTileUriOverrides(
        Object.fromEntries(
          entries.filter((entry): entry is [string, string] => Boolean(entry))
        )
      );
    };

    void loadLocalTileUris().catch(() => { if (isMounted) setTileUriOverrides({}); });

    return () => {
      isMounted = false;
    };
  }, [tileSignature, showBasicMap]);

  const mapDecorations = useMemo(
    () =>
      getMapDecorations({
        points: mapState.points,
        trailName: trail?.name,
      }),
    [mapState.points, trail?.name]
  );

  const showLocationNotice =
    showMapNotices && showUserLocation && (permissionDenied || locationError);
  const showTestingNotice = showMapNotices && isTestingLocation;
  const floatingNoticeTop = controlsTopOffset + 144;
  const locationNoticeOffset = showLocationNotice ? 54 : 0;
  const testingNoticeOffset = showTestingNotice ? 44 : 0;
  const testingNoticeTop = floatingNoticeTop + locationNoticeOffset;
  const selectionHintTop =
    floatingNoticeTop + locationNoticeOffset + testingNoticeOffset;
  const terrainOverlayTop = controlsTopOffset + 96;
  const reportControlsOffset = offline && showMapNotices && onReportCoordinate ? 50 : 0;

  const onLayout = (event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    setLayout({ width, height });
  };
  const isZoomInDisabled = isPerspective
    ? terrainScale >= MAX_TERRAIN_SCALE
    : zoom >= maxZoom;
  const isZoomOutDisabled = isPerspective
    ? terrainScale <= MIN_TERRAIN_SCALE
    : zoom <= minZoom;
  const isInitialTileLoad = cachedTiles.length === 0;
  const loaderTop = isInitialTileLoad
    ? Math.max(128, layout.height / 2 - 24)
    : floatingNoticeTop;

  return (
    <View
      style={[
        styles.map,
        !immersive && styles.embeddedMap,
        immersive && styles.immersiveMap,
        mapGestureSurfaceStyle,
      ]}
    >
    <View
      testID="trail-map-surface"
      style={StyleSheet.absoluteFill}
      onLayout={onLayout}
      onTouchStart={(event) => {
        onInteractionChangeRef.current?.(true);
        if (event.nativeEvent.touches.length !== 1) {
          touchStartRef.current = null;
          touchMovedRef.current = true;
          return;
        }

        touchMovedRef.current = false;
        touchStartRef.current = {
          x: event.nativeEvent.locationX,
          y: event.nativeEvent.locationY,
        };
      }}
      onTouchMove={(event) => {
        if (!touchStartRef.current) return;

        const dx = event.nativeEvent.locationX - touchStartRef.current.x;
        const dy = event.nativeEvent.locationY - touchStartRef.current.y;

        if (Math.sqrt(dx * dx + dy * dy) > 8) {
          touchMovedRef.current = true;
        }
      }}
      onTouchEnd={(event) => {
        if (event.nativeEvent.touches.length === 0) {
          onInteractionChangeRef.current?.(false);
        }
        if (
          !touchStartRef.current ||
          event.nativeEvent.touches.length > 0 ||
          touchMovedRef.current
        ) {
          touchStartRef.current = null;
          touchMovedRef.current = false;
          return;
        }

        handleMapPress(event.nativeEvent.locationX, event.nativeEvent.locationY);
        touchStartRef.current = null;
        touchMovedRef.current = false;
      }}
      onTouchCancel={() => {
        touchStartRef.current = null;
        touchMovedRef.current = false;
        onInteractionChangeRef.current?.(false);
      }}
      {...panResponder.panHandlers}
    >
      {isPerspective ? (
        <View pointerEvents="none" style={styles.terrain3dScene}>
          {terrainModel ? (
            <>
              <Terrain3DScene
                ref={terrainSceneRef}
                markers={sceneMarkers}
                focusCoordinate={activeReport?.coordinate ?? null}
                showContours={terrainStyle === "relief"}
                overlayTopInset={controlsTopOffset + 150}
                overlayBottomInset={bottomOverlayInset}
                onError={() => {
                  setTerrainRenderFailed(true);
                  setIsPerspective(false);
                }}
                terrain={terrainModel}
                userCoordinate={location?.coordinate ?? null}
                viewOffset={{
                  x: terrainOffset.x + panOffset.x,
                  y: terrainOffset.y + panOffset.y,
                }}
                viewScale={terrainScale}
                weather={weather ? {
                  condition: weather.condition,
                  rainProbability: weather.rain_probability,
                  temperatureC: weather.temperature_c,
                  windKmh: weather.wind_kmh,
                  windDirectionDegrees: weather.wind_direction_degrees,
                  cloudCoverPercent: weather.cloud_cover_percent,
                  isDay: weather.is_day,
                  observedAt: weather.observed_at,
                  source: weather.source,
                } : null}
                navigationMode={navigationMode}
                satelliteTextureEnabled={allowSatellite && !offline && terrainStyle === "natural"}
              />
              {!onReportCoordinate && reportMarkers.length === 0 && <View
                pointerEvents="none"
                style={[styles.terrain3dOverlay, { top: terrainOverlayTop }]}
              >
                <View style={styles.terrain3dPill}>
                  <View style={styles.terrain3dRouteSwatch} />
                  <Text numberOfLines={1} style={styles.terrain3dPillText}>
                    {shortenTrailName(trail?.name)}
                  </Text>
                </View>
              </View>}
            </>
          ) : (
            <View style={styles.terrainUnavailable}>
              {terrainElevation.status === "loading" ? (
                <ActivityIndicator size="small" color={colors.green} />
              ) : (
                <Ionicons name="alert-circle-outline" size={24} color={colors.muted} />
              )}
              <Text style={styles.terrainUnavailableTitle}>
                {terrainElevation.status === "loading"
                  ? "Cargando relieve real"
                  : "Relieve 3D no disponible"}
              </Text>
              <Text style={styles.terrainUnavailableText}>
                {getTerrainUnavailableMessage(terrainElevation)}
              </Text>
            </View>
          )}
        </View>
      ) : (
        <View
          pointerEvents="none"
          style={[
            styles.mapContent,
            {
              transform: [
                { translateX: panOffset.x },
                { translateY: panOffset.y },
                { scale: pinchPreviewScale },
              ],
            },
          ]}
        >
          {showBasicMap && basicMap ? <BasicMapLayer map={basicMap} center={activeCenter} zoom={zoom} width={layout.width} height={layout.height} /> : null}
          {!offline && !showBasicMap && isTileLoading && cachedTiles.length > 0
            ? cachedTiles.map((tile) => (
                <Image
                  key={`cached-${tile.key}`}
                  fadeDuration={0}
                  source={{ uri: tile.url }}
                  style={[
                    styles.tile,
                    styles.cachedTile,
                    { left: tile.left, top: tile.top },
                  ]}
                />
              ))
            : null}

          {mapState.tiles.filter(tile => !showBasicMap && (!offline || Boolean(tileUriOverrides[tile.key]))).map((tile) => (
            <Image
              key={tile.key}
              fadeDuration={0}
              source={{ uri: tileUriOverrides[tile.key] || tile.url }}
              style={[styles.tile, { left: tile.left, top: tile.top }]}
            />
          ))}

          {mapDecorations.routePath ? (
            <Svg
              pointerEvents="none"
              style={styles.mapVectorOverlay}
              width={layout.width}
              height={layout.height}
            >
              <Path
                d={mapDecorations.routePath}
                fill="none"
                stroke="#F0643B"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={12}
              />
              <Path
                d={mapDecorations.routePath}
                fill="none"
                stroke="#D4A56F"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={7}
              />
            </Svg>
          ) : null}

          {mapDecorations.labels.map((label) => (
            <View
              key={label.key}
              pointerEvents="none"
              style={[
                styles.terrainMapLabel,
                styles.terrainMapLabelRoute,
                {
                  left: label.x,
                  top: label.y,
                  transform: label.angle ? [{ rotate: label.angle }] : undefined,
                },
              ]}
            >
              <Text
                style={[
                  styles.terrainMapLabelText,
                  label.variant !== "route" && styles.terrainMapLabelTextDark,
                ]}
              >
                {label.text}
              </Text>
            </View>
          ))}

          {mapState.points[0] ? (
            <View
              style={[
                styles.marker,
                styles.startMarker,
                {
                  left: mapState.points[0].x - 18,
                  top: mapState.points[0].y - 18,
                },
              ]}
            >
              <Ionicons name="flag-outline" size={17} color={colors.white} />
            </View>
          ) : null}

          {mapState.points.length > 1 ? (
            <View
              style={[
                styles.marker,
                styles.endMarker,
                {
                  left: mapState.points[mapState.points.length - 1].x - 18,
                  top: mapState.points[mapState.points.length - 1].y - 18,
                },
              ]}
            >
              <Ionicons name="location" size={17} color={colors.white} />
            </View>
          ) : null}

          {mapState.userPoint ? (
            <View
              style={[
                styles.userAccuracy,
                {
                  left: mapState.userPoint.x - 28,
                  top: mapState.userPoint.y - 28,
                },
              ]}
            >
              <View style={styles.userMarker} />
            </View>
          ) : null}

          {mapState.selectedPoint ? (
            <View
              style={[
                styles.selectedMarker,
                {
                  left: mapState.selectedPoint.x - 15,
                  top: mapState.selectedPoint.y - 30,
                },
              ]}
            >
              <Ionicons name="pin" size={18} color={colors.white} />
            </View>
          ) : null}
          <Svg pointerEvents="none" style={styles.mapVectorOverlay} width={layout.width} height={layout.height}>
            {reportScreenPoints.map(marker => marker.radius > 0 ? (
              <Circle key={marker.report.id} cx={marker.x} cy={marker.y} r={marker.radius}
                fill={marker.color} fillOpacity={0.08} stroke={marker.color} strokeOpacity={0.5} strokeDasharray="4 4" />
            ) : null)}
          </Svg>
          {reportScreenPoints.map(marker => (
            <View key={marker.report.id} testID={`trail-report-${marker.report.id}`} pointerEvents="none" style={[styles.reportMarker,
              { left: marker.x - 17, top: marker.y - 34, backgroundColor: marker.color }]}>
              <Ionicons name={marker.report.blocks_path ? "close-circle" : "warning"} size={22} color={colors.white} />
            </View>
          ))}
        </View>
      )}
    </View>

      {reportMarkers.length > 0 && !activeReport && !isSelecting ? (
        <Pressable accessibilityRole="button" accessibilityLabel="Ver advertencias del sendero"
          onPress={() => openReport(reportMarkers[0].report.id)}
          style={[styles.reportBadge, { top: controlsTopOffset + 100 + reportControlsOffset }]}>
          <Ionicons name="warning" size={18} color={colors.danger} />
          <Text style={styles.reportBadgeText}>{reportMarkers.length} {reportMarkers.length === 1 ? "advertencia" : "advertencias"}</Text>
        </Pressable>
      ) : null}
      {onReportCoordinate && route.length > 1 ? (
        <Pressable accessibilityRole="button" accessibilityState={{ selected: isChoosingReportLocation }}
          onPress={() => { setIsChoosingReportLocation(value => !value); setActiveReportId(null); setSelectionError(null); }}
          style={[styles.reportBadge, { top: controlsTopOffset + 50 + reportControlsOffset, left: offline ? 12 : 94 }]}>
          <Ionicons name={isChoosingReportLocation ? "close" : "pin-outline"} size={18} color={colors.greenDark} />
          <Text style={styles.reportBadgeText}>{isChoosingReportLocation ? "Cancelar" : "Reportar punto"}</Text>
        </Pressable>
      ) : null}
      {activeReport && !isSelecting ? (
        <View style={[styles.reportCard, immersive ? { top: controlsTopOffset + 100 + reportControlsOffset } : { bottom: 24 }]}>
          <View style={styles.reportCardHeader}>
            <Ionicons name="warning" size={20} color={activeReport.color} />
            <Text style={styles.reportTitle} numberOfLines={2}>{activeReport.report.issue_summary}</Text>
            <Pressable accessibilityRole="button" accessibilityLabel="Cerrar advertencia" hitSlop={8} onPress={() => setActiveReportId(null)}>
              <Ionicons name="close" size={22} color={colors.ink} />
            </Pressable>
          </View>
          <Text style={styles.reportDescription}>{activeReport.report.trail_state} · Riesgo {activeReport.report.severity}{activeReport.report.blocks_path ? " · Bloquea el paso" : ""}</Text>
          <Text style={styles.reportDescription}>
            {activeReport.precisionMeters > 0 ? `Ubicación aproximada · margen ${activeReport.precisionMeters} m` : "Ubicación del reporte"}
            {activeReport.report.route_progress_meters != null ? ` · km ${(activeReport.report.route_progress_meters / 1000).toLocaleString("es-AR", { maximumFractionDigits: 1 })}` : ""}
          </Text>
          <Text style={styles.reportDescription}>Observado: {new Date(activeReport.report.observed_at || activeReport.report.created_at).toLocaleString("es-AR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}{offline ? " · Guardado sin conexión" : ""}</Text>
          {reportMarkers.length > 1 ? <Pressable accessibilityRole="button" accessibilityLabel="Ver siguiente advertencia"
            onPress={() => openReport(reportMarkers[(reportMarkers.indexOf(activeReport) + 1) % reportMarkers.length].report.id)}>
            <Text style={styles.reportBadgeText}>Siguiente advertencia ({reportMarkers.indexOf(activeReport) + 1}/{reportMarkers.length}) →</Text>
          </Pressable> : null}
        </View>
      ) : null}

      {offline && showMapNotices ? <View pointerEvents="none" style={[styles.locationWarning, {top: controlsTopOffset+52}]}>
        <Ionicons name="cloud-offline-outline" size={16} color={colors.green} />
        <Text style={[styles.locationWarningText,{color:colors.greenDark}]}>
          {basicMap ? containsMapCoordinate(basicMap,activeCenter) ? "Mapa descargado" : "Fuera de la zona descargada · volvé al recorrido" : "Mapa sin conexión · solo zona descargada"}
        </Text>
      </View> : null}

      {!isPerspective && isTileLoading ? (
        <View pointerEvents="none" style={[styles.mapLoaderLayer, { top: loaderTop }]}>
          <View
            style={[
              styles.mapLoaderPill,
              !isInitialTileLoad && styles.mapLoaderPillCompact,
            ]}
          >
            <ActivityIndicator size="small" color={colors.green} />
            {isInitialTileLoad ? (
              <Text style={styles.mapLoaderText}>Cargando mapa</Text>
            ) : null}
          </View>
        </View>
      ) : null}

      {!isPerspective ? (
        <View
          style={[
            styles.layerControl,
            { top: controlsTopOffset },
            immersive && styles.immersiveLayerControl,
          ]}
        >
        <Pressable
          onPress={() => setLayer("standard")}
          style={[styles.layerButton, layer === "standard" && styles.layerButtonActive]}
        >
          <Text style={[styles.layerLabel, layer === "standard" && styles.layerLabelActive]}>
            Mapa
          </Text>
        </Pressable>
        {!offline && <Pressable
          onPress={() => setLayer("terrain")}
          style={[styles.layerButton, layer === "terrain" && styles.layerButtonActive]}
        >
          <Text style={[styles.layerLabel, layer === "terrain" && styles.layerLabelActive]}>
            Terreno
          </Text>
        </Pressable>}
        {allowSatellite && !offline ? (
          <Pressable
            onPress={() => setLayer("satellite")}
            style={[styles.layerButton, layer === "satellite" && styles.layerButtonActive]}
          >
            <Text style={[styles.layerLabel, layer === "satellite" && styles.layerLabelActive]}>
              Satelite
            </Text>
          </Pressable>
        ) : null}
        </View>
      ) : null}
      {isPerspective ? <View style={[styles.terrainStyleControl, { top: controlsTopOffset }]}>
        {([ ["natural", "Imagen"], ["relief", "Relieve"] ] as const).map(([value, label]) => <Pressable key={value}
          accessibilityRole="button" accessibilityLabel={value === "natural" ? "Ver imagen satelital 3D" : "Ver relieve con curvas de nivel"}
          accessibilityState={{ selected: terrainStyle === value }} onPress={() => setTerrainStyle(value)}
          style={[styles.terrainStyleButton, terrainStyle === value && styles.layerButtonActive]}>
          <Text style={[styles.layerLabel, terrainStyle === value && styles.layerLabelActive]}>{label}</Text>
        </Pressable>)}
      </View> : null}

      {terrainRenderFailed && !isPerspective ? (
        <View pointerEvents="none" style={[styles.terrain3dOverlay, {top:terrainOverlayTop}]}>
          <View style={styles.terrain3dPill}>
            <Text style={styles.terrain3dPillText}>Relieve 3D no disponible. Mostrando mapa 2D.</Text>
          </View>
        </View>
      ) : null}
      {!offline && <Pressable
        accessibilityLabel={isPerspective ? "Cambiar a mapa 2D" : "Cambiar a perspectiva 3D"}
        accessibilityRole="button"
        accessibilityState={{ selected: isPerspective }}
        onPress={() => {
          setTerrainRenderFailed(false);
          setIsPerspective((current) => !current);
        }}
        style={[
          styles.perspectiveButton,
          { top: isPerspective ? controlsTopOffset : controlsTopOffset + 50 },
          immersive && styles.immersivePerspectiveButton,
          isPerspective && styles.perspectiveButtonActive,
        ]}
      >
        <Ionicons
          name={isPerspective ? "map-outline" : "cube-outline"}
          size={17}
          color={isPerspective ? colors.white : colors.greenDark}
        />
        <Text
          style={[
            styles.perspectiveLabel,
            isPerspective && styles.perspectiveLabelActive,
          ]}
        >
          {isPerspective ? "2D" : "3D"}
        </Text>
      </Pressable>}

      <View
        style={[
          styles.zoomControl,
          { top: controlsTopOffset },
          immersive && styles.immersiveZoomControl,
        ]}
      >
        <Pressable
          onPress={() => changeZoom(1)}
          disabled={isZoomInDisabled}
          style={[styles.zoomButton, isZoomInDisabled && styles.disabledControl]}
        >
          <Ionicons name="add" size={22} color={colors.ink} />
        </Pressable>
        <View style={styles.zoomDivider} />
        <Pressable
          onPress={() => changeZoom(-1)}
          disabled={isZoomOutDisabled}
          style={[styles.zoomButton, isZoomOutDisabled && styles.disabledControl]}
        >
          <Ionicons name="remove" size={22} color={colors.ink} />
        </Pressable>
        <View style={styles.zoomDivider} />
        <Pressable onPress={centerOnUser} style={styles.zoomButton}>
          <Ionicons name="locate-outline" size={20} color={colors.ink} />
        </Pressable>
      </View>

      {showDetailsCard && !isPerspective && !activeReport ? (
        <View style={styles.mapCard}>
          <Text style={styles.mapLabel}>{trail?.name || "Mapa del recorrido"}</Text>
          <Text style={styles.mapMeta}>
            {trail?.distance_km ? formatKilometers(trail.distance_km) : "Distancia a confirmar"} -{" "}
            {trail?.difficulty || "Dificultad a confirmar"}
          </Text>
        </View>
      ) : null}

      <Text style={styles.attribution} accessibilityRole="link" accessibilityLabel="Fuentes y licencias del mapa"
        onPress={() => router.push(trail ? { pathname: "/atribuciones", params: { trailId: String(trail.id) } } : "/atribuciones")}>
        {isPerspective
          ? `${OPEN_METEO_ELEVATION_ATTRIBUTION}${allowSatellite && !offline ? " · Imagen: Esri World Imagery" : ""}`
          : showBasicMap && basicMap ? basicMap.attribution : getMapAttribution(layer)}
      </Text>

      {showLocationNotice ? (
        <View style={[styles.locationWarning, { top: floatingNoticeTop }]}>
          <Ionicons name="location-outline" size={14} color={colors.danger} />
          <Text style={styles.locationWarningText}>
            Activa la ubicacion para ver tu posicion.
          </Text>
        </View>
      ) : null}

      {showTestingNotice ? (
        <View style={[styles.testingBadge, { top: testingNoticeTop }]}>
          <Ionicons name="flask-outline" size={14} color={colors.greenDark} />
          <Text style={styles.testingBadgeText}>Modo prueba</Text>
        </View>
      ) : null}

      {isSelecting ? (
        <View
          pointerEvents="none"
          style={[styles.selectionHint, { top: selectionHintTop }]}
        >
          <Ionicons name="pin-outline" size={14} color={colors.greenDark} />
          <Text style={styles.selectionHintText}>{selectionError || "Tocá sobre el sendero para ubicar el reporte"}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  reportMarker: {
    position: "absolute", width: 34, height: 34, borderRadius: 17,
    borderBottomLeftRadius: 4, alignItems: "center", justifyContent: "center",
    borderColor: "#FFFFFF", borderWidth: 2, zIndex: 6,
  },
  terrainStyleControl: { position: "absolute", left: 88, right: 64, backgroundColor: "rgba(255,255,255,0.94)", borderRadius: 14,
    padding: 4, flexDirection: "row", justifyContent: "center", zIndex: 6 },
  terrainStyleButton: { flex: 1, paddingHorizontal: 5, paddingVertical: 8, alignItems: "center", borderRadius: 12 },
  reportBadge: {
    position: "absolute", left: 12, right: 64, alignSelf: "flex-start", flexDirection: "row",
    alignItems: "center", gap: 6, backgroundColor: "rgba(255,255,255,0.96)",
    borderRadius: 14, paddingHorizontal: 10, minHeight: 44, zIndex: 7,
  },
  reportBadgeText: { color: colors.greenDark, fontWeight: "800", fontSize: 12 },
  reportCard: {
    position: "absolute", left: 12, right: 64, padding: 12, gap: 8,
    backgroundColor: "rgba(255,255,255,0.98)", borderRadius: 16, zIndex: 8,
  },
  reportCardHeader: { flexDirection: "row", alignItems: "center", gap: 7 },
  reportTitle: { flex: 1, color: colors.ink, fontWeight: "800", fontSize: 14 },
  reportDescription: { color: colors.ink, fontSize: 12, lineHeight: 17 },
  map: {
    backgroundColor: "#DDE9E0",
    borderRadius: 24,
    marginBottom: 16,
    overflow: "hidden",
    position: "relative",
  },
  embeddedMap: {
    alignSelf: "stretch",
    height: 430,
    minHeight: 360,
  },
  immersiveMap: {
    borderRadius: 0,
    flex: 1,
    marginBottom: 0,
    minHeight: 0,
  },
  mapContent: {
    flex: 1,
  },
  tile: {
    height: TILE_SIZE,
    position: "absolute",
    width: TILE_SIZE,
  },
  cachedTile: {
    opacity: 0.72,
  },
  mapVectorOverlay: {
    bottom: 0,
    left: 0,
    position: "absolute",
    right: 0,
    top: 0,
    zIndex: 2,
  },
  mapLoaderLayer: {
    alignItems: "center",
    left: 0,
    position: "absolute",
    right: 0,
    zIndex: 8,
  },
  mapLoaderPill: {
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.95)",
    borderRadius: 18,
    flexDirection: "row",
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    shadowColor: "#000",
    shadowOpacity: 0.12,
    shadowRadius: 12,
  },
  mapLoaderPillCompact: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  mapLoaderText: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "800",
  },
  terrain3dScene: {
    backgroundColor: "#CFE6F1",
    flex: 1,
    overflow: "hidden",
  },
  terrainUnavailable: {
    alignItems: "center",
    flex: 1,
    gap: 8,
    justifyContent: "center",
    paddingHorizontal: 32,
  },
  terrainUnavailableTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "900",
    textAlign: "center",
  },
  terrainUnavailableText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 17,
    textAlign: "center",
  },
  terrain3dOverlay: {
    alignItems: "flex-start",
    gap: 8,
    left: 14,
    position: "absolute",
    zIndex: 5,
  },
  terrain3dPill: {
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.86)",
    borderColor: "rgba(13,122,69,0.16)",
    borderRadius: 14,
    borderWidth: 1,
    flexDirection: "row",
    gap: 7,
    maxWidth: 210,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  terrain3dRouteSwatch: {
    backgroundColor: "#D4A56F",
    borderColor: "#F0643B",
    borderRadius: 5,
    borderWidth: 3,
    height: 12,
    width: 24,
  },
  terrain3dPillText: {
    color: colors.greenDark,
    flexShrink: 1,
    fontSize: 11,
    fontWeight: "900",
  },
  layerControl: {
    backgroundColor: "rgba(255,255,255,0.94)",
    borderRadius: 16,
    flexDirection: "row",
    left: 12,
    padding: 4,
    position: "absolute",
    zIndex: 6,
  },
  immersiveLayerControl: {},
  layerButton: {
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  layerButtonActive: {
    backgroundColor: colors.green,
  },
  layerLabel: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "900",
  },
  layerLabelActive: {
    color: colors.white,
  },
  zoomControl: {
    backgroundColor: "rgba(255,255,255,0.94)",
    borderRadius: 18,
    overflow: "hidden",
    position: "absolute",
    right: 12,
    zIndex: 6,
  },
  immersiveZoomControl: {},
  zoomButton: {
    alignItems: "center",
    height: 42,
    justifyContent: "center",
    width: 42,
  },
  zoomDivider: {
    backgroundColor: colors.line,
    height: 1,
  },
  disabledControl: {
    opacity: 0.38,
  },
  perspectiveButton: {
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.94)",
    borderRadius: 16,
    flexDirection: "row",
    gap: 6,
    left: 12,
    paddingHorizontal: 12,
    paddingVertical: 9,
    position: "absolute",
    zIndex: 6,
  },
  immersivePerspectiveButton: {},
  perspectiveButtonActive: {
    backgroundColor: colors.green,
  },
  perspectiveLabel: {
    color: colors.greenDark,
    fontSize: 12,
    fontWeight: "900",
  },
  perspectiveLabelActive: {
    color: colors.white,
  },
  routeSegment: {
    backgroundColor: colors.danger,
    borderColor: colors.white,
    borderRadius: 999,
    borderWidth: 1,
    height: 7,
    position: "absolute",
    transformOrigin: "left center",
    zIndex: 3,
  },
  terrainMapLabel: {
    alignItems: "center",
    backgroundColor: "rgba(34, 38, 29, 0.68)",
    borderColor: "rgba(255,255,255,0.42)",
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 3,
    position: "absolute",
    zIndex: 3,
  },
  terrainMapLabelRoute: {
    backgroundColor: "rgba(34, 38, 29, 0.74)",
  },
  terrainMapLabelPeak: {
    backgroundColor: "rgba(255,255,255,0.82)",
    borderColor: "rgba(36, 52, 33, 0.22)",
  },
  terrainMapLabelElevation: {
    backgroundColor: "rgba(216, 240, 189, 0.88)",
    borderColor: "rgba(13, 122, 69, 0.24)",
  },
  terrainMapLabelText: {
    color: colors.white,
    fontSize: 10,
    fontWeight: "900",
    textShadowColor: "rgba(0,0,0,0.28)",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 2,
  },
  terrainMapLabelTextDark: {
    color: colors.greenDark,
    textShadowRadius: 0,
  },
  marker: {
    alignItems: "center",
    borderColor: colors.white,
    borderRadius: 18,
    borderWidth: 2,
    height: 36,
    justifyContent: "center",
    position: "absolute",
    width: 36,
    zIndex: 4,
  },
  startMarker: {
    backgroundColor: colors.green,
  },
  endMarker: {
    backgroundColor: colors.danger,
  },
  userAccuracy: {
    alignItems: "center",
    backgroundColor: "rgba(35, 118, 217, 0.18)",
    borderColor: "rgba(35, 118, 217, 0.28)",
    borderRadius: 28,
    borderWidth: 1,
    height: 56,
    justifyContent: "center",
    position: "absolute",
    width: 56,
    zIndex: 5,
  },
  userMarker: {
    backgroundColor: "#2376D9",
    borderColor: colors.white,
    borderRadius: 10,
    borderWidth: 3,
    height: 20,
    shadowColor: "#000",
    shadowOpacity: 0.18,
    shadowRadius: 8,
    width: 20,
  },
  selectedMarker: {
    alignItems: "center",
    backgroundColor: colors.green,
    borderColor: colors.white,
    borderRadius: 15,
    borderWidth: 2,
    height: 30,
    justifyContent: "center",
    position: "absolute",
    width: 30,
    zIndex: 7,
  },
  mapCard: {
    backgroundColor: "rgba(255,255,255,0.95)",
    borderRadius: 18,
    bottom: 14,
    left: 14,
    padding: 14,
    position: "absolute",
    right: 14,
    zIndex: 5,
  },
  mapLabel: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "900",
  },
  mapMeta: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "700",
    marginTop: 4,
  },
  attribution: {
    backgroundColor: "rgba(255,255,255,0.86)",
    bottom: 2,
    color: colors.muted,
    fontSize: 10,
    fontWeight: "400",
    maxWidth: "95%",
    paddingHorizontal: 4,
    paddingVertical: 1,
    position: "absolute",
    right: 4,
    zIndex: 5,
  },
  locationWarning: {
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.94)",
    borderRadius: 14,
    flexDirection: "row",
    gap: 6,
    left: 12,
    paddingHorizontal: 10,
    paddingVertical: 8,
    position: "absolute",
    right: 12,
    zIndex: 7,
  },
  locationWarningText: {
    color: colors.danger,
    flex: 1,
    fontSize: 12,
    fontWeight: "900",
  },
  testingBadge: {
    alignItems: "center",
    backgroundColor: "rgba(223,243,231,0.96)",
    borderColor: "rgba(13,122,69,0.24)",
    borderRadius: 14,
    borderWidth: 1,
    flexDirection: "row",
    gap: 5,
    left: 12,
    paddingHorizontal: 10,
    paddingVertical: 7,
    position: "absolute",
    zIndex: 7,
  },
  testingBadgeText: {
    color: colors.greenDark,
    fontSize: 12,
    fontWeight: "900",
  },
  selectionHint: {
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.94)",
    borderRadius: 14,
    flexDirection: "row",
    gap: 5,
    left: 12,
    right: 12,
    paddingHorizontal: 10,
    paddingVertical: 7,
    position: "absolute",
    zIndex: 7,
  },
  selectionHintText: {
    color: colors.greenDark,
    fontSize: 12,
    fontWeight: "900",
    flex: 1,
  },
});
