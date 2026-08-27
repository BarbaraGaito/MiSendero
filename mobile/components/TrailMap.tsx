import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Image,
  DimensionValue,
  LayoutChangeEvent,
  PanResponder,
  Pressable,
  StyleProp,
  StyleSheet,
  Text,
  View,
  ViewStyle,
} from "react-native";
import Svg, { Path } from "react-native-svg";
import { Trail } from "../../types";
import {
  Coordinate,
  getClosestPointOnRoute,
  getRouteStart,
  parseRouteCoordinates,
} from "../../services/geoUtils";
import {
  getTileRemoteUrl,
  resolveCachedTileUri,
} from "../../services/mapTileCache";
import { useDeviceLocation } from "../hooks/useDeviceLocation";
import { colors } from "./MiSenderoUI";
import {
  Terrain3DScene,
  getTerrainElevationGainMeters,
} from "./Terrain3DScene";

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

type RouteArrow = ScreenPoint & {
  key: string;
  angle: string;
};

type TerrainLabel = ScreenPoint & {
  key: string;
  text: string;
  angle?: string;
  variant: "route" | "peak" | "elevation";
};

type TerrainPoint = ScreenPoint & {
  baseY: number;
  z: number;
};

type TrailMapProps = {
  trail: Trail | null;
  fitRoute?: boolean;
  immersive?: boolean;
  initialPerspective?: boolean;
  showDetailsCard?: boolean;
  showUserLocation?: boolean;
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
};

const TILE_SIZE = 256;
const DEFAULT_ZOOM = 13;
const DEFAULT_CENTER: Coordinate = [-41.1734, -71.4752];
const MIN_ZOOM = 10;
const MAX_TERRAIN_POINTS = 48;
const MAX_ZOOM_BY_LAYER: Record<MapLayer, number> = {
  standard: 18,
  terrain: 17,
  satellite: 19,
};

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));

const getDifficultyFactor = (difficulty: string | null | undefined) => {
  const normalized = difficulty?.toLowerCase() ?? "";

  if (normalized.includes("alta") || normalized.includes("dificil")) return 1.35;
  if (normalized.includes("media") || normalized.includes("moderada")) return 1;
  return 0.72;
};

const getRouteDistanceKm = (points: Coordinate[]) => {
  if (points.length < 2) return 0;

  let totalMeters = 0;

  for (let index = 1; index < points.length; index += 1) {
    const [previousLat, previousLng] = points[index - 1];
    const [nextLat, nextLng] = points[index];
    const deltaLat = (nextLat - previousLat) * 111_000;
    const deltaLng =
      (nextLng - previousLng) *
      111_000 *
      Math.cos(((previousLat + nextLat) / 2) * (Math.PI / 180));

    totalMeters += Math.hypot(deltaLat, deltaLng);
  }

  return totalMeters / 1000;
};

const getSampledRoutePoints = (points: Coordinate[], maxPoints: number) => {
  if (points.length <= maxPoints) return points;

  return Array.from({ length: maxPoints }, (_, index) => {
    const sourceIndex = Math.round((index / (maxPoints - 1)) * (points.length - 1));
    return points[sourceIndex];
  });
};

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

