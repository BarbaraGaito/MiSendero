import { GLView, ExpoWebGLRenderingContext } from "expo-gl";
import { createTerrainRenderer } from "./terrainGraphics";
import { createTerrainImagery } from "./terrainImagery";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import * as THREE from "three";
import { Coordinate } from "../../services/geoUtils";
import {
  clampTerrainScale,
  getTerrainPerspectiveFov,
} from "../../services/mapGestures";
import {
  TERRAIN_SCENE_HALF_SIZE as TERRAIN_HALF_SIZE,
  TerrainSceneModel,
  TerrainScenePoint,
  TerrainSceneWeather,
  TerrainWeatherKind,
  buildTerrainMeshData,
  buildTerrainSceneModel,
  coordinateToTerrainScenePoint,
  drapeRouteOnTerrain,
  getTerrainSceneHeight,
  getTerrainWeatherKind,
  terrainScenePointToCoordinate,
} from "./terrainSceneModel";
import {
  buildTerrainContours, buildTerrainRouteArrows, getTerrainContourInterval,
  getTerrainRouteStations, getTerrainViewReadout, makeCloudTexture, getReportedGroundKind,
} from "./terrainSceneDetails";

export type TerrainMapMarker = {
  id: string;
  coordinate: Coordinate;
  color: string;
  precisionMeters: number;
  selected?: boolean;
  issueSummary?: string;
};

export type Terrain3DSceneHandle = {
  pick: (x: number, y: number) => { coordinate: Coordinate | null; markerId?: string } | null;
};
const EMPTY_MARKERS: TerrainMapMarker[] = [];
type HighlightedSection = { id: string; coordinates: Coordinate[]; color: string };
const EMPTY_SECTIONS: HighlightedSection[] = [];

type Terrain3DSceneProps = {
  terrain: TerrainSceneModel;
  userCoordinate?: Coordinate | null;
  viewOffset: { x: number; y: number };
  viewScale: number;
  weather?: TerrainSceneWeather | null;
  navigationMode?: boolean;
  satelliteTextureEnabled?: boolean;
  markers?: TerrainMapMarker[];
  highlightedSections?: HighlightedSection[];
  focusCoordinate?: Coordinate | null;
  showContours?: boolean;
  overlayTopInset?: number;
  overlayBottomInset?: number;
  onError?: (error: unknown) => void;
};

type NavigationView = {
  anchor: THREE.Vector3;
  direction: THREE.Vector3;
  sightDirection: THREE.Vector3;
};

type SceneHandles = {
  animationFrame: number;
  camera: THREE.PerspectiveCamera;
  gl: ExpoWebGLRenderingContext;
  renderer: THREE.WebGLRenderer;
  routeGroup: THREE.Group;
  scene: THREE.Scene;
  terrainGroup: THREE.Group;
  alignmentRotation: number;
  weatherGroup: THREE.Group;
  sunLight: THREE.DirectionalLight;
  hemiLight: THREE.HemisphereLight;
  navigationView: NavigationView | null;
  model: TerrainSceneModel | null;
  terrainRoute: THREE.Vector3[];
  trackedObject: THREE.Object3D | null;
  imagery: ReturnType<typeof createTerrainImagery> | null;
  markerGroup: THREE.Group;
  groundMesh: THREE.Mesh | null;
};

type SceneReadout = {
  scaleMeters: number;
  scaleFraction: number;
  northDegrees: number;
  labels: { x: number; y: number; text: string }[];
};

const DEFAULT_CAMERA_TARGET_Y = 0.58;
const CAMERA_GROUND_CLEARANCE = 0.8;
const NAVIGATION_EYE_HEIGHT_METERS = 12;
const NAVIGATION_CAMERA_SETBACK_METERS = 5;

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));

const toVector3 = (point: TerrainScenePoint) =>
  new THREE.Vector3(point.x, point.y, point.z);

const disposeObject = (object: THREE.Object3D) => {
  object.traverse((child) => {
    const mesh = child as THREE.Mesh;
    const material = mesh.material as THREE.Material | THREE.Material[] | undefined;

    mesh.geometry?.dispose();
    if (Array.isArray(material)) {
      material.forEach((entry) => {
        (entry as THREE.MeshStandardMaterial).map?.dispose();
        entry.dispose();
      });
    } else {
      (material as THREE.MeshStandardMaterial | undefined)?.map?.dispose();
      material?.dispose();
    }
  });
};

const clearGroup = (group: THREE.Group) => {
  while (group.children.length) {
    const child = group.children[0];
    group.remove(child);
    disposeObject(child);
  }
};

const buildTerrainMesh = (model: TerrainSceneModel) => {
  const mesh = buildTerrainMeshData(model);
  const low = new THREE.Color("#87917E");
  const middle = new THREE.Color("#B0A38C");
  const high = new THREE.Color("#D7D4CD");
  const color = new THREE.Color();
  const colors: number[] = [];

  // Tinte hipsometrico: depende solo de la altura real dentro de la grilla.
  mesh.relativeElevations.forEach((amount) => {
    if (amount < 0.5) {
      color.copy(low).lerp(middle, amount / 0.5);
    } else {
      color.copy(middle).lerp(high, (amount - 0.5) / 0.5);
    }
    colors.push(color.r, color.g, color.b);
  });

  const geometry = new THREE.BufferGeometry();
  geometry.setIndex(mesh.indices);
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(mesh.positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(mesh.uvs, 2));
  geometry.computeVertexNormals();

  const material = new THREE.MeshStandardMaterial({
    roughness: 1,
    metalness: 0,
    vertexColors: true,
  });
  const terrain = new THREE.Mesh(geometry, material);
  terrain.receiveShadow = true;
  terrain.castShadow = true;
  terrain.name = "terrain-dem-surface";

  return terrain;
};

