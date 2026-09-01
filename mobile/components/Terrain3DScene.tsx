import { GLView, ExpoWebGLRenderingContext } from "expo-gl";
import { Renderer, TextureLoader } from "expo-three";
import React, { useCallback, useEffect, useMemo, useRef } from "react";
import { StyleSheet } from "react-native";
import * as THREE from "three";
import { Coordinate } from "../../services/geoUtils";
import {
  clampTerrainScale,
  getTerrainPerspectiveFov,
} from "../../services/mapGestures";

type Terrain3DSceneProps = {
  routePoints: Coordinate[];
  fallbackCenter: Coordinate;
  difficulty?: string | null;
  distanceKm?: number | null;
  userCoordinate?: Coordinate | null;
  viewOffset: { x: number; y: number };
  viewScale: number;
  trailLabel?: string | null;
  weather?: {
    condition: string;
    rainProbability: number;
    temperatureC: number;
  } | null;
  navigationMode?: boolean;
  satelliteTextureEnabled?: boolean;
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
  renderer: Renderer;
  routeGroup: THREE.Group;
  scene: THREE.Scene;
  terrainGroup: THREE.Group;
  alignmentRotation: number;
  weatherGroup: THREE.Group;
  sunLight: THREE.DirectionalLight;
  hemiLight: THREE.HemisphereLight;
  navigationView: NavigationView | null;
  model: TerrainModel | null;
  terrainRoute: THREE.Vector3[];
  trackedObject: THREE.Object3D | null;
  rebuildId: number;
};

type TerrainBiome = "forest" | "steppe" | "alpine";

type TerrainModel = {
  bounds: {
    centerX: number;
    centerZ: number;
    metersPerUnit: number;
    minX: number;
    minZ: number;
    sizeMeters: number;
  };
  difficultyFactor: number;
  origin: Coordinate;
  route: THREE.Vector3[];
  seed: number;
  biome: TerrainBiome;
};

const GRID_SIZE = 104;
const TERRAIN_HALF_SIZE = 7.2;
const RELIEF_EXAGGERATION = 1.32;
const EARTH_RADIUS_METERS = 6371000;
const ROUTE_LIFT = 0.12;
const ROUTE_SHADOW_RADIUS = 0.115;
const ROUTE_SURFACE_RADIUS = 0.082;
const ROUTE_CORE_RADIUS = 0.049;
const ROUTE_CORE_COLOR = "#E85B35";
const ROUTE_SURFACE_COLOR = "#FFF6EA";
const ROUTE_SHADOW_COLOR = "#3A211A";

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));

const getDifficultyFactor = (difficulty: string | null | undefined) => {
  const normalized = (difficulty || "").toLowerCase();

  if (normalized.includes("dificil") || normalized.includes("alta")) return 1;
  if (normalized.includes("media") || normalized.includes("moderada")) return 0.68;
  return 0.42;
};

const getRouteDistanceKm = (points: Coordinate[]) => {
  if (points.length < 2) return 0;

  const toRad = (value: number) => (value * Math.PI) / 180;

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

    return total + (EARTH_RADIUS_METERS / 1000) * c;
  }, 0);
};

export const getTerrainElevationGainMeters = (
  routePoints: Coordinate[],
  difficulty?: string | null,
  distanceKm?: number | null
) => {
  const resolvedDistanceKm =
    distanceKm || getRouteDistanceKm(routePoints.length > 1 ? routePoints : []);
  const difficultyFactor = getDifficultyFactor(difficulty);

  return Math.round(
    Math.max(60, resolvedDistanceKm * (80 + difficultyFactor * 95))
  );
};

const getOrigin = (points: Coordinate[], fallbackCenter: Coordinate): Coordinate => {
  if (points.length === 0) return fallbackCenter;

  const totals = points.reduce(
    (acc, point) => ({
      latitude: acc.latitude + point[0],
      longitude: acc.longitude + point[1],
    }),
    { latitude: 0, longitude: 0 }
  );

  return [totals.latitude / points.length, totals.longitude / points.length];
};

const toLocalMeters = (point: Coordinate, origin: Coordinate) => {
  const latRad = (origin[0] * Math.PI) / 180;

  return {
    x:
      ((point[1] - origin[1]) *
        Math.PI *
        EARTH_RADIUS_METERS *
        Math.cos(latRad)) /
      180,
    z: -(((point[0] - origin[0]) * Math.PI * EARTH_RADIUS_METERS) / 180),
  };
};

