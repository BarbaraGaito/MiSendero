import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Image,
  DimensionValue,
  LayoutChangeEvent,
  PanResponder,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Trail } from "../../types";
import {
  Coordinate,
  getRouteStart,
  parseRouteCoordinates,
} from "../../services/geoUtils";
import {
  getTileRemoteUrl,
  resolveCachedTileUri,
} from "../../services/mapTileCache";
import { useDeviceLocation } from "../hooks/useDeviceLocation";
import { colors } from "./MiSenderoUI";

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

type TrailMapProps = {
  trail: Trail | null;
  fitRoute?: boolean;
  immersive?: boolean;
  initialPerspective?: boolean;
  showDetailsCard?: boolean;
  showUserLocation?: boolean;
  controlsTopOffset?: number;
};

const TILE_SIZE = 256;
const DEFAULT_ZOOM = 13;
const DEFAULT_CENTER: Coordinate = [-41.1734, -71.4752];
const MIN_ZOOM = 10;
const MAX_TERRAIN_POINTS = 42;
const MAX_ZOOM_BY_LAYER: Record<MapLayer, number> = {
  standard: 18,
  terrain: 17,
  satellite: 19,
};

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));

const getTouchDistance = (touches: readonly MapTouch[]) => {
  if (touches.length < 2) return null;

  const [firstTouch, secondTouch] = touches;
  const dx = firstTouch.pageX - secondTouch.pageX;
  const dy = firstTouch.pageY - secondTouch.pageY;

  return Math.sqrt(dx * dx + dy * dy);
};