const buildTerrainSkirt = (model: TerrainSceneModel) => {
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const topColor = new THREE.Color("#465641");
  const bottomColor = new THREE.Color("#2A2924");
  const segments = 64;
  const bottomY = -1.15;
  const edges = [
    (t: number) => [-TERRAIN_HALF_SIZE + t * TERRAIN_HALF_SIZE * 2, -TERRAIN_HALF_SIZE],
    (t: number) => [TERRAIN_HALF_SIZE, -TERRAIN_HALF_SIZE + t * TERRAIN_HALF_SIZE * 2],
    (t: number) => [TERRAIN_HALF_SIZE - t * TERRAIN_HALF_SIZE * 2, TERRAIN_HALF_SIZE],
    (t: number) => [-TERRAIN_HALF_SIZE, TERRAIN_HALF_SIZE - t * TERRAIN_HALF_SIZE * 2],
  ];

  edges.forEach((getPoint) => {
    const vertexOffset = positions.length / 3;
    for (let index = 0; index <= segments; index += 1) {
      const [x, z] = getPoint(index / segments);
      const topY = getTerrainSceneHeight(model, x, z);
      positions.push(x, topY, z, x, bottomY, z);
      colors.push(topColor.r, topColor.g, topColor.b, bottomColor.r, bottomColor.g, bottomColor.b);
      if (index < segments) {
        const offset = vertexOffset + index * 2;
        indices.push(offset, offset + 2, offset + 1, offset + 1, offset + 2, offset + 3);
      }
    }
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setIndex(indices);
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  geometry.computeVertexNormals();
  const skirt = new THREE.Mesh(
    geometry,
    new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1, side: THREE.DoubleSide })
  );
  skirt.receiveShadow = true;
  return skirt;
};

const makeTerrainTrailRibbon = (
  centerLine: THREE.Vector3[],
  model: TerrainSceneModel,
  halfWidth: number,
  color: string,
  lift: number,
  highlighted: boolean
) => {
  const positions: number[] = [];
  const vertexColors: number[] = [];
  const indices: number[] = [];
  const baseColor = new THREE.Color(color);

  centerLine.forEach((point, index) => {
    const previous = centerLine[Math.max(0, index - 1)];
    const next = centerLine[Math.min(centerLine.length - 1, index + 1)];
    const dx = next.x - previous.x;
    const dz = next.z - previous.z;
    const length = Math.max(0.001, Math.hypot(dx, dz));
    const normalX = -dz / length;
    const normalZ = dx / length;

    [-1, 1].forEach((side) => {
      const offset = halfWidth * side;
      positions.push(
        point.x + normalX * offset,
        getTerrainSceneHeight(model, point.x + normalX * offset, point.z + normalZ * offset) + lift,
        point.z + normalZ * offset
      );
      vertexColors.push(baseColor.r, baseColor.g, baseColor.b);
    });

    if (index < centerLine.length - 1) {
      const offset = index * 2;
      indices.push(offset, offset + 2, offset + 1, offset + 1, offset + 2, offset + 3);
    }
  });

  const geometry = new THREE.BufferGeometry();
  geometry.setIndex(indices);
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(vertexColors, 3));
  geometry.computeVertexNormals();

  const material = highlighted
    ? new THREE.MeshBasicMaterial({
        side: THREE.DoubleSide,
        vertexColors: true,
      })
    : new THREE.MeshStandardMaterial({
        metalness: 0,
        roughness: 1,
        side: THREE.DoubleSide,
        vertexColors: true,
      });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.castShadow = false;
  mesh.receiveShadow = !highlighted;
  mesh.renderOrder = highlighted ? 3 : 4;

  return mesh;
};

const makeEndpointMarker = (
  position: THREE.Vector3,
  kind: "start" | "finish",
  scale = 1
) => {
  const group = new THREE.Group();
  const white = new THREE.MeshStandardMaterial({ color: "#FFFFFF", roughness: 0.55 });

  if (kind === "finish") {
    const red = new THREE.MeshStandardMaterial({ color: "#D83D35", roughness: 0.55 });
    const poleMaterial = new THREE.MeshStandardMaterial({
      color: "#343A3D",
      metalness: 0.45,
      roughness: 0.42,
    });
    const pole = new THREE.Mesh(
      new THREE.CylinderGeometry(0.018, 0.025, 0.76, 12),
      poleMaterial
    );
    pole.position.y = 0.38;
    const finial = new THREE.Mesh(new THREE.SphereGeometry(0.035, 12, 8), red);
    finial.position.y = 0.78;
    group.add(pole, finial);

    const squareSize = 0.075;
    for (let row = 0; row < 2; row += 1) {
      for (let column = 0; column < 3; column += 1) {
        const square = new THREE.Mesh(
          new THREE.BoxGeometry(squareSize, squareSize, 0.018),
          (row + column) % 2 === 0 ? red : white
        );
        square.position.set(
          -squareSize * (column + 0.55),
          0.705 - squareSize * (row + 0.5),
          0
        );
        group.add(square);
      }
    }
  } else {
    const green = new THREE.MeshStandardMaterial({ color: "#087F4F", roughness: 0.55 });
    const post = new THREE.Mesh(
      new THREE.CylinderGeometry(0.025, 0.032, 0.48, 10),
      green
    );
    post.position.y = 0.25;
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.14, 20, 14), green);
    head.position.y = 0.55;
    group.add(post, head);
  }

  group.position.copy(position);
  group.scale.setScalar(scale);
  group.children.forEach((child) => { child.castShadow = true; });
  return group;
};

const makeUserMarker = (position: THREE.Vector3) => {
  const marker = new THREE.Mesh(
    new THREE.SphereGeometry(0.13, 20, 14),
    new THREE.MeshStandardMaterial({
      color: "#2376D9",
      emissive: "#2376D9",
      emissiveIntensity: 0.1,
      roughness: 0.5,
    })
  );
  marker.position.copy(position);
  marker.position.y += 0.25;
  marker.castShadow = true;
  return marker;
};

const makeVerticalPin = (position: THREE.Vector3, color: string) => {
  const geometry = new THREE.CylinderGeometry(0.035, 0.055, 0.48, 12);
  const material = new THREE.MeshStandardMaterial({
    color,
    roughness: 0.7,
  });
  const pin = new THREE.Mesh(geometry, material);
  pin.position.copy(position);
  pin.position.y += 0.02;
  pin.castShadow = true;

  return pin;
};