const buildTerrainModel = (
  routePoints: Coordinate[],
  fallbackCenter: Coordinate,
  difficulty?: string | null,
  trailLabel?: string | null
): TerrainModel => {
  const sourcePoints =
    routePoints.length > 1
      ? routePoints
      : [
          [fallbackCenter[0] - 0.004, fallbackCenter[1] - 0.004] as Coordinate,
          fallbackCenter,
          [fallbackCenter[0] + 0.004, fallbackCenter[1] + 0.004] as Coordinate,
        ];
  const origin = getOrigin(sourcePoints, fallbackCenter);
  const localPoints = sourcePoints.map((point) => toLocalMeters(point, origin));
  const minRouteX = Math.min(...localPoints.map((point) => point.x));
  const maxRouteX = Math.max(...localPoints.map((point) => point.x));
  const minRouteZ = Math.min(...localPoints.map((point) => point.z));
  const maxRouteZ = Math.max(...localPoints.map((point) => point.z));
  const routeWidth = Math.max(1, maxRouteX - minRouteX);
  const routeDepth = Math.max(1, maxRouteZ - minRouteZ);
  const sizeMeters = Math.max(routeWidth, routeDepth, 900) * 1.9;
  const metersPerUnit = sizeMeters / 8.4;
  const centerX = (minRouteX + maxRouteX) / 2;
  const centerZ = (minRouteZ + maxRouteZ) / 2;
  const minX = centerX - sizeMeters / 2;
  const minZ = centerZ - sizeMeters / 2;
  const difficultyFactor = getDifficultyFactor(difficulty);
  const normalizedLabel = (trailLabel || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  const isForest =
    normalizedLabel.includes("bosque") ||
    normalizedLabel.includes("selva") ||
    normalizedLabel.includes("yunga") ||
    normalizedLabel.includes("arrayan") ||
    normalizedLabel.includes("coihue");
  const isSteppe =
    !isForest && (
      normalizedLabel.includes("estepa") ||
      normalizedLabel.includes("desierto") ||
      normalizedLabel.includes("puna") ||
      normalizedLabel.includes("pomez") ||
      normalizedLabel.includes("quebrada") ||
      normalizedLabel.includes("catamarca") ||
      normalizedLabel.includes("jujuy") ||
      normalizedLabel.includes("salta")
    );
  const isAlpine =
    normalizedLabel.includes("cerro") ||
    normalizedLabel.includes("cumbre") ||
    normalizedLabel.includes("mont") ||
    normalizedLabel.includes("glaciar") ||
    normalizedLabel.includes("laguna") ||
    difficultyFactor > 0.82;
  const biome: TerrainBiome = isSteppe ? "steppe" : isAlpine && !isForest ? "alpine" : "forest";
  const seed =
    Math.sin(origin[0] * 13.37 + origin[1] * 7.91 + difficultyFactor * 5.3) *
    9.7;
  const route = localPoints.map((point) => {
    const x = (point.x - centerX) / metersPerUnit;
    const z = (point.z - centerZ) / metersPerUnit;

    return new THREE.Vector3(x, getHeightAt(x, z, difficultyFactor, seed), z);
  });

  return {
    bounds: { centerX, centerZ, metersPerUnit, minX, minZ, sizeMeters },
    difficultyFactor,
    origin,
    route,
    seed,
    biome,
  };
};

const hash01 = (x: number, y: number, seed: number) => {
  const s = Math.sin(x * 127.1 + y * 311.7 + seed * 74.7) * 43758.5453123;
  return s - Math.floor(s);
};

const smoothstep = (t: number) => t * t * (3 - 2 * t);

const valueNoise2D = (x: number, y: number, seed: number) => {
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const sx = smoothstep(x - x0);
  const sy = smoothstep(y - y0);
  const n00 = hash01(x0, y0, seed);
  const n10 = hash01(x0 + 1, y0, seed);
  const n01 = hash01(x0, y0 + 1, seed);
  const n11 = hash01(x0 + 1, y0 + 1, seed);
  const nx0 = n00 + (n10 - n00) * sx;
  const nx1 = n01 + (n11 - n01) * sx;

  return (nx0 + (nx1 - nx0) * sy) * 2 - 1;
};

const fbm2D = (x: number, y: number, seed: number, octaves: number) => {
  let amplitude = 1;
  let frequency = 1;
  let sum = 0;
  let max = 0;

  for (let octave = 0; octave < octaves; octave += 1) {
    sum += valueNoise2D(x * frequency, y * frequency, seed + octave * 17.13) * amplitude;
    max += amplitude;
    amplitude *= 0.52;
    frequency *= 2.03;
  }

  return sum / max;
};

const getHeightAt = (
  x: number,
  z: number,
  difficultyFactor: number,
  seed: number
) => {
  const longRidge = Math.sin(x * 0.9 + seed) * 0.34;
  const crossRidge = Math.cos(z * 1.12 - seed * 0.7) * 0.26;
  const peakA =
    Math.exp(-((x + 1.9) ** 2 + (z - 0.9) ** 2) / 5.6) *
    (1.4 + difficultyFactor);
  const peakB =
    Math.exp(-((x - 1.65) ** 2 + (z + 1.15) ** 2) / 3.3) *
    (0.9 + difficultyFactor * 0.8);
  const basin = Math.exp(-((x + 0.2) ** 2 + (z + 0.2) ** 2) / 8.2) * 0.34;
  const detailNoise = fbm2D(x * 0.85, z * 0.85, seed, 5) * 0.19;
  const fineNoise = fbm2D(x * 3.6, z * 3.6, seed + 91.3, 3) * 0.055;

  const relief =
    (longRidge + crossRidge + peakA + peakB - basin + detailNoise + fineNoise) *
    (0.45 + difficultyFactor * 0.34);

  return 0.08 + relief * (RELIEF_EXAGGERATION + difficultyFactor * 0.12);
};

const getSlopeAt = (
  x: number,
  z: number,
  difficultyFactor: number,
  seed: number
) => {
  const eps = 0.06;
  const left = getHeightAt(x - eps, z, difficultyFactor, seed);
  const right = getHeightAt(x + eps, z, difficultyFactor, seed);
  const down = getHeightAt(x, z - eps, difficultyFactor, seed);
  const up = getHeightAt(x, z + eps, difficultyFactor, seed);

  return clamp((Math.abs(right - left) + Math.abs(up - down)) / (eps * 4), 0, 1);
};

const interpolateColor = (
  low: THREE.Color,
  high: THREE.Color,
  amount: number
) => low.clone().lerp(high, clamp(amount, 0, 1));

const getTerrainColor = (
  height: number,
  difficultyFactor: number,
  steepness: number,
  x: number,
  z: number,
  seed: number,
  biome: TerrainBiome
) => {
  const palette = biome === "steppe"
    ? {
        valley: "#8B7651",
        forest: "#A18B5D",
        grass: "#B2A16F",
        scree: "#C1AD83",
        rock: "#9B8874",
        cliff: "#665A4E",
        snow: "#D8D0C2",
      }
    : biome === "alpine"
      ? {
          valley: "#355F42",
          forest: "#4C7448",
          grass: "#718B50",
          scree: "#958C6C",
          rock: "#77736B",
          cliff: "#4A4B48",
          snow: "#E7ECE8",
        }
      : {
          valley: "#244E38",
          forest: "#356B43",
          grass: "#62884D",
          scree: "#8C8A62",
          rock: "#746E5E",
          cliff: "#454942",
          snow: "#E5EBE3",
        };
  const valley = new THREE.Color(palette.valley);
  const forest = new THREE.Color(palette.forest);
  const grass = new THREE.Color(palette.grass);
  const scree = new THREE.Color(palette.scree);
  const rock = new THREE.Color(palette.rock);
  const cliff = new THREE.Color(palette.cliff);
  const snow = new THREE.Color(palette.snow);
  const normalized = clamp(
    height / ((1.45 + difficultyFactor) * RELIEF_EXAGGERATION),
    0,
    1
  );
  const terrainNoise = fbm2D(x * 1.65, z * 1.65, seed + 37.1, 4);
  const fineNoise = fbm2D(x * 5.2, z * 5.2, seed + 113.4, 3);
  let base: THREE.Color;

  if (normalized < 0.24) {
    base = interpolateColor(valley, forest, normalized / 0.24);
  } else if (normalized < 0.5) {
    base = interpolateColor(forest, grass, (normalized - 0.24) / 0.26);
  } else if (normalized < 0.72) {
    base = interpolateColor(grass, scree, (normalized - 0.5) / 0.22);
  } else if (normalized < 0.91) {
    base = interpolateColor(scree, rock, (normalized - 0.72) / 0.19);
  } else {
    base = interpolateColor(rock, snow, (normalized - 0.91) / 0.09);
  }

  const rockExposure = clamp((steepness - 0.2) * 2.4 + terrainNoise * 0.12, 0, 0.88);
  const snowPatch = clamp((normalized - 0.82) * 4.6 + terrainNoise * 0.32, 0, 0.72);
  const sunSide = Math.sin((x + seed) * 0.75) * 0.5 + Math.cos((z - seed) * 0.92) * 0.5;
  const textureAmount = clamp(Math.abs(fineNoise) * 0.14, 0, 0.16);

  base = interpolateColor(base, rockExposure > 0.58 ? cliff : rock, rockExposure);
  base = interpolateColor(base, snow, snowPatch);
  base = interpolateColor(base, new THREE.Color("#D5D0B4"), textureAmount);

  if (sunSide > 0) {
    return interpolateColor(base, new THREE.Color("#FFF1C4"), sunSide * 0.08);
  }

  return interpolateColor(base, new THREE.Color("#273126"), Math.abs(sunSide) * 0.18);
};

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

const buildTerrainMesh = (model: TerrainModel) => {
  const positions: number[] = [];
  const colors: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];
  const color = new THREE.Color();

  for (let row = 0; row <= GRID_SIZE; row += 1) {
    for (let column = 0; column <= GRID_SIZE; column += 1) {
      const x = -TERRAIN_HALF_SIZE + (column / GRID_SIZE) * TERRAIN_HALF_SIZE * 2;
      const z = -TERRAIN_HALF_SIZE + (row / GRID_SIZE) * TERRAIN_HALF_SIZE * 2;
      const height = getHeightAt(
        x,
        z,
        model.difficultyFactor,
        model.seed
      );
      const steepness = getSlopeAt(x, z, model.difficultyFactor, model.seed);
      color.copy(
        getTerrainColor(
          height,
          model.difficultyFactor,
          steepness,
          x,
          z,
          model.seed,
          model.biome
        )
      );

      positions.push(x, height, z);
      colors.push(color.r, color.g, color.b);
      uvs.push(column / GRID_SIZE, 1 - row / GRID_SIZE);
    }
  }

  for (let row = 0; row < GRID_SIZE; row += 1) {
    for (let column = 0; column < GRID_SIZE; column += 1) {
      const a = row * (GRID_SIZE + 1) + column;
      const b = a + 1;
      const c = a + (GRID_SIZE + 1);
      const d = c + 1;

      indices.push(a, c, b, b, c, d);
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setIndex(indices);
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.computeVertexNormals();

  const material = new THREE.MeshStandardMaterial({
    roughness: 0.88,
    metalness: 0.02,
    vertexColors: true,
  });
  const terrain = new THREE.Mesh(geometry, material);
  terrain.receiveShadow = true;

  return terrain;
};

const makeTube = (
  points: THREE.Vector3[],
  radius: number,
  color: string,
  opacity = 1
) => {
  const curve = new THREE.CatmullRomCurve3(points, false, "centripetal", 0.35);
  const geometry = new THREE.TubeGeometry(
    curve,
    Math.max(24, points.length * 10),
    radius,
    8,
    false
  );
  const material = new THREE.MeshStandardMaterial({
    color,
    emissive: color,
    emissiveIntensity: radius < 0.06 ? 0.04 : 0.01,
    opacity,
    transparent: opacity < 1,
    roughness: 0.62,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.castShadow = true;

  return mesh;
};

const getSatelliteTextureUrl = (model: TerrainModel) => {
  const metersPerLatitudeDegree = (Math.PI * EARTH_RADIUS_METERS) / 180;
  const metersPerLongitudeDegree =
    metersPerLatitudeDegree * Math.cos((model.origin[0] * Math.PI) / 180);
  const toCoordinate = (x: number, z: number): Coordinate => {
    const localX = model.bounds.centerX + x * model.bounds.metersPerUnit;
    const localZ = model.bounds.centerZ + z * model.bounds.metersPerUnit;
    return [
      model.origin[0] - localZ / metersPerLatitudeDegree,
      model.origin[1] + localX / metersPerLongitudeDegree,
    ];
  };
  const northWest = toCoordinate(-TERRAIN_HALF_SIZE, -TERRAIN_HALF_SIZE);
  const southEast = toCoordinate(TERRAIN_HALF_SIZE, TERRAIN_HALF_SIZE);
  const params = new URLSearchParams({
    bbox: `${northWest[1]},${southEast[0]},${southEast[1]},${northWest[0]}`,
    bboxSR: "4326",
    imageSR: "4326",
    size: "1024,1024",
    format: "jpg",
    transparent: "false",
    f: "image",
  });

  return `https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?${params.toString()}`;
};

const applySatelliteTexture = (
  terrain: THREE.Mesh,
  model: TerrainModel,
  onLoad: (texture: THREE.Texture) => void,
  onError: () => void
) => {
  const loader = new TextureLoader();
  loader.setCrossOrigin("anonymous");
  loader.load(
    getSatelliteTextureUrl(model),
    (texture) => {
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.anisotropy = 4;
      texture.needsUpdate = true;
      const material = terrain.material as THREE.MeshStandardMaterial;
      material.map = texture;
      material.vertexColors = false;
      material.color.set("#FFFFFF");
      material.roughness = 0.94;
      material.needsUpdate = true;
      onLoad(texture);
    },
    undefined,
    onError
  );
};

const buildTerrainSkirt = (model: TerrainModel) => {
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const topColor = new THREE.Color(model.biome === "steppe" ? "#77644D" : "#465641");
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
      const topY = getHeightAt(x, z, model.difficultyFactor, model.seed);
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

const sampleRouteOnTerrain = (model: TerrainModel) => {
  if (model.route.length < 2) return model.route;

  const sampledRoute: THREE.Vector3[] = [];
  const maxSegmentLength = 0.055;

  for (let index = 1; index < model.route.length; index += 1) {
    const start = model.route[index - 1];
    const end = model.route[index];
    const segmentLength = Math.hypot(end.x - start.x, end.z - start.z);
    const steps = Math.max(1, Math.ceil(segmentLength / maxSegmentLength));

    for (let step = 0; step < steps; step += 1) {
      const progress = step / steps;
      const x = start.x + (end.x - start.x) * progress;
      const z = start.z + (end.z - start.z) * progress;
      sampledRoute.push(
        new THREE.Vector3(
          x,
          getHeightAt(x, z, model.difficultyFactor, model.seed),
          z
        )
      );
    }
  }

  const lastPoint = model.route[model.route.length - 1];
  sampledRoute.push(
    new THREE.Vector3(
      lastPoint.x,
      getHeightAt(lastPoint.x, lastPoint.z, model.difficultyFactor, model.seed),
      lastPoint.z
    )
  );

  return sampledRoute;
};

const getSmoothedCrossSlopes = (
  centerLine: THREE.Vector3[],
  model: TerrainModel
) => {
  const sampleDistance = 0.045;
  const rawSlopes = centerLine.map((point, index) => {
    const previous = centerLine[Math.max(0, index - 1)];
    const next = centerLine[Math.min(centerLine.length - 1, index + 1)];
    const dx = next.x - previous.x;
    const dz = next.z - previous.z;
    const length = Math.max(0.001, Math.hypot(dx, dz));
    const normalX = -dz / length;
    const normalZ = dx / length;
    const leftHeight = getHeightAt(
      point.x - normalX * sampleDistance,
      point.z - normalZ * sampleDistance,
      model.difficultyFactor,
      model.seed
    );
    const rightHeight = getHeightAt(
      point.x + normalX * sampleDistance,
      point.z + normalZ * sampleDistance,
      model.difficultyFactor,
      model.seed
    );

    return clamp(
      (rightHeight - leftHeight) / (sampleDistance * 2),
      -1.25,
      1.25
    );
  });

  return rawSlopes.map((_, index) => {
    const start = Math.max(0, index - 2);
    const end = Math.min(rawSlopes.length - 1, index + 2);
    let total = 0;

    for (let sampleIndex = start; sampleIndex <= end; sampleIndex += 1) {
      total += rawSlopes[sampleIndex];
    }

    return total / (end - start + 1);
  });
};

const makeTerrainTrailRibbon = (
  centerLine: THREE.Vector3[],
  model: TerrainModel,
  halfWidth: number,
  color: string,
  lift: number,
  highlighted: boolean
) => {
  const positions: number[] = [];
  const vertexColors: number[] = [];
  const indices: number[] = [];
  const baseColor = new THREE.Color(color);
  const crossSlopes = getSmoothedCrossSlopes(centerLine, model);

  centerLine.forEach((point, index) => {
    const previous = centerLine[Math.max(0, index - 1)];
    const next = centerLine[Math.min(centerLine.length - 1, index + 1)];
    const dx = next.x - previous.x;
    const dz = next.z - previous.z;
    const length = Math.max(0.001, Math.hypot(dx, dz));
    const normalX = -dz / length;
    const normalZ = dx / length;
    const shade = highlighted
      ? 1
      : 0.88 + hash01(index * 0.67, model.seed, 81) * 0.2;
    const shadedColor = baseColor.clone().multiplyScalar(shade);

    [-1, 1].forEach((side) => {
      const offset = halfWidth * side;
      positions.push(
        point.x + normalX * offset,
        point.y + crossSlopes[index] * offset + lift,
        point.z + normalZ * offset
      );
      vertexColors.push(shadedColor.r, shadedColor.g, shadedColor.b);
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

const makeRouteEndpointCap = (
  position: THREE.Vector3,
  radius: number,
  color: string,
  opacity = 1
) => {
  const geometry = new THREE.SphereGeometry(radius, 20, 12);
  const material = new THREE.MeshStandardMaterial({
    color,
    emissive: color,
    emissiveIntensity: radius < 0.06 ? 0.04 : 0.01,
    opacity,
    transparent: opacity < 1,
    roughness: 0.62,
  });
  const cap = new THREE.Mesh(geometry, material);
  cap.position.copy(position);
  cap.castShadow = true;

  return cap;
};

const makeRouteAnchor = (position: THREE.Vector3, markerColor: string) => {
  const group = new THREE.Group();
  const shadowMaterial = new THREE.MeshStandardMaterial({
    color: ROUTE_SHADOW_COLOR,
    opacity: 0.22,
    transparent: true,
    roughness: 0.72,
  });
  const surfaceMaterial = new THREE.MeshStandardMaterial({
    color: ROUTE_SURFACE_COLOR,
    roughness: 0.58,
  });
  const routeMaterial = new THREE.MeshStandardMaterial({
    color: ROUTE_CORE_COLOR,
    emissive: ROUTE_CORE_COLOR,
    emissiveIntensity: 0.04,
    roughness: 0.58,
  });
  const markerMaterial = new THREE.MeshStandardMaterial({
    color: markerColor,
    emissive: markerColor,
    emissiveIntensity: 0.08,
    roughness: 0.56,
  });
  const layers = [
    { radius: 0.27, height: 0.035, material: shadowMaterial, y: -0.012 },
    { radius: 0.215, height: 0.034, material: surfaceMaterial, y: 0.006 },
    { radius: 0.155, height: 0.038, material: routeMaterial, y: 0.026 },
    { radius: 0.07, height: 0.042, material: markerMaterial, y: 0.052 },
  ];

  group.position.copy(position);

  layers.forEach((layer) => {
    const disc = new THREE.Mesh(
      new THREE.CylinderGeometry(layer.radius, layer.radius, layer.height, 32),
      layer.material
    );
    disc.position.y = layer.y;
    disc.castShadow = true;
    disc.receiveShadow = true;
    group.add(disc);
  });

  return group;
};

const makeStartPin = (position: THREE.Vector3) => {
  const group = new THREE.Group();
  const green = "#008955";
  const darkGreen = "#075B3D";
  const poleMaterial = new THREE.MeshStandardMaterial({
    color: darkGreen,
    roughness: 0.68,
  });
  const headMaterial = new THREE.MeshStandardMaterial({
    color: green,
    emissive: green,
    emissiveIntensity: 0.12,
    roughness: 0.5,
  });
  const pole = new THREE.Mesh(
    new THREE.CylinderGeometry(0.022, 0.03, 0.45, 14),
    poleMaterial
  );
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.13, 24, 16), headMaterial);
  const point = new THREE.Mesh(new THREE.ConeGeometry(0.095, 0.2, 24), headMaterial);

  group.position.copy(position);
  group.position.y += 0.07;
  pole.position.y = 0.23;
  head.position.y = 0.53;
  point.position.y = 0.42;
  point.rotation.x = Math.PI;
  pole.castShadow = true;
  head.castShadow = true;
  point.castShadow = true;
  group.add(pole);
  group.add(head);
  group.add(point);

  return group;
};

const makeCheckeredFinishFlag = (position: THREE.Vector3) => {
  const group = new THREE.Group();
  const poleMaterial = new THREE.MeshStandardMaterial({
    color: "#2C2A24",
    metalness: 0.08,
    roughness: 0.48,
  });
  const whiteMaterial = new THREE.MeshStandardMaterial({
    color: "#FFFFFF",
    roughness: 0.5,
    side: THREE.DoubleSide,
  });
  const blackMaterial = new THREE.MeshStandardMaterial({
    color: "#111111",
    roughness: 0.5,
    side: THREE.DoubleSide,
  });
  const borderMaterial = new THREE.MeshStandardMaterial({
    color: "#F6F1E7",
    roughness: 0.54,
    side: THREE.DoubleSide,
  });
  const pole = new THREE.Mesh(
    new THREE.CylinderGeometry(0.025, 0.032, 0.82, 14),
    poleMaterial
  );
  const finial = new THREE.Mesh(new THREE.SphereGeometry(0.045, 16, 10), poleMaterial);
  const flagBack = new THREE.Mesh(new THREE.PlaneGeometry(0.51, 0.285), borderMaterial);
  const flagGroup = new THREE.Group();
  const columns = 4;
  const rows = 3;
  const cellWidth = 0.12;
  const cellHeight = 0.075;
  const left = 0.075;
  const top = 0.66;

  group.position.copy(position);
  group.position.y += 0.055;
  pole.position.y = 0.41;
  finial.position.y = 0.84;
  flagBack.position.set(left + (columns * cellWidth) / 2, top - (rows * cellHeight) / 2, -0.004);
  pole.castShadow = true;
  finial.castShadow = true;
  flagBack.castShadow = true;
  group.add(pole);
  group.add(finial);
  group.add(flagBack);

  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const material = (row + column) % 2 === 0 ? whiteMaterial : blackMaterial;
      const square = new THREE.Mesh(new THREE.PlaneGeometry(cellWidth, cellHeight), material);
      square.position.set(
        left + cellWidth * (column + 0.5),
        top - cellHeight * (row + 0.5),
        Math.sin((column / columns) * Math.PI) * 0.012
      );
      square.castShadow = true;
      flagGroup.add(square);
    }
  }

  group.add(flagGroup);

  return group;
};

const makeMarker = (position: THREE.Vector3, color: string) => {
  const geometry = new THREE.SphereGeometry(0.16, 24, 16);
  const material = new THREE.MeshStandardMaterial({
    color,
    emissive: color,
    emissiveIntensity: 0.12,
    roughness: 0.52,
  });
  const marker = new THREE.Mesh(geometry, material);
  marker.position.copy(position);
  marker.position.y += 0.24;
  marker.castShadow = true;

  return marker;
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
  if (navigationMode) {
    const startPoint = terrainRoute[0].clone();
    const nextPoint =
      terrainRoute.find((point, index) => {
        if (index === 0) return false;
        const deltaX = point.x - startPoint.x;
        const deltaZ = point.z - startPoint.z;
        return deltaX * deltaX + deltaZ * deltaZ > 0.0064;
      }) || terrainRoute[1];
    const sightPoint =
      terrainRoute.find((point, index) => {
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
    return;
  }

  handles.navigationView = null;
  if (!userCoordinate) return;
  const userPoint = toScenePoint(userCoordinate, model);
  const markerGroup = new THREE.Group();
  markerGroup.add(makeUserMarker(userPoint), makeVerticalPin(userPoint, "#2376D9"));
  handles.routeGroup.add(markerGroup);
  handles.trackedObject = markerGroup;
};

const addContourLines = (group: THREE.Group, model: TerrainModel) => {
  for (let index = 0; index < 16; index += 1) {
    const z = -4.1 + index * 0.55;
    const points: THREE.Vector3[] = [];

    for (let step = 0; step <= 96; step += 1) {
      const x = -4.15 + (step / 96) * 8.3;
      const height = getHeightAt(x, z, model.difficultyFactor, model.seed);
      points.push(new THREE.Vector3(x, height + 0.012, z));
    }

    group.add(
      new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(points),
        new THREE.LineBasicMaterial({
          color: "#FFFFFF",
          opacity: index % 4 === 0 ? 0.34 : 0.2,
          transparent: true,
        })
      )
    );
  }

  for (let index = 0; index < 9; index += 1) {
    const x = -3.8 + index * 0.95;
    const points: THREE.Vector3[] = [];

    for (let step = 0; step <= 72; step += 1) {
      const z = -4 + (step / 72) * 8;
      const height = getHeightAt(x, z, model.difficultyFactor, model.seed);
      points.push(new THREE.Vector3(x, height + 0.014, z));
    }

    group.add(
      new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(points),
        new THREE.LineBasicMaterial({
          color: "#F4E9CA",
          opacity: 0.12,
          transparent: true,
        })
      )
    );
  }
};

const getOffsetRoute = (
  route: THREE.Vector3[],
  model: TerrainModel,
  offset: number,
  lift: number,
  wave = 0
) =>
  route.map((point, index) => {
    const previous = route[Math.max(0, index - 1)];
    const next = route[Math.min(route.length - 1, index + 1)];
    const dx = next.x - previous.x;
    const dz = next.z - previous.z;
    const length = Math.max(0.01, Math.hypot(dx, dz));
    const shift = offset + Math.sin(index * 0.88 + model.seed) * wave;
    const x = point.x + (-dz / length) * shift;
    const z = point.z + (dx / length) * shift;
    const height = getHeightAt(x, z, model.difficultyFactor, model.seed);

    return new THREE.Vector3(x, height + lift, z);
  });

const addReferenceTerrainLines = (group: THREE.Group, model: TerrainModel) => {
  if (model.route.length < 2) return;

  const creek = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(getOffsetRoute(model.route, model, 0.48, 0.02, 0.08)),
    new THREE.LineBasicMaterial({
      color: "#55BDE0",
      opacity: 0.62,
      transparent: true,
    })
  );
  group.add(creek);

  const sideTrailGeometry = new THREE.BufferGeometry().setFromPoints(
    getOffsetRoute(model.route, model, -0.62, 0.035, 0.1)
  );
  const sideTrail = new THREE.Line(
    sideTrailGeometry,
    new THREE.LineDashedMaterial({
      color: "#E6B183",
      dashSize: 0.18,
      gapSize: 0.13,
      opacity: 0.54,
      transparent: true,
    })
  );
  sideTrail.computeLineDistances();
  group.add(sideTrail);

  for (let index = 0; index < 6; index += 1) {
    const ridgeX = -3.6 + index * 1.45;
    const ridgePoints: THREE.Vector3[] = [];

    for (let step = 0; step <= 54; step += 1) {
      const z = -3.8 + (step / 54) * 7.6;
      const x = ridgeX + Math.sin(step * 0.18 + model.seed + index) * 0.12;
      const height = getHeightAt(x, z, model.difficultyFactor, model.seed);
      const slope = getSlopeAt(x, z, model.difficultyFactor, model.seed);

      if (slope > 0.2) {
        ridgePoints.push(new THREE.Vector3(x, height + 0.018, z));
      }
    }

    if (ridgePoints.length > 3) {
      group.add(
        new THREE.Line(
          new THREE.BufferGeometry().setFromPoints(ridgePoints),
          new THREE.LineBasicMaterial({
            color: "#2C2A24",
            opacity: 0.16,
            transparent: true,
          })
        )
      );
    }
  }
};

const TREE_COUNT = 230;
const TRUNK_HEIGHT = 0.14;
const FOLIAGE_HEIGHT = 0.24;

const addVegetation = (group: THREE.Group, model: TerrainModel) => {
  const targetCount = model.biome === "steppe" ? 58 : model.biome === "alpine" ? 145 : TREE_COUNT;
  const trunkGeometry = new THREE.CylinderGeometry(0.012, 0.024, TRUNK_HEIGHT, 7);
  const trunkMaterial = new THREE.MeshStandardMaterial({
    color: "#6B4A31",
    roughness: 0.92,
  });
  const foliageGeometry = model.biome === "forest"
    ? new THREE.IcosahedronGeometry(0.095, 1)
    : model.biome === "steppe"
      ? new THREE.IcosahedronGeometry(0.075, 1)
      : new THREE.ConeGeometry(0.1, FOLIAGE_HEIGHT, 9);
  const foliageTopGeometry = model.biome === "forest"
    ? new THREE.IcosahedronGeometry(0.075, 1)
    : model.biome === "steppe"
      ? new THREE.IcosahedronGeometry(0.055, 1)
      : new THREE.ConeGeometry(0.075, FOLIAGE_HEIGHT * 0.82, 9);
  const foliageMaterial = new THREE.MeshStandardMaterial({
    color: model.biome === "steppe" ? "#8D8B45" : model.biome === "alpine" ? "#416D3F" : "#2F7142",
    roughness: 0.85,
  });
  const trunks = new THREE.InstancedMesh(trunkGeometry, trunkMaterial, TREE_COUNT);
  const foliage = new THREE.InstancedMesh(foliageGeometry, foliageMaterial, TREE_COUNT);
  const foliageTop = new THREE.InstancedMesh(foliageTopGeometry, foliageMaterial, TREE_COUNT);
  trunks.castShadow = true;
  trunks.receiveShadow = true;
  foliage.castShadow = true;
  foliage.receiveShadow = true;
  foliageTop.castShadow = true;
  foliageTop.receiveShadow = true;

  const dummy = new THREE.Object3D();
  let placed = 0;
  let attempt = 0;

  while (placed < targetCount && attempt < targetCount * 12) {
    attempt += 1;
    const rx = hash01(attempt * 3.11, model.seed, model.seed + 1) * TERRAIN_HALF_SIZE * 1.9 - TERRAIN_HALF_SIZE * 0.95;
    const rz = hash01(model.seed, attempt * 5.73, model.seed + 2) * TERRAIN_HALF_SIZE * 1.9 - TERRAIN_HALF_SIZE * 0.95;
    const height = getHeightAt(rx, rz, model.difficultyFactor, model.seed);
    const steepness = getSlopeAt(rx, rz, model.difficultyFactor, model.seed);
    const normalizedHeight = clamp(
      height / ((1.45 + model.difficultyFactor) * RELIEF_EXAGGERATION),
      0,
      1
    );

    const treeLine = model.biome === "alpine" ? 0.48 : 0.64;
    if (steepness > 0.32 || normalizedHeight < 0.06 || normalizedHeight > treeLine ||
      (model.biome === "steppe" && hash01(rx, rz, model.seed + 40) > 0.24)) {
      continue;
    }

    const tooCloseToRoute = model.route.some(
      (point) => Math.hypot(point.x - rx, point.z - rz) < 0.22
    );
    if (tooCloseToRoute) continue;

    const scale = 0.65 + hash01(rx * 91.7, rz * 57.1, model.seed + 3) * 0.85;
    const rotationY = hash01(rx * 13.1, rz * 27.3, model.seed + 4) * Math.PI * 2;

    dummy.rotation.set(0, rotationY, 0);
    dummy.scale.setScalar(scale);
    dummy.position.set(rx, height + (TRUNK_HEIGHT / 2) * scale, rz);
    dummy.updateMatrix();
    trunks.setMatrixAt(placed, dummy.matrix);

    dummy.position.y = height + (TRUNK_HEIGHT + FOLIAGE_HEIGHT / 2) * scale;
    dummy.updateMatrix();
    foliage.setMatrixAt(placed, dummy.matrix);

    dummy.position.y = height + (TRUNK_HEIGHT + FOLIAGE_HEIGHT * 0.95) * scale;
    dummy.scale.setScalar(scale * 0.82);
    dummy.updateMatrix();
    foliageTop.setMatrixAt(placed, dummy.matrix);

    placed += 1;
  }

  trunks.count = placed;
  foliage.count = placed;
  foliageTop.count = placed;
  trunks.instanceMatrix.needsUpdate = true;
  foliage.instanceMatrix.needsUpdate = true;
  foliageTop.instanceMatrix.needsUpdate = true;

  group.add(trunks);
  group.add(foliage);
  group.add(foliageTop);
};

const addGroundDetails = (group: THREE.Group, model: TerrainModel) => {
  const rockCount = model.biome === "forest" ? 115 : 210;
  const grassCount = model.biome === "steppe" ? 260 : 330;
  const rockGeometry = new THREE.DodecahedronGeometry(0.045, 0);
  const rockMaterial = new THREE.MeshStandardMaterial({
    color: model.biome === "steppe" ? "#8A765E" : "#77766E",
    roughness: 1,
  });
  const grassGeometry = new THREE.ConeGeometry(0.018, 0.09, 3);
  const grassMaterial = new THREE.MeshStandardMaterial({
    color: model.biome === "steppe" ? "#A39A4C" : "#5F913F",
    roughness: 0.95,
  });
  const rocks = new THREE.InstancedMesh(rockGeometry, rockMaterial, rockCount);
  const grass = new THREE.InstancedMesh(grassGeometry, grassMaterial, grassCount);
  const dummy = new THREE.Object3D();

  const populate = (mesh: THREE.InstancedMesh, count: number, isRock: boolean) => {
    let placed = 0;
    for (let attempt = 0; placed < count && attempt < count * 5; attempt += 1) {
      const x = hash01(attempt * 8.17, model.seed + 19, model.seed) * TERRAIN_HALF_SIZE * 1.9 - TERRAIN_HALF_SIZE * 0.95;
      const z = hash01(model.seed + 23, attempt * 4.91, model.seed) * TERRAIN_HALF_SIZE * 1.9 - TERRAIN_HALF_SIZE * 0.95;
      const slope = getSlopeAt(x, z, model.difficultyFactor, model.seed);
      if ((!isRock && slope > 0.27) || model.route.some((p) => Math.hypot(p.x - x, p.z - z) < 0.16)) continue;
      const y = getHeightAt(x, z, model.difficultyFactor, model.seed);
      const scale = (isRock ? 0.65 : 0.55) + hash01(x * 17, z * 29, model.seed) * (isRock ? 1.5 : 0.8);
      dummy.position.set(x, y + (isRock ? 0.025 : 0.04) * scale, z);
      dummy.rotation.set(hash01(x, z, 2) * 0.5, hash01(x, z, 3) * Math.PI, hash01(x, z, 4) * 0.35);
      dummy.scale.set(scale * (isRock ? 1.25 : 1), scale, scale * (isRock ? 0.9 : 1));
      dummy.updateMatrix();
      mesh.setMatrixAt(placed, dummy.matrix);
      placed += 1;
    }
    mesh.count = placed;
    mesh.instanceMatrix.needsUpdate = true;
  };
  populate(rocks, rockCount, true);
  populate(grass, grassCount, false);
  rocks.castShadow = true;
  rocks.receiveShadow = true;
  group.add(rocks, grass);
};

const toScenePoint = (coordinate: Coordinate, model: TerrainModel) => {
  const local = toLocalMeters(coordinate, model.origin);
  const x = (local.x - model.bounds.centerX) / model.bounds.metersPerUnit;
  const z = (local.z - model.bounds.centerZ) / model.bounds.metersPerUnit;

  return new THREE.Vector3(
    x,
    getHeightAt(x, z, model.difficultyFactor, model.seed),
    z
  );
};

const normalizeWeatherText = (value: string) =>
  value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

const getWeatherKind = (condition = "", rainProbability = 0) => {
  const normalized = normalizeWeatherText(condition);
  if (normalized.includes("nieve") || normalized.includes("nevada")) return "snow";
  if (normalized.includes("torment")) return "storm";
  if (normalized.includes("lluv") || normalized.includes("chaparr") || rainProbability >= 55) return "rain";
  if (normalized.includes("nubl") || normalized.includes("cubierto")) return "cloudy";
  if (normalized.includes("parcial") || normalized.includes("nubes")) return "partly-cloudy";
  return "clear";
};

const buildSkyDome = (weather: Terrain3DSceneProps["weather"]) => {
  const kind = getWeatherKind(weather?.condition, weather?.rainProbability);
  const colorsByKind = {
    clear: ["#418BC1", "#D9EFF5"],
    "partly-cloudy": ["#648FAC", "#D8E5E9"],
    cloudy: ["#667681", "#C4CDD0"],
    rain: ["#405565", "#9BAAB1"],
    storm: ["#273743", "#73838B"],
    snow: ["#839BAA", "#E8F0F1"],
  } as const;
  const [topColor, bottomColor] = colorsByKind[kind];
  const geometry = new THREE.SphereGeometry(60, 24, 16);
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

const addWeatherGraphics = (
  group: THREE.Group,
  weather: Terrain3DSceneProps["weather"]
) => {
  const kind = getWeatherKind(weather?.condition, weather?.rainProbability);
  const cloudKinds = ["partly-cloudy", "cloudy", "rain", "storm", "snow"];

  if (kind === "clear" || kind === "partly-cloudy") {
    const sun = new THREE.Mesh(
      new THREE.SphereGeometry(0.58, 24, 18),
      new THREE.MeshBasicMaterial({ color: "#FFD466", fog: false })
    );
    sun.position.set(-4.8, 5.9, -5.8);
    group.add(sun);
  }

  if (cloudKinds.includes(kind)) {
    const cloudCount = kind === "partly-cloudy" ? 3 : kind === "cloudy" ? 6 : 8;
    const cloudMaterial = new THREE.MeshStandardMaterial({
      color: kind === "storm" ? "#65727A" : kind === "rain" ? "#86969D" : "#E8EEF0",
      roughness: 1,
      transparent: true,
      opacity: kind === "partly-cloudy" ? 0.84 : 0.94,
      fog: false,
    });
    for (let index = 0; index < cloudCount; index += 1) {
      const cloud = new THREE.Group();
      const x = -5.8 + (index % 4) * 3.8 + hash01(index, 1, 52) * 0.6;
      const y = 4.6 + Math.floor(index / 4) * 1.15 + hash01(index, 2, 53) * 0.4;
      const z = -5.5 + (index % 2) * 1.1;
      [
        [-0.52, 0, 0, 0.72],
        [0, 0.17, 0, 0.92],
        [0.58, 0, 0, 0.68],
        [0.18, -0.1, 0.08, 0.78],
      ].forEach(([cx, cy, cz, scale]) => {
        const puff = new THREE.Mesh(new THREE.SphereGeometry(0.55, 12, 8), cloudMaterial);
        puff.position.set(cx, cy, cz);
        puff.scale.set(scale * 1.5, scale * 0.72, scale);
        cloud.add(puff);
      });
      cloud.position.set(x, y, z);
      cloud.name = "weather-cloud";
      cloud.userData.speed = 0.015 + hash01(index, 14, 61) * 0.018;
      cloud.userData.originX = x;
      group.add(cloud);
    }
  }

  if (["rain", "storm", "snow"].includes(kind)) {
    const precipitationCount = kind === "storm" ? 150 : 95;
    const isSnow = kind === "snow";
    const geometry = isSnow
      ? new THREE.SphereGeometry(0.018, 5, 4)
      : new THREE.CylinderGeometry(0.006, 0.006, 0.24, 4);
    const material = new THREE.MeshBasicMaterial({
      color: isSnow ? "#FFFFFF" : "#9DD4E9",
      transparent: true,
      opacity: 0.76,
      fog: false,
    });
    const precipitation = new THREE.InstancedMesh(geometry, material, precipitationCount);
    const dummy = new THREE.Object3D();
    for (let index = 0; index < precipitationCount; index += 1) {
      dummy.position.set(
        hash01(index, 5, 71) * 12 - 6,
        hash01(index, 7, 72) * 5 + 1.2,
        hash01(index, 9, 73) * 8 - 4
      );
      dummy.rotation.z = isSnow ? 0 : -0.18;
      const scale = 0.65 + hash01(index, 11, 74) * 0.75;
      dummy.scale.setScalar(scale);
      dummy.updateMatrix();
      precipitation.setMatrixAt(index, dummy.matrix);
    }
    precipitation.instanceMatrix.needsUpdate = true;
    precipitation.name = "weather-precipitation";
    group.add(precipitation);
  }
};

export function Terrain3DScene({
  routePoints,
  fallbackCenter,
  difficulty,
  distanceKm,
  userCoordinate,
  viewOffset,
  viewScale,
  trailLabel,
  weather,
  navigationMode = false,
  satelliteTextureEnabled = true,
}: Terrain3DSceneProps) {
  const handlesRef = useRef<SceneHandles | null>(null);
  const propsRef = useRef({
    routePoints,
    fallbackCenter,
    difficulty,
    distanceKm,
    userCoordinate,
    viewOffset,
    viewScale,
    trailLabel,
    weather,
    navigationMode,
    satelliteTextureEnabled,
  });
  const geometrySignature = useMemo(
    () =>
      JSON.stringify({
        routePoints,
        fallbackCenter,
        difficulty,
        distanceKm,
        trailLabel,
        weather,
        navigationMode,
        satelliteTextureEnabled,
      }),
    [
      routePoints,
      fallbackCenter,
      difficulty,
      distanceKm,
      trailLabel,
      weather,
      navigationMode,
      satelliteTextureEnabled,
    ]
  );

  useEffect(() => {
    propsRef.current = {
      routePoints,
      fallbackCenter,
      difficulty,
      distanceKm,
      userCoordinate,
      viewOffset,
      viewScale,
      trailLabel,
      weather,
      navigationMode,
      satelliteTextureEnabled,
    };
  }, [
    routePoints,
    fallbackCenter,
    difficulty,
    distanceKm,
    userCoordinate,
    viewOffset,
    viewScale,
    trailLabel,
    weather,
    navigationMode,
    satelliteTextureEnabled,
  ]);

  const rebuildScene = useCallback(() => {
    const handles = handlesRef.current;
    if (!handles) return;

    const current = propsRef.current;
    const rebuildId = handles.rebuildId + 1;
    handles.rebuildId = rebuildId;
    const model = buildTerrainModel(
      current.routePoints,
      current.fallbackCenter,
      current.difficulty,
      current.trailLabel
    );
    clearGroup(handles.terrainGroup);
    clearGroup(handles.routeGroup);
    clearGroup(handles.weatherGroup);
    handles.trackedObject = null;
    const weatherKind = getWeatherKind(current.weather?.condition, current.weather?.rainProbability);
    const isDarkWeather = weatherKind === "storm" || weatherKind === "rain";
    const fogColor = weatherKind === "storm"
      ? "#66747B"
      : weatherKind === "rain"
        ? "#899CA5"
        : weatherKind === "snow"
          ? "#DDE7E9"
          : "#CFE4E8";
    handles.scene.fog = new THREE.FogExp2(fogColor, isDarkWeather ? 0.06 : 0.035);
    handles.renderer.setClearColor(fogColor);
    handles.sunLight.intensity = weatherKind === "clear" ? 3.35 : isDarkWeather ? 1.25 : 2.25;
    handles.hemiLight.intensity = isDarkWeather ? 0.72 : 1.05;
    handles.weatherGroup.add(buildSkyDome(current.weather));
    addWeatherGraphics(handles.weatherGroup, current.weather);
    const terrain = buildTerrainMesh(model);
    handles.terrainGroup.add(terrain);
    if (current.satelliteTextureEnabled) {
      applySatelliteTexture(terrain, model, (texture) => {
        if (handlesRef.current !== handles || handles.rebuildId !== rebuildId) {
          texture.dispose();
        }
      }, () => {
        if (handlesRef.current === handles && handles.rebuildId === rebuildId) {
          addVegetation(handles.terrainGroup, model);
          addGroundDetails(handles.terrainGroup, model);
        }
      });
    }
    handles.terrainGroup.add(buildTerrainSkirt(model));
    if (!current.satelliteTextureEnabled) {
      addVegetation(handles.terrainGroup, model);
      addGroundDetails(handles.terrainGroup, model);
    }
    handles.alignmentRotation = 0;
    handles.navigationView = null;
    handles.terrainGroup.rotation.y = 0;
    handles.routeGroup.rotation.y = 0;

    if (model.route.length > 1) {
      const direction = model.route[model.route.length - 1].clone().sub(model.route[0]);
      handles.alignmentRotation = Math.atan2(direction.z, direction.x);
      handles.terrainGroup.rotation.y = handles.alignmentRotation;
      handles.routeGroup.rotation.y = handles.alignmentRotation;
    }

    const terrainRoute = sampleRouteOnTerrain(model);
    handles.model = model;
    handles.terrainRoute = terrainRoute;
    const markerRoute = terrainRoute.map((point) => {
      const next = point.clone();
      next.y += 0.025;
      return next;
    });

    if (terrainRoute.length > 1) {
      const trailOuterHalfWidth = current.navigationMode ? 0.042 : 0.135;
      const trailInnerHalfWidth = current.navigationMode ? 0.023 : 0.092;
      handles.routeGroup.add(
        makeTerrainTrailRibbon(
          terrainRoute,
          model,
          trailOuterHalfWidth,
          "#F0643B",
          0.052,
          true
        )
      );
      handles.routeGroup.add(
        makeTerrainTrailRibbon(
          terrainRoute,
          model,
          trailInnerHalfWidth,
          "#D4A56F",
          0.061,
          false
        )
      );
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
  }, []);

  useEffect(() => {
    rebuildScene();
  }, [geometrySignature, rebuildScene]);

  useEffect(() => {
    const handles = handlesRef.current;
    if (!handles) return;
    updateTrackedPosition(handles, userCoordinate, navigationMode);
  }, [userCoordinate, navigationMode]);

  useEffect(
    () => () => {
      const handles = handlesRef.current;
      if (!handles) return;

      cancelAnimationFrame(handles.animationFrame);
      clearGroup(handles.terrainGroup);
      clearGroup(handles.routeGroup);
      clearGroup(handles.weatherGroup);
      handles.renderer.dispose();
      handlesRef.current = null;
    },
    []
  );

  const updateCamera = useCallback((camera: THREE.PerspectiveCamera, navigationView?: NavigationView | null) => {
    const current = propsRef.current;
    const scale = clampTerrainScale(current.viewScale);
    const orbitAngle = current.viewOffset.x / 100;
    const tilt = clamp(current.viewOffset.y / 120, -1.65, 1.65);

    if (current.navigationMode && navigationView) {
      const anchor = navigationView.anchor.clone();
      const viewDirection = navigationView.direction
        .clone()
        .applyAxisAngle(new THREE.Vector3(0, 1, 0), orbitAngle);
      const sightDirection = navigationView.sightDirection
        .clone()
        .applyAxisAngle(new THREE.Vector3(0, 1, 0), orbitAngle);
      const eyeHeight = clamp(0.46 - tilt * 0.035, 0.4, 0.52);
      const cameraPosition = anchor
        .clone()
        .addScaledVector(viewDirection, -0.045)
        .add(new THREE.Vector3(0, eyeHeight, 0));
      const lookTarget = cameraPosition
        .clone()
        .addScaledVector(sightDirection, 3.2)
        .add(new THREE.Vector3(0, -0.1 - tilt * 0.28, 0));
      camera.fov = getTerrainPerspectiveFov(scale);
      camera.zoom = 1;
      camera.position.copy(cameraPosition);
      camera.lookAt(lookTarget);
      camera.updateProjectionMatrix();
      return;
    }

    const target = new THREE.Vector3(0, 0.58, 0);
    const radius = 8 + Math.max(0, tilt) * 0.28;
    const height = clamp(3.78 - tilt * 1.12, 1.65, 5.7);

    camera.fov = 43;
    camera.zoom = scale;
    camera.position.set(
      Math.sin(orbitAngle) * radius,
      height,
      Math.cos(orbitAngle) * radius
    );
    camera.lookAt(target);
    camera.updateProjectionMatrix();
  }, []);

  const onContextCreate = useCallback(
    (gl: ExpoWebGLRenderingContext) => {
      const width = gl.drawingBufferWidth || 1;
      const height = gl.drawingBufferHeight || 1;
      const renderer = new Renderer({
        gl,
        width,
        height,
        pixelRatio: 1,
        antialias: true,
        clearColor: "#DCEFF7",
      });
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.08;
      renderer.outputColorSpace = THREE.SRGBColorSpace;

      const scene = new THREE.Scene();
      scene.fog = new THREE.FogExp2("#CFE9F2", 0.035);

      const camera = new THREE.PerspectiveCamera(43, width / height, 0.1, 80);
      updateCamera(camera, null);

      const terrainGroup = new THREE.Group();
      const routeGroup = new THREE.Group();
      const weatherGroup = new THREE.Group();
      scene.add(weatherGroup);
      scene.add(terrainGroup);
      scene.add(routeGroup);

      const hemiLight = new THREE.HemisphereLight("#DDF6FF", "#335C36", 1.5);
      const sunLight = new THREE.DirectionalLight("#FFF3D9", 2.7);
      const fillLight = new THREE.DirectionalLight("#A9CBE8", 0.6);
      sunLight.position.set(-6, 6.5, 4.5);
      sunLight.castShadow = true;
      sunLight.shadow.mapSize.set(1024, 1024);
      sunLight.shadow.camera.left = -6;
      sunLight.shadow.camera.right = 6;
      sunLight.shadow.camera.top = 6;
      sunLight.shadow.camera.bottom = -6;
      sunLight.shadow.camera.near = 1;
      sunLight.shadow.camera.far = 18;
      sunLight.shadow.bias = -0.0025;
      sunLight.shadow.radius = 2;
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
        rebuildId: 0,
      };
      rebuildScene();

      const render = () => {
        const handles = handlesRef.current;
        if (!handles) return;

        updateCamera(handles.camera, handles.navigationView);
        const elapsed = Date.now() / 1000;
        handles.weatherGroup.children.forEach((child) => {
          if (child.name === "weather-cloud") {
            const originX = Number(child.userData.originX) || 0;
            const speed = Number(child.userData.speed) || 0.02;
            child.position.x = originX + Math.sin(elapsed * speed * 8 + originX) * 0.34;
          } else if (child.name === "weather-precipitation") {
            child.position.y = -((elapsed * 0.72) % 0.8);
          }
        });
        handles.renderer.render(handles.scene, handles.camera);
        handles.gl.endFrameEXP?.();
        handles.animationFrame = requestAnimationFrame(render);
      };

      render();
    },
    [rebuildScene, updateCamera]
  );

  return <GLView style={styles.canvas} onContextCreate={onContextCreate} />;
}

const styles = StyleSheet.create({
  canvas: {
    flex: 1,
  },
});
