import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Image,
  LayoutChangeEvent,
  PanResponder,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Trail } from "../../types";
import { colors } from "./MiSenderoUI";

type Coordinate = [number, number];
type MapLayer = "standard" | "terrain";

type TrailMapProps = {
  trail: Trail | null;
  fitRoute?: boolean;
  immersive?: boolean;
  initialPerspective?: boolean;
  showDetailsCard?: boolean;
};

const TILE_SIZE = 256;
const DEFAULT_ZOOM = 13;
const DEFAULT_CENTER: Coordinate = [-41.1734, -71.4752];
const MIN_ZOOM = 10;
const MAX_ZOOM_BY_LAYER: Record<MapLayer, number> = {
  standard: 18,
  terrain: 17,
};

const parseCoordinates = (value: string | null | undefined): Coordinate[] => {
  if (!value) return [];

  try {
    const parsed = JSON.parse(value);

    if (!Array.isArray(parsed)) return [];

    return parsed.filter(
      (point): point is Coordinate =>
        Array.isArray(point) &&
        point.length >= 2 &&
        Number.isFinite(point[0]) &&
        Number.isFinite(point[1])
    );
  } catch (error) {
    return [];
  }
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

const getTileUrl = (layer: MapLayer, zoom: number, x: number, y: number) => {
  const tileX = wrapTileX(x, zoom);

  if (layer === "terrain") {
    return `https://tile.opentopomap.org/${zoom}/${tileX}/${y}.png`;
  }

  return `https://tile.openstreetmap.org/${zoom}/${tileX}/${y}.png`;
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
}: TrailMapProps) {
  const [layout, setLayout] = useState({ width: 0, height: 0 });
  const [layer, setLayer] = useState<MapLayer>("terrain");
  const [isPerspective, setIsPerspective] = useState(initialPerspective);
  const [activeZoom, setActiveZoom] = useState(trail?.map_zoom || DEFAULT_ZOOM);
  const [activeCenter, setActiveCenter] = useState<Coordinate>(DEFAULT_CENTER);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const centerRef = useRef(activeCenter);
  const zoomRef = useRef(activeZoom);
  const centerLat = trail?.center_lat;
  const centerLng = trail?.center_lng;
  const hasRealCenter =
    typeof centerLat === "number" && typeof centerLng === "number";
  const trailCenter: Coordinate = hasRealCenter ? [centerLat, centerLng] : DEFAULT_CENTER;
  const route = useMemo(
    () => parseCoordinates(trail?.route_coordinates),
    [trail?.route_coordinates]
  );
  const routePoints = useMemo(
    () => (route.length > 1 ? route : [trailCenter]),
    [route, trailCenter[0], trailCenter[1]]
  );
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
  }, [trail?.id, trailCenter[0], trailCenter[1], layout.width, layout.height, fitRoute, layer]);

  useEffect(() => {
    centerRef.current = activeCenter;
    zoomRef.current = zoom;
  }, [activeCenter, zoom]);

  useEffect(() => {
    if (activeZoom > maxZoom) {
      setActiveZoom(maxZoom);
    }
  }, [activeZoom, maxZoom]);

  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, gesture) =>
          Math.abs(gesture.dx) > 5 || Math.abs(gesture.dy) > 5,
        onPanResponderMove: (_, gesture) => {
          setPanOffset({ x: gesture.dx, y: gesture.dy });
        },
        onPanResponderRelease: (_, gesture) => {
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
          setPanOffset({ x: 0, y: 0 });
        },
      }),
    []
  );

  const changeZoom = (delta: number) => {
    setActiveZoom((currentZoom) =>
      Math.max(MIN_ZOOM, Math.min(maxZoom, currentZoom + delta))
    );
  };

  const resetView = () => {
    const nextView = getInitialView();

    setActiveCenter(nextView.center);
    setActiveZoom(nextView.zoom);
    setPanOffset({ x: 0, y: 0 });
  };

  const mapState = useMemo(() => {
    if (!layout.width || !layout.height) {
      return { tiles: [], points: [] };
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
    const tiles = [];

    for (let x = minTileX; x <= maxTileX; x += 1) {
      for (let y = minTileY; y <= maxTileY; y += 1) {
        if (y < 0 || y >= 2 ** zoom) continue;

        tiles.push({
          key: `${layer}-${zoom}-${x}-${y}`,
          url: getTileUrl(layer, zoom, x, y),
          left: x * TILE_SIZE - topLeft.x,
          top: y * TILE_SIZE - topLeft.y,
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

    return { tiles, points };
  }, [activeCenter[0], activeCenter[1], layer, layout.height, layout.width, routePoints, zoom]);

  const onLayout = (event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    setLayout({ width, height });
  };

  return (
    <View
      style={[styles.map, immersive && styles.immersiveMap]}
      onLayout={onLayout}
      {...panResponder.panHandlers}
    >
      <View
        style={[
          styles.mapContent,
          isPerspective && styles.perspectiveContent,
          { transform: [{ translateX: panOffset.x }, { translateY: panOffset.y }] },
          isPerspective && {
            transform: [
              { translateX: panOffset.x },
              { translateY: panOffset.y + 54 },
              { perspective: 900 },
              { rotateX: "52deg" },
              { scale: 1.42 },
            ],
          },
        ]}
      >
        {mapState.tiles.map((tile) => (
          <Image
            key={tile.key}
            source={{ uri: tile.url }}
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
      </View>

      <View style={[styles.layerControl, immersive && styles.immersiveLayerControl]}>
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
      </View>

      <Pressable
        onPress={() => setIsPerspective((current) => !current)}
        style={[
          styles.perspectiveButton,
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
          Perspectiva
        </Text>
      </Pressable>

      <View style={[styles.zoomControl, immersive && styles.immersiveZoomControl]}>
        <Pressable
          onPress={() => changeZoom(1)}
          disabled={zoom >= maxZoom}
          style={[styles.zoomButton, zoom >= maxZoom && styles.disabledControl]}
        >
          <Ionicons name="add" size={22} color={colors.ink} />
        </Pressable>
        <View style={styles.zoomDivider} />
        <Pressable
          onPress={() => changeZoom(-1)}
          disabled={zoom <= MIN_ZOOM}
          style={[styles.zoomButton, zoom <= MIN_ZOOM && styles.disabledControl]}
        >
          <Ionicons name="remove" size={22} color={colors.ink} />
        </Pressable>
        <View style={styles.zoomDivider} />
        <Pressable onPress={resetView} style={styles.zoomButton}>
          <Ionicons name="locate-outline" size={20} color={colors.ink} />
        </Pressable>
      </View>

      <View style={[styles.zoomBadge, immersive && styles.immersiveZoomBadge]}>
        <Text style={styles.zoomBadgeText}>z{zoom}</Text>
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

      <Text style={styles.attribution}>
        {layer === "terrain"
          ? "OpenTopoMap | OpenStreetMap contributors"
          : "OpenStreetMap contributors"}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  map: {
    backgroundColor: "#DDE9E0",
    borderRadius: 24,
    flex: 1,
    marginBottom: 16,
    minHeight: 320,
    overflow: "hidden",
    position: "relative",
  },
  immersiveMap: {
    borderRadius: 0,
    marginBottom: 0,
    minHeight: 0,
  },
  mapContent: {
    flex: 1,
  },
  perspectiveContent: {
    height: "100%",
  },
  tile: {
    height: TILE_SIZE,
    position: "absolute",
    width: TILE_SIZE,
  },
  layerControl: {
    backgroundColor: "rgba(255,255,255,0.94)",
    borderRadius: 16,
    flexDirection: "row",
    left: 12,
    padding: 4,
    position: "absolute",
    top: 12,
    zIndex: 6,
  },
  immersiveLayerControl: {
    top: 74,
  },
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
    top: 12,
    zIndex: 6,
  },
  immersiveZoomControl: {
    top: 74,
  },
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
  zoomBadge: {
    backgroundColor: "rgba(255,255,255,0.94)",
    borderRadius: 12,
    paddingHorizontal: 9,
    paddingVertical: 5,
    position: "absolute",
    right: 12,
    top: 148,
    zIndex: 6,
  },
  immersiveZoomBadge: {
    top: 210,
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
    top: 62,
    zIndex: 6,
  },
  immersivePerspectiveButton: {
    top: 124,
  },
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
  zoomBadgeText: {
    color: colors.ink,
    fontSize: 11,
    fontWeight: "900",
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
});