const makeMapMarker = (model: TerrainSceneModel, marker: TerrainMapMarker) => {
  const position = coordinateToTerrainScenePoint(model, marker.coordinate);
  if (!position) return null;
  const group = new THREE.Group();
  group.userData.markerId = marker.id;
  group.position.copy(toVector3(position));
  const material = new THREE.MeshBasicMaterial({ color: marker.color });
  const stemHeight = marker.selected ? 0.97 : 0.65;
  const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.025, stemHeight, 8), material);
  stem.position.y = stemHeight / 2;
  const head = new THREE.Group();
  head.position.y = stemHeight + 0.15;
  head.name = "map-marker-head";
  const disc = new THREE.Mesh(new THREE.CircleGeometry(0.2, 24), material);
  const white = new THREE.MeshBasicMaterial({ color: "#FFFFFF" });
  if (marker.selected) {
    const center = new THREE.Mesh(new THREE.CircleGeometry(0.08, 16), white);
    center.position.z = 0.015;
    head.add(disc, center);
  } else {
    const bar = new THREE.Mesh(new THREE.BoxGeometry(0.035, 0.15, 0.01), white);
    bar.position.set(0, 0.04, 0.01);
    const dot = new THREE.Mesh(new THREE.CircleGeometry(0.023, 10), white);
    dot.position.set(0, -0.09, 0.015);
    head.add(disc, bar, dot);
  }
  group.add(stem, head);
  if (marker.precisionMeters > 0 &&
      Math.abs(position.x) + marker.precisionMeters / model.metersPerUnit <= TERRAIN_HALF_SIZE &&
      Math.abs(position.z) + marker.precisionMeters / model.metersPerUnit <= TERRAIN_HALF_SIZE) {
    const radius = marker.precisionMeters / model.metersPerUnit;
    const ring = new THREE.Mesh(new THREE.RingGeometry(radius * 0.94, radius, 48),
      new THREE.MeshBasicMaterial({ color: marker.color, transparent: true, opacity: 0.35, side: THREE.DoubleSide }));
    // Drape the uncertainty boundary onto the DEM, too.
    const vertices = ring.geometry.getAttribute("position");
    for (let index = 0; index < vertices.count; index += 1) {
      const x = vertices.getX(index), z = vertices.getY(index);
      vertices.setXYZ(index, x, getTerrainSceneHeight(model, position.x + x, position.z + z) - position.y + 0.025, z);
    }
    group.add(ring);
  }
  return group;
};

const updateTrackedPosition = (
  handles: SceneHandles,
  userCoordinate: Coordinate | null | undefined,
  navigationMode: boolean
) => {
  if (!handles.model || handles.terrainRoute.length < 2) return;

  if (handles.trackedObject) {
    handles.routeGroup.remove(handles.trackedObject);
    disposeObject(handles.trackedObject);
    handles.trackedObject = null;
  }

  const model = handles.model;
  const terrainRoute = handles.terrainRoute;
  const userScenePoint = userCoordinate ? coordinateToTerrainScenePoint(model, userCoordinate) : null;
  if (navigationMode) {
    const startPoint = userScenePoint ? toVector3(userScenePoint) : terrainRoute[0].clone();
    handles.imagery?.updatePosition(startPoint.x, startPoint.z);
    let nearestIndex = 0;
    if (userScenePoint) {
      let nearestDistance = Infinity;
      terrainRoute.forEach((point, index) => {
        const distance = Math.hypot(point.x - startPoint.x, point.z - startPoint.z);
        if (distance < nearestDistance) { nearestDistance = distance; nearestIndex = index; }
      });
    }
    const ahead = terrainRoute.slice(nearestIndex);
    const nextPoint =
      ahead.find((point, index) => {
        if (index === 0) return false;
        const deltaX = point.x - startPoint.x;
        const deltaZ = point.z - startPoint.z;
        return deltaX * deltaX + deltaZ * deltaZ > 0.0064;
      }) || startPoint.clone().add(startPoint.clone().sub(terrainRoute[Math.max(0, nearestIndex - 1)]));
    const sightPoint =
      ahead.find((point, index) => {
        if (index === 0) return false;
        const deltaX = point.x - startPoint.x;
        const deltaZ = point.z - startPoint.z;
        return deltaX * deltaX + deltaZ * deltaZ > 0.64;
      }) || terrainRoute[terrainRoute.length - 1];
    const localDirection = nextPoint.clone().sub(startPoint);
    localDirection.y = 0;
    if (localDirection.lengthSq() < 0.000001) {
      localDirection.set(0, 0, -1);
    } else {
      localDirection.normalize();
    }

    const yAxis = new THREE.Vector3(0, 1, 0);
    const sightDirection = sightPoint.clone().sub(startPoint);
    if (sightDirection.lengthSq() < 0.000001) {
      sightDirection.copy(localDirection);
    } else {
      sightDirection.normalize();
    }
    handles.navigationView = {
      anchor: startPoint.applyAxisAngle(yAxis, handles.alignmentRotation),
      direction: localDirection.clone().applyAxisAngle(yAxis, handles.alignmentRotation),
      sightDirection: sightDirection.applyAxisAngle(yAxis, handles.alignmentRotation),
    };
  } else {
    handles.navigationView = null;
  }
  // Fuera de la grilla real no hay altura conocida: no se dibuja el marcador.
  const scenePoint = userScenePoint;
  if (!scenePoint || navigationMode) return;
  const userPoint = toVector3(scenePoint);
  const markerGroup = new THREE.Group();
  markerGroup.name = "user-gps-marker";
  markerGroup.add(makeUserMarker(userPoint), makeVerticalPin(userPoint, "#2376D9"));
  handles.routeGroup.add(markerGroup);
  handles.trackedObject = markerGroup;
};