const wrapTileX = (x: number, zoom: number) => {
  const max = 2 ** zoom;
  return ((x % max) + max) % max;
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

const createOffsetRoutePoints = (
  points: ScreenPoint[],
  offset: number,
  wave = 0
) =>
  points.map((point, index) => {
    const previous = points[Math.max(0, index - 1)];
    const next = points[Math.min(points.length - 1, index + 1)];
    const dx = next.x - previous.x;
    const dy = next.y - previous.y;
    const length = Math.max(1, Math.hypot(dx, dy));
    const shift = offset + Math.sin(index * 0.9) * wave;

    return {
      x: point.x + (-dy / length) * shift,
      y: point.y + (dx / length) * shift,
    };
  });

const buildTerrainPaths = (
  points: ScreenPoint[],
  layer: MapLayer,
  layout: { width: number; height: number }
) => {
  if (points.length < 2 || !layout.width || !layout.height) {
    return { contours: [], ridgeShadows: [], creek: null, secondaryTrails: [] };
  }

  const bounds = getRouteBounds(points);
  const padding = Math.max(84, Math.min(layout.width, layout.height) * 0.24);
  const minX = Math.max(-padding, Math.min(bounds.minX - padding, -24));
  const maxX = Math.min(layout.width + padding, Math.max(bounds.maxX + padding, layout.width + 24));
  const minY = Math.max(-padding, Math.min(bounds.minY - padding, -24));
  const maxY = Math.min(layout.height + padding, Math.max(bounds.maxY + padding, layout.height + 24));
  const width = Math.max(160, maxX - minX);
  const height = Math.max(160, maxY - minY);
  const contourCount = layer === "standard" ? 8 : 12;
  const { contours, ridgeShadows } = buildContourTerrainPaths({
    contourCount,
    height,
    layer,
    minX,
    minY,
    width,
  });

  const creekPoints = createOffsetRoutePoints(points, 48, 12);
  const secondaryTrailPoints = createOffsetRoutePoints(points, -58, 16);
  const secondaryTrailPointsAlt = createOffsetRoutePoints(points, 88, 10).slice(
    Math.max(0, Math.floor(points.length * 0.18)),
    Math.max(2, Math.ceil(points.length * 0.82))
  );

  return {
    contours,
    ridgeShadows,
    creek: {
      key: "creek",
      path: pointsToSvgPath(creekPoints),
      color: "#58B7D8",
      opacity: layer === "standard" ? 0.26 : 0.5,
      width: 2.1,
    } as TerrainPath,
    secondaryTrails: [
      {
        key: "secondary-main",
        path: pointsToSvgPath(secondaryTrailPoints),
        color: "#EAC091",
        opacity: layer === "standard" ? 0.24 : 0.44,
        width: 1.55,
        dash: "7 6",
      },
      {
        key: "secondary-alt",
        path: pointsToSvgPath(secondaryTrailPointsAlt),
        color: "#DB7959",
        opacity: layer === "standard" ? 0.18 : 0.34,
        width: 1.25,
        dash: "5 5",
      },
    ],
  };
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

const getTerrainBands = () =>
  Array.from({ length: 9 }, (_, index) => ({
    key: `terrain-band-${index}`,
    top: `${index * 11}%` as DimensionValue,
    opacity: 0.7 - index * 0.025,
    color: index < 3 ? "#D5E8BE" : index < 6 ? "#A9D39B" : "#6FAC77",
  }));

const getTerrainState = ({
  layout,
  locationCoordinate,
  routePoints,
  trail,
  trailCenter,
}: {
  layout: { width: number; height: number };
  locationCoordinate: Coordinate | null;
  routePoints: Coordinate[];
  trail: Trail | null;
  trailCenter: Coordinate;
}) => {
  if (!layout.width || !layout.height) {
    return {
      points: [] as TerrainPoint[],
      bands: [] as ReturnType<typeof getTerrainBands>,
      userPoint: null as ScreenPoint | null,
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
  const points = getTerrainPoints(
    projectedPoints,
    { minX, minY, offsetX, offsetY, fitScale },
    difficultyFactor,
    elevationGain
  );
  const userPoint = locationCoordinate
    ? {
        x: offsetX + (project(locationCoordinate, DEFAULT_ZOOM).x - minX) * fitScale,
        y: offsetY + (project(locationCoordinate, DEFAULT_ZOOM).y - minY) * fitScale,
      }
    : null;

  return {
    points,
    bands: getTerrainBands(),
    userPoint,
    distanceKm,
    elevationGain,
  };
};

const getTerrainPoints = (
  projectedPoints: ScreenPoint[],
  view: { minX: number; minY: number; offsetX: number; offsetY: number; fitScale: number },
  difficultyFactor: number,
  elevationGain: number
) =>
  projectedPoints.map((point, index) => {
    const progress =
      projectedPoints.length <= 1 ? 0 : index / (projectedPoints.length - 1);
    const wave = Math.sin(progress * Math.PI * 2.4) * 18;
    const localPeak = Math.sin(progress * Math.PI) * 58 * difficultyFactor;
    const secondaryPeak = Math.max(0, Math.sin((progress - 0.18) * Math.PI * 2)) * 28;
    const climb = progress * elevationGain * 0.045 * difficultyFactor;
    const z = Math.max(18, 34 + localPeak + secondaryPeak + climb);

    return {
      x: view.offsetX + (point.x - view.minX) * view.fitScale,
      y: view.offsetY + (point.y - view.minY) * view.fitScale - wave - z,
      baseY: view.offsetY + (point.y - view.minY) * view.fitScale + 18,
      z,
    };
  });

function RouteSegments({
  points,
  segmentStyle,
  getSegmentLeft,
  getSegmentTop,
  keyPrefix,
}: {
  points: ScreenPoint[];
  segmentStyle: StyleProp<ViewStyle>;
  getSegmentLeft?: (point: ScreenPoint, nextPoint: ScreenPoint) => number;
  getSegmentTop?: (point: ScreenPoint, nextPoint: ScreenPoint) => number;
  keyPrefix: string;
}) {
  return (
    <>
      {points.slice(0, -1).map((point, index) => {
        const nextPoint = points[index + 1];
        const dx = nextPoint.x - point.x;
        const dy = nextPoint.y - point.y;
        const length = Math.sqrt(dx * dx + dy * dy);
        const angle = `${Math.atan2(dy, dx)}rad`;

        return (
          <View
            key={`${keyPrefix}-${index}`}
            style={[
              segmentStyle,
              {
                left: getSegmentLeft ? getSegmentLeft(point, nextPoint) : point.x,
                top: getSegmentTop ? getSegmentTop(point, nextPoint) : point.y,
                width: length,
                transform: [{ rotate: angle }],
              },
            ]}
          />
        );
      })}
    </>
  );
}

function LayerControl({
  layer,
  immersive,
  controlsTopOffset,
  setLayer,
}: {
  layer: MapLayer;
  immersive: boolean;
  controlsTopOffset: number;
  setLayer: (layer: MapLayer) => void;
}) {
  const layers: Array<{ id: MapLayer; label: string }> = [
    { id: "standard", label: "Mapa" },
    { id: "terrain", label: "Terreno" },
    { id: "satellite", label: "Satelite" },
  ];

  return (
    <View
      style={[
        styles.layerControl,
        { top: controlsTopOffset },
        immersive && styles.immersiveLayerControl,
      ]}
    >
      {layers.map((item) => (
        <Pressable
          key={item.id}
          onPress={() => setLayer(item.id)}
          style={[styles.layerButton, layer === item.id && styles.layerButtonActive]}
        >
          <Text style={[styles.layerLabel, layer === item.id && styles.layerLabelActive]}>
            {item.label}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

const getMapAttribution = (layer: MapLayer) => {
  if (layer === "terrain") return "Esri World Topo Map";
  if (layer === "satellite") return "Esri World Imagery";
  return "OpenStreetMap contributors";
};

const getMapDecorations = ({
  layer,
  layout,
  points,
  terrainElevationGain,
  trailName,
}: {
  layer: MapLayer;
  layout: { width: number; height: number };
  points: ScreenPoint[];
  terrainElevationGain: number;
  trailName: string | null | undefined;
}) => {
  const routePath = pointsToSvgPath(points);
  const routeLabel = getPointAtRouteFraction(points, 0.5);
  const peakLabel = getPointAtRouteFraction(points, 0.22);
  const elevationLabel = getPointAtRouteFraction(points, 0.78);

  return {
    ...buildTerrainPaths(points, layer, layout),
    arrows: getRouteArrows(points),
    labels: getTerrainLabels(routeLabel, peakLabel, elevationLabel, trailName, terrainElevationGain),
    routePath,
  };
};

const buildContourTerrainPaths = ({
  contourCount,
  height,
  layer,
  minX,
  minY,
  width,
}: {
  contourCount: number;
  height: number;
  layer: MapLayer;
  minX: number;
  minY: number;
  width: number;
}) => {
  const contours: TerrainPath[] = [];
  const ridgeShadows: TerrainPath[] = [];

  for (let index = 0; index < contourCount; index += 1) {
    const contourPoints = getContourPoints(index, contourCount, minX, minY, width, height);

    contours.push(getContourPath(index, layer, contourPoints));

    if (index % 3 === 0) {
      ridgeShadows.push(getRidgeShadowPath(index, layer, contourPoints));
    }
  }

  return { contours, ridgeShadows };
};

const getContourPoints = (
  index: number,
  contourCount: number,
  minX: number,
  minY: number,
  width: number,
  height: number
) => {
  const baseY = minY + ((index + 1) / (contourCount + 1)) * height;

  return Array.from({ length: 14 }, (_, step) => {
    const progress = step / 13;

    return {
      x: minX + progress * width,
      y:
        baseY +
        Math.sin(progress * Math.PI * 2.2 + index * 0.72) * 18 +
        Math.cos(progress * Math.PI * 4.1 + index * 0.31) * 7,
    };
  });
};

const getContourPath = (
  index: number,
  layer: MapLayer,
  contourPoints: ScreenPoint[]
): TerrainPath => ({
  key: `contour-${index}`,
  path: pointsToSvgPath(contourPoints),
  color: layer === "satellite" ? "#F4F0DE" : "#FFFFFF",
  opacity: layer === "standard" ? 0.18 : 0.34,
  width: index % 3 === 0 ? 1.45 : 0.9,
});

const getRidgeShadowPath = (
  index: number,
  layer: MapLayer,
  contourPoints: ScreenPoint[]
): TerrainPath => ({
  key: `ridge-${index}`,
  path: pointsToSvgPath(
    contourPoints.map((point) => ({ x: point.x + 2, y: point.y + 4 }))
  ),
  color: "#1F2B1F",
  opacity: layer === "satellite" ? 0.18 : 0.1,
  width: 2.2,
});

const getRouteArrows = (points: ScreenPoint[]) =>
  [0.24, 0.5, 0.76]
    .map((fraction, index) => {
      const point = getPointAtRouteFraction(points, fraction);
      return point
        ? {
            key: `direction-${index}`,
            x: point.x,
            y: point.y,
            angle: point.angle,
          }
        : null;
    })
    .filter((point): point is RouteArrow => Boolean(point));

const getTerrainLabels = (
  routeLabel: (ScreenPoint & { angle: string }) | null,
  peakLabel: (ScreenPoint & { angle: string }) | null,
  elevationLabel: (ScreenPoint & { angle: string }) | null,
  trailName: string | null | undefined,
  terrainElevationGain: number
) => {
  const labels: TerrainLabel[] = [];

  if (routeLabel) {
    labels.push({
      key: "route-label",
      text: shortenTrailName(trailName),
      x: routeLabel.x - 72,
      y: routeLabel.y - 28,
      angle: routeLabel.angle,
      variant: "route",
    });
  }

  if (peakLabel) {
    labels.push({
      key: "peak-label",
      text: "Cota alta",
      x: peakLabel.x + 14,
      y: peakLabel.y - 48,
      variant: "peak",
    });
  }

  if (elevationLabel) {
    labels.push({
      key: "elevation-label",
      text: `${terrainElevationGain} m`,
      x: elevationLabel.x + 12,
      y: elevationLabel.y + 18,
      variant: "elevation",
    });
  }

  return labels;
};

export function TrailMap({
  trail,
  fitRoute = false,
  immersive = false,
  initialPerspective = false,
  showDetailsCard = true,
  showUserLocation = true,
  controlsTopOffset = 12,
  allowSatellite = true,
  selectedCoordinate = null,
  selectionToleranceMeters = 80,
  onSelectCoordinate,
  onSelectionRejected,
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
    panOffsetRef.current = panOffset;
    layoutRef.current = layout;
    maxZoomRef.current = maxZoom;
    isPerspectiveRef.current = isPerspective;
    terrainOffsetRef.current = terrainOffset;
    terrainScaleRef.current = terrainScale;
  }, [activeCenter, isPerspective, layout, maxZoom, panOffset, terrainOffset, terrainScale, zoom]);

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

  const handleMapPress = (x: number, y: number) => {
    if (!onSelectCoordinate || isPerspectiveRef.current) return;

    const currentLayout = layoutRef.current;
    if (!currentLayout.width || !currentLayout.height || route.length < 2) {
      onSelectionRejected?.(null);
      return;
    }

    const currentZoom = zoomRef.current;
    const centerPixel = project(centerRef.current, currentZoom);
    const currentPanOffset = panOffsetRef.current;
    const touchCoordinate = unproject(
      {
        x: centerPixel.x - currentLayout.width / 2 + x - currentPanOffset.x,
        y: centerPixel.y - currentLayout.height / 2 + y - currentPanOffset.y,
      },
      currentZoom
    );
    const closest = getClosestPointOnRoute(touchCoordinate, route);

    if (!closest) {
      onSelectionRejected?.(null);
      return;
    }

    if (closest.distanceMeters > selectionToleranceMeters) {
      onSelectionRejected?.(closest.distanceMeters);
      return;
    }

    onSelectCoordinate({
      coordinate: closest.coordinate,
      distanceToRouteMeters: closest.distanceMeters,
      routeProgressMeters: closest.progressMeters,
    });
  };

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

  const terrainElevationGain = useMemo(
    () =>
      getTerrainElevationGainMeters(
        routePoints,
        trail?.difficulty,
        trail?.distance_km
      ),
    [routePoints, trail?.difficulty, trail?.distance_km]
  );
  const mapDecorations = useMemo(
    () =>
      getMapDecorations({
        layer,
        layout,
        points: mapState.points,
        terrainElevationGain,
        trailName: trail?.name,
      }),
    [layer, layout, mapState.points, terrainElevationGain, trail?.name]
  );

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
      onTouchStart={(event) => {
        if (!onSelectCoordinate || event.nativeEvent.touches.length !== 1) return;

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
        if (
          !onSelectCoordinate ||
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
      {...panResponder.panHandlers}
    >
      {isPerspective ? (
        <View style={styles.terrain3dScene}>
          <Terrain3DScene
            routePoints={routePoints}
            fallbackCenter={trailCenter}
            difficulty={trail?.difficulty}
            distanceKm={trail?.distance_km}
            userCoordinate={location?.coordinate ?? null}
            viewOffset={{
              x: terrainOffset.x + panOffset.x,
              y: terrainOffset.y + panOffset.y,
            }}
            viewScale={terrainScale}
          />
          <View style={styles.terrainInfo}>
            <Text style={styles.terrainInfoTitle}>Vista 3D del terreno</Text>
            <Text style={styles.terrainInfoText}>
              {terrainElevationGain} m desnivel aprox. - {trail?.difficulty || "Dificultad a confirmar"}
            </Text>
          </View>
          <View pointerEvents="none" style={styles.terrain3dOverlay}>
            <View style={styles.terrain3dPill}>
              <View style={styles.terrain3dRouteSwatch} />
              <Text style={styles.terrain3dPillText}>
                {shortenTrailName(trail?.name)}
              </Text>
            </View>
            <View style={styles.terrain3dPill}>
              <Ionicons name="analytics-outline" size={13} color={colors.greenDark} />
              <Text style={styles.terrain3dPillText}>Curvas de nivel</Text>
            </View>
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

          {mapDecorations.routePath ? (
            <Svg
              pointerEvents="none"
              style={styles.mapVectorOverlay}
              width={layout.width}
              height={layout.height}
            >
              {mapDecorations.ridgeShadows.map((path) => (
                <Path
                  key={path.key}
                  d={path.path}
                  fill="none"
                  stroke={path.color}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeOpacity={path.opacity}
                  strokeWidth={path.width}
                />
              ))}
              {mapDecorations.contours.map((path) => (
                <Path
                  key={path.key}
                  d={path.path}
                  fill="none"
                  stroke={path.color}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeOpacity={path.opacity}
                  strokeWidth={path.width}
                />
              ))}
              {mapDecorations.secondaryTrails.map((path) => (
                <Path
                  key={path.key}
                  d={path.path}
                  fill="none"
                  stroke={path.color}
                  strokeDasharray={path.dash}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeOpacity={path.opacity}
                  strokeWidth={path.width}
                />
              ))}
              {mapDecorations.creek ? (
                <Path
                  d={mapDecorations.creek.path}
                  fill="none"
                  stroke={mapDecorations.creek.color}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeOpacity={mapDecorations.creek.opacity}
                  strokeWidth={mapDecorations.creek.width}
                />
              ) : null}
              <Path
                d={mapDecorations.routePath}
                fill="none"
                stroke="#2D201B"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeOpacity={0.34}
                strokeWidth={13}
              />
              <Path
                d={mapDecorations.routePath}
                fill="none"
                stroke="#FFFFFF"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeOpacity={0.92}
                strokeWidth={8}
              />
              <Path
                d={mapDecorations.routePath}
                fill="none"
                stroke="#E85B35"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={5.4}
              />
            </Svg>
          ) : null}

          {mapDecorations.labels.map((label) => (
            <View
              key={label.key}
              pointerEvents="none"
              style={[
                styles.terrainMapLabel,
                label.variant === "route" && styles.terrainMapLabelRoute,
                label.variant === "peak" && styles.terrainMapLabelPeak,
                label.variant === "elevation" && styles.terrainMapLabelElevation,
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

          {mapDecorations.arrows.map((arrow) => (
            <View
              key={arrow.key}
              pointerEvents="none"
              style={[
                styles.routeDirectionMarker,
                {
                  left: arrow.x - 10,
                  top: arrow.y - 10,
                  transform: [{ rotate: arrow.angle }],
                },
              ]}
            >
              <Ionicons name="chevron-forward" size={14} color={colors.white} />
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
        {allowSatellite ? (
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
          {getMapAttribution(layer)}
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

      {onSelectCoordinate && !isPerspective ? (
        <View pointerEvents="none" style={styles.selectionHint}>
          <Ionicons name="pin-outline" size={14} color={colors.greenDark} />
          <Text style={styles.selectionHintText}>Toca sobre el sendero</Text>
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
  terrain3dOverlay: {
    alignItems: "flex-start",
    gap: 8,
    left: 14,
    position: "absolute",
    top: 14,
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
    backgroundColor: "#E85B35",
    borderColor: colors.white,
    borderRadius: 5,
    borderWidth: 1,
    height: 10,
    width: 22,
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
  routeDirectionMarker: {
    alignItems: "center",
    backgroundColor: "#E85B35",
    borderColor: colors.white,
    borderRadius: 10,
    borderWidth: 1,
    height: 20,
    justifyContent: "center",
    position: "absolute",
    shadowColor: "#000",
    shadowOpacity: 0.22,
    shadowRadius: 5,
    width: 20,
    zIndex: 4,
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
    backgroundColor: colors.danger,
    borderColor: colors.white,
    borderRadius: 15,
    borderWidth: 2,
    height: 30,
    justifyContent: "center",
    position: "absolute",
    width: 30,
    zIndex: 6,
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
  selectionHint: {
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.94)",
    borderRadius: 14,
    flexDirection: "row",
    gap: 5,
    left: 12,
    paddingHorizontal: 10,
    paddingVertical: 7,
    position: "absolute",
    top: 154,
    zIndex: 7,
  },
  selectionHintText: {
    color: colors.greenDark,
    fontSize: 12,
    fontWeight: "900",
  },
});