const getSampledRoutePoints = (points: Coordinate[], maxPoints: number) => {
  if (points.length <= maxPoints) return points;

  const lastIndex = points.length - 1;

  return Array.from({ length: maxPoints }, (_, index) => {
    const sourceIndex = Math.round((index / (maxPoints - 1)) * lastIndex);

    return points[sourceIndex];
  });
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

const wrapTileX = (x: number, zoom: number) => {
  const max = 2 ** zoom;
  return ((x % max) + max) % max;
};

const getDifficultyFactor = (difficulty: string | null | undefined) => {
  const normalized = (difficulty || "").toLowerCase();

  if (normalized.includes("dificil") || normalized.includes("alta")) return 1;
  if (normalized.includes("media") || normalized.includes("moderada")) return 0.68;
  return 0.42;
};

const getRouteDistanceKm = (points: Coordinate[]) => {
  if (points.length < 2) return 0;

  const toRad = (value: number) => (value * Math.PI) / 180;
  const earthRadiusKm = 6371;

  return points.slice(0, -1).reduce((total, point, index) => {
    const nextPoint = points[index + 1];
    const dLat = toRad(nextPoint[0] - point[0]);
    const dLng = toRad(nextPoint[1] - point[1]);
    const lat1 = toRad(point[0]);
    const lat2 = toRad(nextPoint[0]);
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

    return total + earthRadiusKm * c;
  }, 0);
};

const getFittedView = (
  points: Coordinate[],
  layout: { width: number; height: number },
  maxZoom: number,
  fallbackCenter: Coordinate,
  fallbackZoom: number
) => {
  if (points.length < 2 || !layout.width || !layout.height) {
    return { center: fallbackCenter, zoom: fallbackZoom };
  }

  for (let candidateZoom = maxZoom; candidateZoom >= MIN_ZOOM; candidateZoom -= 1) {
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

  const projectedPoints = points.map((point) => project(point, MIN_ZOOM));
  const xs = projectedPoints.map((point) => point.x);
  const ys = projectedPoints.map((point) => point.y);

  return {
    center: unproject(
      {
        x: (Math.min(...xs) + Math.max(...xs)) / 2,
        y: (Math.min(...ys) + Math.max(...ys)) / 2,
      },
      MIN_ZOOM
    ),
    zoom: MIN_ZOOM,
  };
};

export function TrailMap({
  trail,
  fitRoute = false,
  immersive = false,
  initialPerspective = false,
  showDetailsCard = true,
  showUserLocation = true,
  controlsTopOffset = 12,
}: TrailMapProps) {
  const [layout, setLayout] = useState({ width: 0, height: 0 });
  const [layer, setLayer] = useState<MapLayer>("terrain");
  const [isPerspective, setIsPerspective] = useState(initialPerspective);
  const [activeZoom, setActiveZoom] = useState(trail?.map_zoom || DEFAULT_ZOOM);
  const [activeCenter, setActiveCenter] = useState<Coordinate>(DEFAULT_CENTER);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [terrainOffset, setTerrainOffset] = useState({ x: 0, y: 0 });
  const [terrainScale, setTerrainScale] = useState(1);
  const [pinchPreviewScale, setPinchPreviewScale] = useState(1);
  const [cachedTiles, setCachedTiles] = useState<MapTile[]>([]);
  const [tileUriOverrides, setTileUriOverrides] = useState<Record<string, string>>({});
  const [isTileLoading, setIsTileLoading] = useState(false);
  const centerRef = useRef(activeCenter);
  const zoomRef = useRef(activeZoom);
  const maxZoomRef = useRef(MAX_ZOOM_BY_LAYER.terrain);
  const isPerspectiveRef = useRef(isPerspective);
  const terrainOffsetRef = useRef(terrainOffset);
  const terrainScaleRef = useRef(terrainScale);
  const isPinchingRef = useRef(false);
  const pinchStartDistanceRef = useRef<number | null>(null);
  const pinchStartZoomRef = useRef(activeZoom);
  const pinchStartTerrainScaleRef = useRef(terrainScale);
  const lastPinchRatioRef = useRef(1);
  const tileLoadRef = useRef(0);
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
  const simulatedStartLocation = useMemo(
    () => getRouteStart(route, trailCenter),
    [route, trailCenter[0], trailCenter[1]]
  );
  const { location, permissionDenied, error: locationError, isTestingLocation } =
    useDeviceLocation(showUserLocation, simulatedStartLocation);
  const maxZoom = MAX_ZOOM_BY_LAYER[layer];
  const zoom = Math.min(activeZoom, maxZoom);
  const getInitialView = () =>
    fitRoute
      ? getFittedView(
          routePoints,
          layout,
          maxZoom,
          trailCenter,
          Math.min(trail?.map_zoom || DEFAULT_ZOOM, maxZoom)
        )
      : {
          center: trailCenter,
          zoom: Math.min(trail?.map_zoom || DEFAULT_ZOOM, maxZoom),
        };

  useEffect(() => {
    const nextView = getInitialView();

    setActiveCenter(nextView.center);
    setActiveZoom(nextView.zoom);
    setPanOffset({ x: 0, y: 0 });
    setTerrainOffset({ x: 0, y: 0 });
    setTerrainScale(1);
    setPinchPreviewScale(1);
  }, [trail?.id, trailCenter[0], trailCenter[1], layout.width, layout.height, fitRoute, layer]);

  useEffect(() => {
    centerRef.current = activeCenter;
    zoomRef.current = zoom;
    maxZoomRef.current = maxZoom;
    isPerspectiveRef.current = isPerspective;
    terrainOffsetRef.current = terrainOffset;
    terrainScaleRef.current = terrainScale;
  }, [activeCenter, isPerspective, maxZoom, terrainOffset, terrainScale, zoom]);

  useEffect(() => {
    if (activeZoom > maxZoom) {
      setActiveZoom(maxZoom);
    }
  }, [activeZoom, maxZoom]);

  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: (event) => event.nativeEvent.touches.length >= 2,
        onMoveShouldSetPanResponder: (event, gesture) =>
          event.nativeEvent.touches.length >= 2 ||
          Math.abs(gesture.dx) > 5 ||
          Math.abs(gesture.dy) > 5,
        onPanResponderGrant: (event) => {
          const distance = getTouchDistance(event.nativeEvent.touches);

          if (!distance) return;

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

          if (distance && pinchStartDistanceRef.current) {
            const ratio = distance / pinchStartDistanceRef.current;
            isPinchingRef.current = true;
            lastPinchRatioRef.current = ratio;
            setPanOffset({ x: 0, y: 0 });

            if (isPerspectiveRef.current) {
              setTerrainScale(
                Number(
                  clamp(pinchStartTerrainScaleRef.current * ratio, 0.7, 1.9).toFixed(2)
                )
              );
              return;
            }

            setPinchPreviewScale(Number(clamp(ratio, 0.68, 1.55).toFixed(2)));
            return;
          }

          if (isPinchingRef.current) return;

          setPanOffset({ x: gesture.dx, y: gesture.dy });
        },
        onPanResponderRelease: (_, gesture) => {
          if (isPinchingRef.current) {
            if (!isPerspectiveRef.current) {
              const zoomDelta = Math.round(Math.log(lastPinchRatioRef.current) / Math.log(1.38));
              const nextZoom = clamp(
                pinchStartZoomRef.current + zoomDelta,
                MIN_ZOOM,
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
        Math.max(0.7, Math.min(1.9, Number((currentScale + delta * 0.16).toFixed(2))))
      );
      return;
    }

    setActiveZoom((currentZoom) =>
      Math.max(MIN_ZOOM, Math.min(maxZoom, currentZoom + delta))
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

  const mapState = useMemo(() => {
    if (!layout.width || !layout.height) {
      return { tiles: [], points: [], userPoint: null };
    }

    if (isPerspective) {
      return { tiles: [], points: [], userPoint: null };
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
    const tiles: MapTile[] = [];

    for (let x = minTileX - tileBuffer; x <= maxTileX + tileBuffer; x += 1) {
      for (let y = minTileY - tileBuffer; y <= maxTileY + tileBuffer; y += 1) {
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

    const points = routePoints.map((point) => {
      const pixel = project(point, zoom);

      return {
        x: pixel.x - topLeft.x,
        y: pixel.y - topLeft.y,
      };
    });

    const userPoint = location
      ? {
          x: project(location.coordinate, zoom).x - topLeft.x,
          y: project(location.coordinate, zoom).y - topLeft.y,
        }
      : null;

    return { tiles, points, userPoint };
  }, [activeCenter[0], activeCenter[1], isPerspective, layer, layout.height, layout.width, location, routePoints, zoom]);

  const tileSignature = useMemo(
    () => mapState.tiles.map((tile) => tile.key).join("|"),
    [mapState.tiles]
  );

  useEffect(() => {
    if (isPerspective || mapState.tiles.length === 0) {
      setIsTileLoading(false);
      return;
    }

    const nextTiles = mapState.tiles;
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
  }, [isPerspective, tileSignature]);

  useEffect(() => {
    let isMounted = true;

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

    loadLocalTileUris();

    return () => {
      isMounted = false;
    };
  }, [tileSignature]);

  const terrainState = useMemo(() => {
    if (!layout.width || !layout.height) {
      return {
        points: [],
        bands: [],
        userPoint: null,
        distanceKm: 0,
        elevationGain: 0,
      };
    }

    const rawSourcePoints = routePoints.length > 1 ? routePoints : [trailCenter, trailCenter];
    const sourcePoints = getSampledRoutePoints(rawSourcePoints, MAX_TERRAIN_POINTS);
    const projectedPoints = sourcePoints.map((point) => project(point, DEFAULT_ZOOM));
    const xs = projectedPoints.map((point) => point.x);
    const ys = projectedPoints.map((point) => point.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const mapWidth = Math.max(1, maxX - minX);
    const mapHeight = Math.max(1, maxY - minY);
    const sceneWidth = layout.width;
    const sceneHeight = layout.height;
    const paddingX = sceneWidth * 0.16;
    const paddingY = sceneHeight * 0.24;
    const fitScale = Math.min(
      (sceneWidth - paddingX * 2) / mapWidth,
      (sceneHeight - paddingY * 2) / mapHeight
    );
    const offsetX = (sceneWidth - mapWidth * fitScale) / 2;
    const offsetY = (sceneHeight - mapHeight * fitScale) / 2;
    const difficultyFactor = getDifficultyFactor(trail?.difficulty);
    const distanceKm = trail?.distance_km || getRouteDistanceKm(rawSourcePoints);
    const elevationGain = Math.round(
      Math.max(60, distanceKm * (80 + difficultyFactor * 95))
    );

    const points = projectedPoints.map((point, index) => {
      const progress =
        projectedPoints.length <= 1 ? 0 : index / (projectedPoints.length - 1);
      const wave = Math.sin(progress * Math.PI * 2.4) * 18;
      const localPeak = Math.sin(progress * Math.PI) * 58 * difficultyFactor;
      const secondaryPeak = Math.max(0, Math.sin((progress - 0.18) * Math.PI * 2)) * 28;
      const climb = progress * elevationGain * 0.045 * difficultyFactor;
      const z = Math.max(18, 34 + localPeak + secondaryPeak + climb);

      return {
        x: offsetX + (point.x - minX) * fitScale,
        y: offsetY + (point.y - minY) * fitScale - wave - z,
        baseY: offsetY + (point.y - minY) * fitScale + 18,
        z,
      };
    });
    const userPoint = location
      ? {
          x: offsetX + (project(location.coordinate, DEFAULT_ZOOM).x - minX) * fitScale,
          y: offsetY + (project(location.coordinate, DEFAULT_ZOOM).y - minY) * fitScale,
        }
      : null;

    const bands = Array.from({ length: 9 }, (_, index) => ({
      key: `terrain-band-${index}`,
      top: `${index * 11}%` as DimensionValue,
      opacity: 0.7 - index * 0.025,
      color:
        index < 3
          ? "#D5E8BE"
          : index < 6
            ? "#A9D39B"
            : "#6FAC77",
    }));

    return {
      points,
      bands,
      userPoint,
      distanceKm,
      elevationGain,
    };
  }, [layout.height, layout.width, location, routePoints, trail?.difficulty, trail?.distance_km, trailCenter[0], trailCenter[1]]);

  const onLayout = (event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    setLayout({ width, height });
  };
  const isZoomInDisabled = isPerspective ? terrainScale >= 1.9 : zoom >= maxZoom;
  const isZoomOutDisabled = isPerspective ? terrainScale <= 0.7 : zoom <= MIN_ZOOM;
  const isInitialTileLoad = cachedTiles.length === 0;
  const loaderTop = isInitialTileLoad
    ? Math.max(128, layout.height / 2 - 24)
    : controlsTopOffset + 112;

  return (
    <View
      style={[styles.map, !immersive && styles.embeddedMap, immersive && styles.immersiveMap]}
      onLayout={onLayout}
      {...panResponder.panHandlers}
    >
      {isPerspective ? (
        <View style={styles.terrain3dScene}>
          <View style={styles.terrainSky} />
          <View style={styles.mountainFar} />
          <View style={styles.mountainNear} />
          <View style={styles.terrainHorizon} />
          <View style={styles.terrainPlane}>
            <View
              style={[
                styles.terrainMovableContent,
                {
                  transform: [
                    { translateX: terrainOffset.x + panOffset.x },
                    { translateY: terrainOffset.y + panOffset.y },
                    { scale: terrainScale },
                  ],
                },
              ]}
            >
              {terrainState.bands.map((band) => (
                <View
                  key={band.key}
                  style={[
                    styles.terrainBand,
                    {
                      backgroundColor: band.color,
                      opacity: band.opacity,
                      top: band.top,
                    },
                  ]}
                />
              ))}

              <View style={styles.terrainRidgeBack} />
              <View style={styles.terrainRidgeFront} />

              {terrainState.points.map((point, index) => (
                <View
                  key={`terrain-pillar-${index}`}
                  style={[
                    styles.terrainPillar,
                    {
                      height: Math.max(18, point.baseY - point.y),
                      left: point.x - 5,
                      top: point.y + 8,
                    },
                  ]}
                />
              ))}

              {terrainState.points.slice(0, -1).map((point, index) => {
                const nextPoint = terrainState.points[index + 1];
                const dx = nextPoint.x - point.x;
                const dy = nextPoint.y - point.y;
                const length = Math.sqrt(dx * dx + dy * dy);
                const angle = `${Math.atan2(dy, dx)}rad`;

                return (
                  <View
                    key={`terrain-route-shadow-${index}`}
                    style={[
                      styles.terrainRouteShadow,
                      {
                        left: point.x + 5,
                        top: Math.max(point.baseY, nextPoint.baseY) + 4,
                        width: length,
                        transform: [{ rotate: angle }],
                      },
                    ]}
                  />
                );
              })}

              {terrainState.points.slice(0, -1).map((point, index) => {
                const nextPoint = terrainState.points[index + 1];
                const dx = nextPoint.x - point.x;
                const dy = nextPoint.y - point.y;
                const length = Math.sqrt(dx * dx + dy * dy);
                const angle = `${Math.atan2(dy, dx)}rad`;

                return (
                  <View
                    key={`terrain-route-wall-${index}`}
                    style={[
                      styles.terrainRouteWall,
                      {
                        height: Math.max(18, (point.z + nextPoint.z) / 2),
                        left: point.x,
                        top: point.y + 5,
                        width: length,
                        transform: [{ rotate: angle }],
                      },
                    ]}
                  />
                );
              })}

              {terrainState.points.slice(0, -1).map((point, index) => {
                const nextPoint = terrainState.points[index + 1];
                const dx = nextPoint.x - point.x;
                const dy = nextPoint.y - point.y;
                const length = Math.sqrt(dx * dx + dy * dy);
                const angle = `${Math.atan2(dy, dx)}rad`;

                return (
                  <View
                    key={`terrain-route-${index}`}
                    style={[
                      styles.terrainRouteSegment,
                      {
                        left: point.x,
                        top: point.y,
                        width: length,
                        transform: [{ rotate: angle }],
                      },
                    ]}
                  />
                );
              })}

              {terrainState.points[0] ? (
                <View
                  style={[
                    styles.terrainMarker,
                    styles.startMarker,
                    {
                      left: terrainState.points[0].x - 16,
                      top: terrainState.points[0].y - 16,
                    },
                  ]}
                >
                  <Ionicons name="flag-outline" size={15} color={colors.white} />
                </View>
              ) : null}

              {terrainState.points.length > 1 ? (
                <View
                  style={[
                    styles.terrainMarker,
                    styles.endMarker,
                    {
                      left: terrainState.points[terrainState.points.length - 1].x - 16,
                      top: terrainState.points[terrainState.points.length - 1].y - 16,
                    },
                  ]}
                >
                  <Ionicons name="location" size={15} color={colors.white} />
                </View>
              ) : null}

              {terrainState.userPoint ? (
                <View
                  style={[
                    styles.terrainUserMarker,
                    {
                      left: terrainState.userPoint.x - 11,
                      top: terrainState.userPoint.y - 11,
                    },
                  ]}
                />
              ) : null}
            </View>
          </View>

          <View style={styles.terrainInfo}>
            <Text style={styles.terrainInfoTitle}>Vista 3D del terreno</Text>
            <Text style={styles.terrainInfoText}>
              {terrainState.elevationGain} m desnivel aprox. - {trail?.difficulty || "Dificultad a confirmar"}
            </Text>
          </View>
        </View>
      ) : (
        <View
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
          {isTileLoading && cachedTiles.length > 0
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

          {mapState.tiles.map((tile) => (
            <Image
              key={tile.key}
              fadeDuration={0}
              source={{ uri: tileUriOverrides[tile.key] || tile.url }}
              style={[styles.tile, { left: tile.left, top: tile.top }]}
            />
          ))}

          {mapState.points.slice(0, -1).map((point, index) => {
            const nextPoint = mapState.points[index + 1];
            const dx = nextPoint.x - point.x;
            const dy = nextPoint.y - point.y;
            const length = Math.sqrt(dx * dx + dy * dy);
            const angle = `${Math.atan2(dy, dx)}rad`;

            return (
              <View
                key={`${point.x}-${point.y}-${index}`}
                style={[
                  styles.routeSegment,
                  {
                    left: point.x,
                    top: point.y,
                    width: length,
                    transform: [{ rotate: angle }],
                  },
                ]}
              />
            );
          })}

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
        </View>
      )}

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
        <Pressable
          onPress={() => setLayer("terrain")}
          style={[styles.layerButton, layer === "terrain" && styles.layerButtonActive]}
        >
          <Text style={[styles.layerLabel, layer === "terrain" && styles.layerLabelActive]}>
            Terreno
          </Text>
        </Pressable>
        <Pressable
          onPress={() => setLayer("satellite")}
          style={[styles.layerButton, layer === "satellite" && styles.layerButtonActive]}
        >
          <Text style={[styles.layerLabel, layer === "satellite" && styles.layerLabelActive]}>
            Satelite
          </Text>
        </Pressable>
        </View>
      ) : null}

      <Pressable
        onPress={() => setIsPerspective((current) => !current)}
        style={[
          styles.perspectiveButton,
          { top: controlsTopOffset + 50 },
          immersive && styles.immersivePerspectiveButton,
          isPerspective && styles.perspectiveButtonActive,
        ]}
      >
        <Ionicons
          name="layers-outline"
          size={17}
          color={isPerspective ? colors.white : colors.greenDark}
        />
        <Text
          style={[
            styles.perspectiveLabel,
            isPerspective && styles.perspectiveLabelActive,
          ]}
        >
          3D
        </Text>
      </Pressable>

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

      {showDetailsCard ? (
        <View style={styles.mapCard}>
          <Text style={styles.mapLabel}>{trail?.name || "Mapa del recorrido"}</Text>
          <Text style={styles.mapMeta}>
            {trail?.distance_km ? `${trail.distance_km} km` : "Distancia a confirmar"} -{" "}
            {trail?.difficulty || "Dificultad a confirmar"}
          </Text>
        </View>
      ) : null}

      {!isPerspective ? (
        <Text style={styles.attribution}>
          {layer === "terrain"
            ? "Esri World Topo Map"
            : layer === "satellite"
              ? "Esri World Imagery"
              : "OpenStreetMap contributors"}
        </Text>
      ) : null}

      {showUserLocation && (permissionDenied || locationError) ? (
        <View style={styles.locationWarning}>
          <Ionicons name="location-outline" size={14} color={colors.danger} />
          <Text style={styles.locationWarningText}>
            Activa la ubicacion para ver tu posicion.
          </Text>
        </View>
      ) : null}

      {isTestingLocation ? (
        <View style={styles.testingBadge}>
          <Ionicons name="flask-outline" size={14} color={colors.greenDark} />
          <Text style={styles.testingBadgeText}>Testing</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
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
  terrainSky: {
    backgroundColor: "#B8D9E8",
    height: "45%",
    left: 0,
    opacity: 0.95,
    position: "absolute",
    right: 0,
    top: 0,
  },
  mountainFar: {
    backgroundColor: "#D6E6C7",
    height: "28%",
    left: "-18%",
    position: "absolute",
    right: "-18%",
    top: "25%",
    transform: [{ rotate: "-5deg" }, { skewX: "-18deg" }],
  },
  mountainNear: {
    backgroundColor: "#BED8A5",
    height: "22%",
    left: "-16%",
    opacity: 0.92,
    position: "absolute",
    right: "-20%",
    top: "35%",
    transform: [{ rotate: "7deg" }, { skewX: "24deg" }],
  },
  terrainHorizon: {
    backgroundColor: "#EEF5DF",
    borderTopColor: "rgba(255,255,255,0.72)",
    borderTopWidth: 2,
    height: "14%",
    left: "-8%",
    position: "absolute",
    right: "-8%",
    top: "43%",
    transform: [{ rotate: "-2deg" }],
  },
  terrainPlane: {
    backgroundColor: "#78B97B",
    borderTopColor: "rgba(255,255,255,0.56)",
    borderTopWidth: 2,
    bottom: "-10%",
    height: "68%",
    left: "-20%",
    overflow: "hidden",
    position: "absolute",
    right: "-20%",
    shadowColor: "#174D31",
    shadowOpacity: 0.25,
    shadowRadius: 18,
    transform: [{ perspective: 850 }, { rotateX: "42deg" }],
  },
  terrainMovableContent: {
    bottom: 0,
    left: 0,
    position: "absolute",
    right: 0,
    top: 0,
  },
  terrainBand: {
    borderTopColor: "rgba(255,255,255,0.26)",
    borderTopWidth: 1,
    height: "13%",
    left: "-5%",
    position: "absolute",
    right: "-5%",
    transform: [{ rotate: "-7deg" }],
  },
  terrainRidgeBack: {
    backgroundColor: "rgba(42,112,70,0.16)",
    borderRadius: 999,
    height: "22%",
    left: "-8%",
    position: "absolute",
    right: "20%",
    top: "28%",
    transform: [{ rotate: "-8deg" }],
  },
  terrainRidgeFront: {
    backgroundColor: "rgba(14,78,48,0.18)",
    borderRadius: 999,
    bottom: "8%",
    height: "24%",
    left: "12%",
    position: "absolute",
    right: "-10%",
    transform: [{ rotate: "-10deg" }],
  },
  terrainPillar: {
    backgroundColor: "rgba(36,96,62,0.22)",
    borderRadius: 999,
    position: "absolute",
    width: 10,
    zIndex: 2,
  },
  terrainRouteShadow: {
    backgroundColor: "rgba(23,70,43,0.24)",
    borderRadius: 999,
    height: 13,
    position: "absolute",
    transformOrigin: "left center",
    zIndex: 1,
  },
  terrainRouteWall: {
    backgroundColor: "rgba(168,59,50,0.34)",
    borderBottomColor: "rgba(255,255,255,0.22)",
    borderBottomWidth: 1,
    position: "absolute",
    transformOrigin: "left top",
    zIndex: 3,
  },
  terrainRouteSegment: {
    backgroundColor: colors.danger,
    borderColor: colors.white,
    borderRadius: 999,
    borderWidth: 1,
    height: 8,
    position: "absolute",
    transformOrigin: "left center",
    zIndex: 4,
  },
  terrainMarker: {
    alignItems: "center",
    borderColor: colors.white,
    borderRadius: 16,
    borderWidth: 2,
    height: 32,
    justifyContent: "center",
    position: "absolute",
    shadowColor: "#000",
    shadowOpacity: 0.22,
    shadowRadius: 8,
    width: 32,
    zIndex: 7,
  },
  terrainUserMarker: {
    backgroundColor: "#2376D9",
    borderColor: colors.white,
    borderRadius: 11,
    borderWidth: 3,
    height: 22,
    position: "absolute",
    shadowColor: "#000",
    shadowOpacity: 0.22,
    shadowRadius: 7,
    width: 22,
    zIndex: 8,
  },
  terrainInfo: {
    backgroundColor: "rgba(255,255,255,0.94)",
    borderRadius: 18,
    bottom: 14,
    left: 14,
    paddingHorizontal: 14,
    paddingVertical: 12,
    position: "absolute",
    right: 14,
    zIndex: 5,
  },
  terrainInfoTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "900",
  },
  terrainInfoText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "800",
    marginTop: 4,
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
    bottom: 98,
    color: colors.muted,
    fontSize: 10,
    fontWeight: "800",
    paddingHorizontal: 7,
    paddingVertical: 3,
    position: "absolute",
    right: 10,
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
    top: 112,
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
    top: 112,
    zIndex: 7,
  },
  testingBadgeText: {
    color: colors.greenDark,
    fontSize: 12,
    fontWeight: "900",
  },
});