const buildSkyDome = (kind: TerrainWeatherKind | null, isNight: boolean) => {
  const colorsByKind = {
    clear: ["#5988AF", "#D7E3E8"],
    "partly-cloudy": ["#7997AE", "#DAE2E5"],
    cloudy: ["#89959D", "#CED4D5"],
    rain: ["#596B78", "#A9B5BA"],
    storm: ["#273743", "#73838B"],
    snow: ["#839BAA", "#E8F0F1"],
    fog: ["#A5ADB0", "#D1D6D5"],
  } as const;
  // Sin pronostico real se usa un degradado neutro.
  const [topColor, bottomColor] = isNight ? ["#101C2F", "#3A4858"] : kind ? colorsByKind[kind] : ["#8EA4B2", "#E4EBEE"];
  const geometry = new THREE.SphereGeometry(500, 24, 16);
  const material = new THREE.ShaderMaterial({
    uniforms: {
      topColor: { value: new THREE.Color(topColor) },
      bottomColor: { value: new THREE.Color(bottomColor) },
      offset: { value: 4 },
      exponent: { value: 0.68 },
    },
    vertexShader: `
      varying vec3 vWorldPosition;
      void main() {
        vec4 worldPosition = modelMatrix * vec4(position, 1.0);
        vWorldPosition = worldPosition.xyz;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 topColor;
      uniform vec3 bottomColor;
      uniform float offset;
      uniform float exponent;
      varying vec3 vWorldPosition;
      void main() {
        float h = normalize(vWorldPosition + vec3(0.0, offset, 0.0)).y;
        gl_FragColor = vec4(mix(bottomColor, topColor, max(pow(max(h, 0.0), exponent), 0.0)), 1.0);
      }
    `,
    side: THREE.BackSide,
    fog: false,
  });

  return new THREE.Mesh(geometry, material);
};

// Efectos solo para un pronostico real. Las posiciones siguen una grilla fija
// y se elevan sobre el punto mas alto del relieve.
const addWeatherGraphics = (
  group: THREE.Group,
  kind: TerrainWeatherKind | null,
  baseHeight: number,
  weather: TerrainSceneWeather | null | undefined
) => {
  if (!kind) return;
  const cloudKinds = ["partly-cloudy", "cloudy", "rain", "storm", "snow"];

  if (cloudKinds.includes(kind)) {
    const cloudCount = weather?.cloudCoverPercent != null
      ? Math.round(clamp(weather.cloudCoverPercent / 12, 1, 9)) : kind === "partly-cloudy" ? 3 : kind === "cloudy" ? 6 : 8;
    const cloudMaterial = new THREE.SpriteMaterial({
      map: makeCloudTexture(),
      color: weather?.isDay === false ? "#637284" : kind === "storm" ? "#75818B" : kind === "rain" ? "#A0ABB1" : "#F1F3F1",
      transparent: true,
      opacity: 0.72,
      depthWrite: false,
      fog: true,
    });
    for (let index = 0; index < cloudCount; index += 1) {
      const cloud = new THREE.Sprite(cloudMaterial);
      const x = -5.8 + (index % 4) * 3.8;
      const y = 4.6 + Math.floor(index / 4) * 1.15 + baseHeight;
      const z = -5.5 + (index % 2) * 1.1;
      cloud.scale.set(5.5, 2.5, 1);
      cloud.position.set(x, y, z);
      cloud.name = "weather-cloud";
      cloud.userData.originX = x;
      cloud.userData.originZ = z;
      group.add(cloud);
    }
  }

  if (["rain", "storm", "snow"].includes(kind)) {
    const precipitationCount = kind === "storm" ? 150 : 95;
    const isSnow = kind === "snow";
    const geometry = isSnow
      ? new THREE.SphereGeometry(0.008, 5, 4)
      : new THREE.CylinderGeometry(0.003, 0.003, 0.08, 4);
    const material = new THREE.MeshBasicMaterial({
      color: isSnow ? "#FFFFFF" : "#9DD4E9",
      transparent: true,
      opacity: 0.76,
      fog: false,
    });
    const precipitation = new THREE.InstancedMesh(geometry, material, precipitationCount);
    const dummy = new THREE.Object3D();
    for (let index = 0; index < precipitationCount; index += 1) {
      const row = Math.floor(index / 15);
      dummy.position.set(
        -6 + (index % 15) * 0.8 + (row % 2) * 0.4,
        1.2 + ((index * 7) % 25) * 0.2 + baseHeight,
        -4 + ((row * 3) % 10) * 0.8
      );
      dummy.rotation.z = isSnow ? 0 : -0.18;
      dummy.updateMatrix();
      precipitation.setMatrixAt(index, dummy.matrix);
    }
    precipitation.instanceMatrix.needsUpdate = true;
    precipitation.name = "weather-precipitation";
    precipitation.userData.baseHeight = baseHeight;
    precipitation.frustumCulled = false;
    group.add(precipitation);
  }
};

export const Terrain3DScene = forwardRef<Terrain3DSceneHandle, Terrain3DSceneProps>(function Terrain3DScene({
  terrain,
  userCoordinate,
  viewOffset,
  viewScale,
  weather,
  navigationMode = false,
  satelliteTextureEnabled = true,
  markers = EMPTY_MARKERS,
  highlightedSections = EMPTY_SECTIONS,
  focusCoordinate = null,
  showContours = false,
  overlayTopInset = 150,
  overlayBottomInset = 28,
  onError,
}, ref) {
  const handlesRef = useRef<SceneHandles | null>(null);
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const viewportRef = useRef(viewport);
  viewportRef.current = viewport;
  const [readout, setReadout] = useState<SceneReadout | null>(null);
  const [hasSatelliteImage, setHasSatelliteImage] = useState(false);
  const lastReadoutRef = useRef(0);
  const readoutSignatureRef = useRef("");
  const stations = useMemo(() => getTerrainRouteStations(terrain), [terrain]);
  const stationsRef = useRef(stations);
  stationsRef.current = stations;
  const overlayTopRef = useRef(overlayTopInset);
  overlayTopRef.current = overlayTopInset;
  const renderedFrameRef = useRef(false);
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;
  const disposeScene = useCallback(() => {
    const handles = handlesRef.current;
    handlesRef.current = null;
    if (!handles) return;
    cancelAnimationFrame(handles.animationFrame);
    // Cleanup must not prevent returning to the 2D map after a lost context.
    try {
      handles.imagery?.dispose();
      clearGroup(handles.terrainGroup);
      clearGroup(handles.routeGroup);
      clearGroup(handles.weatherGroup);
      clearGroup(handles.markerGroup);
      handles.scene.traverse((object) => {
        if (object instanceof THREE.Light) object.shadow?.dispose();
      });
      handles.renderer.dispose();
    } catch { /* Context may already be destroyed by the native view. */ }
  }, []);
  const failScene = useCallback((error: unknown) => {
    disposeScene();
    onErrorRef.current?.(error);
  }, [disposeScene]);
  useEffect(() => {
    // Some native GL failures never call onContextCreate. Keep 2D available.
    const timer = setTimeout(() => {
      if (!renderedFrameRef.current) failScene(new Error("El contexto 3D no respondió."));
    }, 12000);
    return () => clearTimeout(timer);
  }, [failScene]);
  const markersRef = useRef(markers);
  markersRef.current = markers;
  const sectionsRef = useRef(highlightedSections);
  sectionsRef.current = highlightedSections;
  const updateMarkers = useCallback(() => {
    const handles = handlesRef.current;
    if (!handles?.model) return;
    clearGroup(handles.markerGroup);
    handles.markerGroup.rotation.y = handles.alignmentRotation;
    markersRef.current.forEach(marker => {
      const object = makeMapMarker(handles.model!, marker);
      if (object) handles.markerGroup.add(object);
      const groundKind = getReportedGroundKind(marker.issueSummary ?? "");
      const point = coordinateToTerrainScenePoint(handles.model!, marker.coordinate);
      if (!groundKind || !point) return;
      const radius = Math.max(marker.precisionMeters, 60) / handles.model!.metersPerUnit;
      let section: THREE.Vector3[] = [];
      const flush = () => {
        if (section.length > 1) {
          const ribbon = makeTerrainTrailRibbon(section, handles.model!, 0.028, groundKind.color, 0.022, true);
          ribbon.name = "reported-ground-section";
          ribbon.userData.isGroundSection = true;
          handles.markerGroup.add(ribbon);
        }
        section = [];
      };
      handles.terrainRoute.forEach(routePoint => {
        if (Math.hypot(routePoint.x - point.x, routePoint.z - point.z) <= radius) section.push(routePoint);
        else flush();
      });
      flush();
    });
    sectionsRef.current.forEach(section => {
      const model = buildTerrainSceneModel(handles.model!.grid, section.coordinates);
      if (!model) return;
      const ribbon = makeTerrainTrailRibbon(drapeRouteOnTerrain(model).map(toVector3), model, 0.055, section.color, 0.027, true);
      ribbon.name = `report-section-${section.id}`;
      ribbon.userData.isGroundSection = true;
      handles.markerGroup.add(ribbon);
    });
  }, []);
  useEffect(() => { updateMarkers(); }, [markers, highlightedSections, updateMarkers]);
  useImperativeHandle(ref, () => ({
    pick: (x, y) => {
      const handles = handlesRef.current;
      if (!handles?.model || !handles.groundMesh) return null;
      handles.scene.updateMatrixWorld(true);
      handles.camera.updateMatrixWorld(true);
      const ray = new THREE.Raycaster();
      ray.setFromCamera(new THREE.Vector2(x, y), handles.camera);
      const ground = ray.intersectObject(handles.groundMesh, false)[0];
      const hit = ray.intersectObject(handles.markerGroup, true).find(intersection => {
        // Precision rings describe an area; only the pin itself opens a report.
        return !intersection.object.userData.isGroundSection && !(intersection.object as THREE.Mesh).geometry?.type?.includes("Ring") &&
          (!ground || intersection.distance <= ground.distance + 0.03);
      });
      if (hit) {
        let object: THREE.Object3D | null = hit.object;
        while (object && !object.userData.markerId) object = object.parent;
        if (object) return { coordinate: terrainScenePointToCoordinate(handles.model, object.position), markerId: object.userData.markerId };
      }
      if (!ground) return null;
      return { coordinate: terrainScenePointToCoordinate(handles.model, handles.terrainGroup.worldToLocal(ground.point.clone())) };
    },
  }), []);
  const propsRef = useRef({
    terrain,
    userCoordinate,
    viewOffset,
    viewScale,
    weather,
    navigationMode,
    satelliteTextureEnabled,
    focusCoordinate,
    showContours,
  });
  const geometrySignature = useMemo(
    () =>
      JSON.stringify({
        weather,
        navigationMode,
        satelliteTextureEnabled,
        showContours,
      }),
    [
      weather,
      navigationMode,
      satelliteTextureEnabled,
      showContours,
    ]
  );

  useEffect(() => {
    propsRef.current = {
      terrain,
      userCoordinate,
      viewOffset,
      viewScale,
      weather,
      navigationMode,
      satelliteTextureEnabled,
      focusCoordinate,
      showContours,
    };
  }, [
    terrain,
    userCoordinate,
    viewOffset,
    viewScale,
    weather,
    navigationMode,
    satelliteTextureEnabled,
    focusCoordinate,
    showContours,
  ]);

  const rebuildScene = useCallback(() => {
    const handles = handlesRef.current;
    if (!handles) return;

    const current = propsRef.current;
    const model = current.terrain;
    handles.imagery?.dispose();
    handles.imagery = null;
    clearGroup(handles.terrainGroup);
    clearGroup(handles.routeGroup);
    clearGroup(handles.weatherGroup);
    handles.trackedObject = null;
    const weatherKind = getTerrainWeatherKind(current.weather);
    const isNight = current.weather?.isDay === false;
    const isDarkWeather = weatherKind === "storm" || weatherKind === "rain";
    const fogColor = isNight ? "#283747" : weatherKind === "fog" ? "#CBD0D0" : weatherKind === "storm"
      ? "#66747B"
      : weatherKind === "rain"
        ? "#899CA5"
        : weatherKind === "snow"
          ? "#DDE7E9"
          : "#CFE4E8";
    const visibilityMeters = weatherKind === "fog" ? 2000 : isDarkWeather ? 8000 : weatherKind === "snow" ? 6000 : 50000;
    handles.scene.fog = new THREE.FogExp2(fogColor, model.metersPerUnit / visibilityMeters);
    handles.renderer.setClearColor(fogColor);
    handles.sunLight.intensity = isNight ? 0.18 : weatherKind === "clear" ? 2.4 : isDarkWeather || weatherKind === "fog" ? 0.65 : 1.5;
    handles.hemiLight.intensity = isNight ? 0.45 : isDarkWeather ? 1.05 : 1.35;
    handles.sunLight.position.set(-8, model.maxHeight + 12, 6);
    handles.sunLight.shadow.camera.far = 40 + model.maxHeight * 2;
    handles.sunLight.shadow.camera.updateProjectionMatrix();
    handles.weatherGroup.add(buildSkyDome(weatherKind, isNight));
    addWeatherGraphics(handles.weatherGroup, weatherKind, model.maxHeight, current.weather);
    const terrain = buildTerrainMesh(model);
    setHasSatelliteImage(false);
    handles.groundMesh = terrain;
    handles.terrainGroup.add(terrain);
    if (current.satelliteTextureEnabled) {
      handles.imagery = createTerrainImagery(
        terrain.material,
        model,
        handles.renderer.capabilities?.getMaxAnisotropy?.() ?? 1,
        current.navigationMode,
        () => setHasSatelliteImage(true)
      );
    }
    handles.terrainGroup.add(buildTerrainSkirt(model));
    if (current.showContours) handles.terrainGroup.add(buildTerrainContours(model));
    handles.alignmentRotation = 0;
    handles.navigationView = null;
    handles.terrainGroup.rotation.y = 0;
    handles.routeGroup.rotation.y = 0;

    if (model.route.length > 1) {
      const first = model.route[0];
      const last = model.route[model.route.length - 1];
      handles.alignmentRotation = Math.atan2(last.z - first.z, last.x - first.x);
      handles.terrainGroup.rotation.y = handles.alignmentRotation;
      handles.routeGroup.rotation.y = handles.alignmentRotation;
    }
    handles.weatherGroup.rotation.y = handles.alignmentRotation;

    const terrainRoute = drapeRouteOnTerrain(model).map(toVector3);
    handles.model = model;
    handles.terrainRoute = terrainRoute;
    const markerRoute = terrainRoute.map((point) => {
      const next = point.clone();
      next.y += 0.025;
      return next;
    });

    if (terrainRoute.length > 1) {
      const trailOuterHalfWidth = current.navigationMode ? 0.026 : 0.045;
      const trailInnerHalfWidth = current.navigationMode ? 0.014 : 0.025;
      handles.routeGroup.add(
        makeTerrainTrailRibbon(
          terrainRoute,
          model,
          trailOuterHalfWidth,
          "#F0643B",
          0.012,
          true
        )
      );
      handles.routeGroup.add(
        makeTerrainTrailRibbon(
          terrainRoute,
          model,
          trailInnerHalfWidth,
          "#E6BC89",
          0.018,
          false
        )
      );
      handles.routeGroup.add(buildTerrainRouteArrows(model, terrainRoute));
    }

    const endpointScale = current.navigationMode ? 0.74 : 1;
    if (markerRoute[0]) {
      handles.routeGroup.add(makeEndpointMarker(markerRoute[0], "start", endpointScale));
    }

    if (markerRoute.length > 1) {
      handles.routeGroup.add(
        makeEndpointMarker(markerRoute[markerRoute.length - 1], "finish", endpointScale)
      );
    }

    updateTrackedPosition(
      handles,
      current.userCoordinate,
      current.navigationMode
    );
    updateMarkers();
  }, [updateMarkers]);

  useEffect(() => {
    try { rebuildScene(); } catch (error) { failScene(error); }
  }, [terrain, geometrySignature, rebuildScene, failScene]);

  useEffect(() => {
    const handles = handlesRef.current;
    if (!handles) return;
    try { updateTrackedPosition(handles, userCoordinate, navigationMode); }
    catch (error) { failScene(error); }
  }, [userCoordinate, navigationMode, failScene]);

  useEffect(() => disposeScene, [disposeScene]);

  const updateCamera = useCallback((
    camera: THREE.PerspectiveCamera,
    navigationView?: NavigationView | null,
    alignmentRotation = 0
  ) => {
    const current = propsRef.current;
    const scale = clampTerrainScale(current.viewScale);
    const orbitAngle = current.viewOffset.x / 100;
    const tilt = clamp(current.viewOffset.y / 120, -1.65, 1.65);
    const focusPoint = current.focusCoordinate ? coordinateToTerrainScenePoint(current.terrain, current.focusCoordinate) : null;

    if (current.navigationMode && navigationView && !focusPoint) {
      const model = current.terrain;
      const yAxis = new THREE.Vector3(0, 1, 0);
      const viewDirection = navigationView.direction.clone().applyAxisAngle(yAxis, orbitAngle);
      const sightDirection = navigationView.sightDirection
        .clone()
        .applyAxisAngle(yAxis, orbitAngle);
      const cameraPosition = navigationView.anchor
        .clone()
        .addScaledVector(viewDirection, -NAVIGATION_CAMERA_SETBACK_METERS / model.metersPerUnit);
      const localCamera = cameraPosition.clone().applyAxisAngle(yAxis, -alignmentRotation);
      const groundY = getTerrainSceneHeight(model, localCamera.x, localCamera.z);
      cameraPosition.y = groundY + NAVIGATION_EYE_HEIGHT_METERS / model.metersPerUnit;

      // Mantiene suelo visible en el centro incluso al mirar cuesta arriba.
      const trailPitch = Math.min(0.17, Math.asin(clamp(sightDirection.y, -1, 1)));
      const pitch = clamp(trailPitch - 0.30 - tilt * 0.24, -1.48, 0.23);
      const lookDirection = sightDirection.setY(0).normalize().multiplyScalar(Math.cos(pitch));
      lookDirection.y = Math.sin(pitch);
      const lookTarget = cameraPosition
        .clone()
        .add(lookDirection);
      camera.fov = getTerrainPerspectiveFov(scale);
      camera.near = Math.max(0.0005, 0.5 / current.terrain.metersPerUnit);
      camera.zoom = 1;
      camera.position.copy(cameraPosition);
      camera.lookAt(lookTarget);
      camera.updateProjectionMatrix();
      return;
    }

    // El relieve real puede ser mas alto que la vista por defecto: se eleva el
    // objetivo con el relieve y la camara nunca queda debajo del terreno.
    const model = current.terrain;
    const targetY = focusPoint ? focusPoint.y + DEFAULT_CAMERA_TARGET_Y : Math.max(DEFAULT_CAMERA_TARGET_Y, model.maxHeight * 0.4);
    const target = focusPoint
      ? new THREE.Vector3(focusPoint.x, targetY, focusPoint.z).applyAxisAngle(new THREE.Vector3(0, 1, 0), alignmentRotation)
      : new THREE.Vector3(0, targetY, 0);
    const limitingHalfAngle = Math.min(43 * Math.PI / 360, Math.atan(Math.tan(43 * Math.PI / 360) * camera.aspect));
    let routeRadius = 0;
    model.route.forEach(point => { routeRadius = Math.max(routeRadius, Math.hypot(point.x, point.y - targetY, point.z)); });
    const distance = focusPoint ? 8 : Math.max(8, routeRadius / Math.sin(limitingHalfAngle) * 1.12);
    const pitch = clamp(0.55 - tilt * 0.2, 0.22, 1.05);
    const radius = distance * Math.cos(pitch);
    const height = targetY + distance * Math.sin(pitch);
    const cameraX = target.x + Math.sin(orbitAngle) * radius;
    const cameraZ = target.z + Math.cos(orbitAngle) * radius;
    const groundY = getTerrainSceneHeight(
      model,
      cameraX * Math.cos(alignmentRotation) - cameraZ * Math.sin(alignmentRotation),
      cameraX * Math.sin(alignmentRotation) + cameraZ * Math.cos(alignmentRotation)
    );

    camera.fov = 43;
    camera.near = 0.03;
    camera.zoom = scale;
    camera.position.set(
      cameraX,
      Math.max(height, groundY + CAMERA_GROUND_CLEARANCE),
      cameraZ
    );
    camera.lookAt(target);
    camera.updateProjectionMatrix();
  }, []);

  const onContextCreate = useCallback(
    (gl: ExpoWebGLRenderingContext) => {
      disposeScene();
      let renderer: THREE.WebGLRenderer | undefined;
      try {
        const width = gl.drawingBufferWidth || 1;
        const height = gl.drawingBufferHeight || 1;
        renderer = createTerrainRenderer(gl);
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.08;
        renderer.outputColorSpace = THREE.SRGBColorSpace;

        const scene = new THREE.Scene();
        scene.fog = new THREE.FogExp2("#CFE9F2", 0.035);

        const camera = new THREE.PerspectiveCamera(43, width / height, 0.03, 1500);
        updateCamera(camera, null);

        const terrainGroup = new THREE.Group();
        const routeGroup = new THREE.Group();
        const weatherGroup = new THREE.Group();
        const markerGroup = new THREE.Group();
        scene.add(weatherGroup);
        scene.add(terrainGroup);
        scene.add(routeGroup);
        scene.add(markerGroup);

        const hemiLight = new THREE.HemisphereLight("#DDF6FF", "#335C36", 1.5);
        const sunLight = new THREE.DirectionalLight("#FFF3D9", 2.7);
        const fillLight = new THREE.DirectionalLight("#A9CBE8", 0.6);
        sunLight.position.set(-6, 6.5, 4.5);
        sunLight.castShadow = true;
        sunLight.shadow.mapSize.set(2048, 2048);
        sunLight.shadow.camera.left = -11;
        sunLight.shadow.camera.right = 11;
        sunLight.shadow.camera.top = 11;
        sunLight.shadow.camera.bottom = -11;
        sunLight.shadow.camera.near = 1;
        sunLight.shadow.camera.far = 40;
        sunLight.shadow.normalBias = 0.025;
        sunLight.shadow.bias = -0.0003;
        sunLight.shadow.radius = 1.5;
        fillLight.position.set(5, 4, -4);
        scene.add(hemiLight);
        scene.add(sunLight);
        scene.add(fillLight);

        handlesRef.current = {
          alignmentRotation: 0,
          animationFrame: 0,
          camera,
          gl,
          renderer,
          routeGroup,
          scene,
          terrainGroup,
          weatherGroup,
          sunLight,
          hemiLight,
          navigationView: null,
          model: null,
          terrainRoute: [],
          trackedObject: null,
          imagery: null,
          markerGroup,
          groundMesh: null,
        };
        rebuildScene();
        const precipitationDummy = new THREE.Object3D();
        const animationStart = Date.now();

        const render = () => {
          const handles = handlesRef.current;
          if (!handles) return;
          try {
            if (handles.gl.isContextLost?.()) throw new Error("Se perdió el contexto GL.");
            updateCamera(handles.camera, handles.navigationView, handles.alignmentRotation);
            handles.markerGroup.children.forEach(marker => {
              const head = marker.getObjectByName("map-marker-head");
              if (head) {
                head.quaternion.copy(handles.markerGroup.quaternion).invert().multiply(handles.camera.quaternion);
              }
            });
            const elapsed = (Date.now() - animationStart) / 1000;
            const weather = propsRef.current.weather;
            const windSpeed = Math.max(0, weather?.windKmh ?? 0) / 3.6 / (handles.model?.metersPerUnit ?? 1);
            const direction = (weather?.windDirectionDegrees ?? 0) * Math.PI / 180;
            const windX = weather?.windDirectionDegrees == null ? 0 : -Math.sin(direction) * windSpeed;
            const windZ = weather?.windDirectionDegrees == null ? 0 : Math.cos(direction) * windSpeed;
            const wrap = (value: number, length: number) => ((value % length) + length) % length;
            handles.weatherGroup.children.forEach((child) => {
              if (child.name === "weather-cloud") {
                const originX = Number(child.userData.originX) || 0;
                const originZ = Number(child.userData.originZ) || 0;
                child.position.x = wrap(originX + elapsed * windX + 8, 16) - 8;
                child.position.z = wrap(originZ + elapsed * windZ + 8, 16) - 8;
              } else if (child.name === "weather-precipitation" && handles.model) {
                const particles = child as THREE.InstancedMesh;
                const isSnow = getTerrainWeatherKind(weather) === "snow";
                const fallSpeed = (isSnow ? 1.2 : 7) / handles.model.metersPerUnit;
                const range = Math.max(2, handles.model.maxHeight + 3);
                for (let index = 0; index < particles.count; index += 1) {
                  const x = wrap(index * 0.6180339887 * 14 + elapsed * windX, 14) - 7;
                  const z = wrap(index * 0.754877666 * 14 + elapsed * windZ, 14) - 7;
                  const ground = getTerrainSceneHeight(handles.model, x, z);
                  precipitationDummy.position.set(x, ground + 0.1 + wrap(index * 0.56984029 * range - elapsed * fallSpeed, range), z);
                  precipitationDummy.rotation.set(isSnow ? 0 : Math.atan2(windZ, fallSpeed), 0, isSnow ? 0 : -Math.atan2(windX, fallSpeed));
                  precipitationDummy.updateMatrix();
                  particles.setMatrixAt(index, precipitationDummy.matrix);
                }
                particles.instanceMatrix.needsUpdate = true;
              }
            });
            handles.renderer.render(handles.scene, handles.camera);
            handles.gl.endFrameEXP?.();
            const viewport = viewportRef.current;
            if (viewport.width > 0 && handles.groundMesh && Date.now() - lastReadoutRef.current > 180) {
              lastReadoutRef.current = Date.now();
              const scale = getTerrainViewReadout(handles.camera, handles.groundMesh, propsRef.current.terrain.metersPerUnit, handles.alignmentRotation);
              if (scale) {
                handles.scene.updateMatrixWorld(true);
                const labels: SceneReadout["labels"] = [];
                if (!propsRef.current.navigationMode) stationsRef.current.forEach(station => {
                  const world = toVector3(station.point).applyMatrix4(handles.routeGroup.matrixWorld);
                  const point = world.clone().project(handles.camera);
                  const x = (point.x + 1) * viewport.width / 2;
                  const y = (1 - point.y) * viewport.height / 2;
                  if (point.z < -1 || point.z > 1 || x < 36 || x > viewport.width - 65 || y < overlayTopRef.current || y > viewport.height - 120) return;
                  if (labels.some(label => Math.hypot(label.x - x, label.y - y) < 72)) return;
                  const direction = world.clone().sub(handles.camera.position);
                  const distance = direction.length();
                  const obstacle = new THREE.Raycaster(handles.camera.position, direction.normalize()).intersectObject(handles.groundMesh!, false)[0];
                  if (obstacle && obstacle.distance < distance - 0.08) return;
                  labels.push({ x: Math.round(x), y: Math.round(y), text: `${station.label} · ${station.elevationMeters} m` });
                });
                const next = { ...scale, scaleFraction: Math.round(scale.scaleFraction * 1000) / 1000, northDegrees: Math.round(scale.northDegrees), labels };
                const signature = JSON.stringify(next);
                if (signature !== readoutSignatureRef.current) { readoutSignatureRef.current = signature; setReadout(next); }
              } else if (readoutSignatureRef.current) {
                readoutSignatureRef.current = "";
                setReadout(null);
              }
            }
            renderedFrameRef.current = true;
            handles.animationFrame = requestAnimationFrame(render);
          } catch (error) { failScene(error); }
        };

        render();
      } catch (error) {
        if (!handlesRef.current) {
          try { renderer?.dispose(); } catch { /* Context lost during creation. */ }
        }
        failScene(error);
      }
    },
    [rebuildScene, updateCamera, disposeScene, failScene]
  );

  const groundLabels = [...new Set(markers.map(marker => getReportedGroundKind(marker.issueSummary ?? "")?.label).filter(Boolean))];
  return <View style={styles.canvas} testID="terrain-scene-viewport" onLayout={event => setViewport(event.nativeEvent.layout)}>
    <GLView style={styles.canvas} onContextCreate={onContextCreate} />
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      {readout?.labels.map(label => <View key={label.text} style={[styles.routeLabel, { left: label.x - 30, top: label.y - 28 }]}>
        <Text style={styles.routeLabelText}>{label.text}</Text>
      </View>)}
      <View style={[styles.readout, { bottom: overlayBottomInset }]}>
        <View style={styles.readoutRow}>
          {readout ? <View>
            <Text style={styles.readoutText}>{readout.scaleMeters >= 1000 ? `${readout.scaleMeters / 1000} km` : `${readout.scaleMeters} m`} · en el centro</Text>
            <View style={[styles.scaleBar, { width: Math.max(1, viewport.width * readout.scaleFraction) }]} />
          </View> : <Text style={styles.readoutText}>Relieve a escala real</Text>}
          {readout && <View style={styles.readoutRow}><View style={{ transform: [{ rotate: `${readout.northDegrees}deg` }] }}><Text style={styles.northArrow}>↑</Text></View><Text style={styles.northArrow}> N</Text></View>}
        </View>
        <Text style={styles.readoutText}>Altura ×1 · {Math.round(terrain.minElevationMeters)}–{Math.round(terrain.maxElevationMeters)} m s. n. m.</Text>
        {!navigationMode && <Text style={styles.readoutSubtle}>{hasSatelliteImage ? "Imagen satelital de referencia" : "Color por altitud"} · detalle ≈ {Math.round(Math.max(90, terrain.grid.cellSizeMeters))} m{showContours ? ` · curvas ${getTerrainContourInterval(terrain)} m` : ""}</Text>}
        <Text numberOfLines={navigationMode ? 1 : 2} style={styles.readoutText}>{weather ? `Pronóstico: ${weather.condition} · ${weather.temperatureC} °C${weather.windKmh != null ? ` · viento ${weather.windKmh} km/h` : ""}${weather.observedAt ? ` · ${new Date(weather.observedAt).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })}` : ""}` : "Clima sin datos"}</Text>
        <Text numberOfLines={navigationMode ? 1 : 2} style={styles.readoutSubtle}>{groundLabels.length ? `Suelo reportado: ${groundLabels.join(" · ")} · ubicación aproximada` : "Suelo: sin reportes recientes"}</Text>
      </View>
    </View>
  </View>;
});

const styles = StyleSheet.create({
  canvas: {
    flex: 1,
  },
  readout: { position: "absolute", bottom: 28, left: 12, right: 12, backgroundColor: "rgba(255,255,255,0.91)", borderRadius: 14, padding: 10, gap: 4 },
  readoutRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  readoutText: { color: "#23372D", fontSize: 11, fontWeight: "700" },
  readoutSubtle: { color: "#46554C", fontSize: 10, lineHeight: 14 },
  scaleBar: { height: 6, borderBottomWidth: 2, borderLeftWidth: 2, borderRightWidth: 2, borderColor: "#23372D", marginTop: 2 },
  northArrow: { color: "#23372D", fontWeight: "900", fontSize: 15 },
  routeLabel: { position: "absolute", paddingHorizontal: 6, paddingVertical: 3, borderRadius: 6, backgroundColor: "rgba(255,255,255,0.9)" },
  routeLabelText: { color: "#23372D", fontWeight: "800", fontSize: 10 },
});
