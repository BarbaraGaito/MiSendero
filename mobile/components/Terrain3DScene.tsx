import { GLView, ExpoWebGLRenderingContext } from "expo-gl";
import { Renderer } from "expo-three";
import React, { useCallback, useEffect, useMemo, useRef } from "react";
import { StyleSheet } from "react-native";
import * as THREE from "three";
import { Coordinate } from "../../services/geoUtils";

type Terrain3DSceneProps = {
  routePoints: Coordinate[];
  fallbackCenter: Coordinate;
  difficulty?: string | null;
  distanceKm?: number | null;
  userCoordinate?: Coordinate | null;
  viewOffset: { x: number; y: number };
  viewScale: number;
};

type SceneHandles = {
  animationFrame: number;
  camera: THREE.PerspectiveCamera;
  gl: ExpoWebGLRenderingContext;
  renderer: Renderer;
  routeGroup: THREE.Group;
  scene: THREE.Scene;
  terrainGroup: THREE.Group;
};

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
};

const GRID_SIZE = 68;
const EARTH_RADIUS_METERS = 6371000;

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
  difficulty?: string | null
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

  return (
    0.08 +
    (longRidge + crossRidge + peakA + peakB - basin + detailNoise + fineNoise) *
      (0.45 + difficultyFactor * 0.34)
  );
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
  steepness: number
) => {
  const valley = new THREE.Color("#4FA56F");
  const grass = new THREE.Color("#85C778");
  const scree = new THREE.Color("#B1C77A");
  const rock = new THREE.Color("#9C8E67");
  const snow = new THREE.Color("#EAF3DD");
  const normalized = clamp(height / (1.45 + difficultyFactor), 0, 1);
  let base: THREE.Color;

  if (normalized < 0.36) {
    base = interpolateColor(valley, grass, normalized / 0.36);
  } else if (normalized < 0.68) {
    base = interpolateColor(grass, scree, (normalized - 0.36) / 0.32);
  } else if (normalized < 0.9) {
    base = interpolateColor(scree, rock, (normalized - 0.68) / 0.22);
  } else {
    base = interpolateColor(rock, snow, (normalized - 0.9) / 0.1);
  }

  const rockExposure = clamp((steepness - 0.22) * 1.9, 0, 0.82);

  return interpolateColor(base, rock, rockExposure);
};

const disposeObject = (object: THREE.Object3D) => {
  object.traverse((child) => {
    const mesh = child as THREE.Mesh;
    const material = mesh.material as THREE.Material | THREE.Material[] | undefined;

    mesh.geometry?.dispose();
    if (Array.isArray(material)) {
      material.forEach((entry) => entry.dispose());
    } else {
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
  const indices: number[] = [];
  const color = new THREE.Color();

  for (let row = 0; row <= GRID_SIZE; row += 1) {
    for (let column = 0; column <= GRID_SIZE; column += 1) {
      const x = -4.2 + (column / GRID_SIZE) * 8.4;
      const z = -4.2 + (row / GRID_SIZE) * 8.4;
      const height = getHeightAt(
        x,
        z,
        model.difficultyFactor,
        model.seed
      );
      const steepness = getSlopeAt(x, z, model.difficultyFactor, model.seed);
      color.copy(getTerrainColor(height, model.difficultyFactor, steepness));

      positions.push(x, height, z);
      colors.push(color.r, color.g, color.b);
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
  const curve = new THREE.CatmullRomCurve3(points);
  const geometry = new THREE.TubeGeometry(
    curve,
    Math.max(24, points.length * 10),
    radius,
    8,
    false
  );
  const material = new THREE.MeshStandardMaterial({
    color,
    opacity,
    transparent: opacity < 1,
    roughness: 0.62,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.castShadow = true;

  return mesh;
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

const addContourLines = (group: THREE.Group, model: TerrainModel) => {
  for (let index = 0; index < 12; index += 1) {
    const z = -4 + index * 0.72;
    const points: THREE.Vector3[] = [];

    for (let step = 0; step <= 72; step += 1) {
      const x = -4.1 + (step / 72) * 8.2;
      const height = getHeightAt(x, z, model.difficultyFactor, model.seed);
      points.push(new THREE.Vector3(x, height + 0.012, z));
    }

    group.add(
      new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(points),
        new THREE.LineBasicMaterial({
          color: "#FFFFFF",
          opacity: 0.23,
          transparent: true,
        })
      )
    );
  }
};

const TREE_COUNT = 110;
const TRUNK_HEIGHT = 0.09;
const FOLIAGE_HEIGHT = 0.17;

const addVegetation = (group: THREE.Group, model: TerrainModel) => {
  const trunkGeometry = new THREE.CylinderGeometry(0.014, 0.02, TRUNK_HEIGHT, 5);
  const trunkMaterial = new THREE.MeshStandardMaterial({
    color: "#6B4A31",
    roughness: 0.92,
  });
  const foliageGeometry = new THREE.ConeGeometry(0.06, FOLIAGE_HEIGHT, 6);
  const foliageMaterial = new THREE.MeshStandardMaterial({
    color: "#3D7A45",
    roughness: 0.85,
  });
  const trunks = new THREE.InstancedMesh(trunkGeometry, trunkMaterial, TREE_COUNT);
  const foliage = new THREE.InstancedMesh(foliageGeometry, foliageMaterial, TREE_COUNT);
  trunks.castShadow = true;
  trunks.receiveShadow = true;
  foliage.castShadow = true;
  foliage.receiveShadow = true;

  const dummy = new THREE.Object3D();
  let placed = 0;
  let attempt = 0;

  while (placed < TREE_COUNT && attempt < TREE_COUNT * 8) {
    attempt += 1;
    const rx = hash01(attempt * 3.11, model.seed, model.seed + 1) * 8.2 - 4.1;
    const rz = hash01(model.seed, attempt * 5.73, model.seed + 2) * 8.2 - 4.1;
    const height = getHeightAt(rx, rz, model.difficultyFactor, model.seed);
    const steepness = getSlopeAt(rx, rz, model.difficultyFactor, model.seed);
    const normalizedHeight = clamp(
      height / (1.45 + model.difficultyFactor),
      0,
      1
    );

    if (steepness > 0.32 || normalizedHeight < 0.06 || normalizedHeight > 0.6) {
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

    placed += 1;
  }

  trunks.count = placed;
  foliage.count = placed;
  trunks.instanceMatrix.needsUpdate = true;
  foliage.instanceMatrix.needsUpdate = true;

  group.add(trunks);
  group.add(foliage);
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

const buildSkyDome = () => {
  const geometry = new THREE.SphereGeometry(60, 24, 16);
  const material = new THREE.ShaderMaterial({
    uniforms: {
      topColor: { value: new THREE.Color("#3F92D2") },
      bottomColor: { value: new THREE.Color("#DCEFF7") },
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

export function Terrain3DScene({
  routePoints,
  fallbackCenter,
  difficulty,
  distanceKm,
  userCoordinate,
  viewOffset,
  viewScale,
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
  });
  const geometrySignature = useMemo(
    () =>
      JSON.stringify({
        routePoints,
        fallbackCenter,
        difficulty,
        distanceKm,
        userCoordinate,
      }),
    [routePoints, fallbackCenter, difficulty, distanceKm, userCoordinate]
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
    };
  }, [
    routePoints,
    fallbackCenter,
    difficulty,
    distanceKm,
    userCoordinate,
    viewOffset,
    viewScale,
  ]);

  const rebuildScene = useCallback(() => {
    const handles = handlesRef.current;
    if (!handles) return;

    const current = propsRef.current;
    const model = buildTerrainModel(
      current.routePoints,
      current.fallbackCenter,
      current.difficulty
    );
    clearGroup(handles.terrainGroup);
    clearGroup(handles.routeGroup);
    handles.terrainGroup.add(buildTerrainMesh(model));
    addContourLines(handles.terrainGroup, model);
    addVegetation(handles.terrainGroup, model);

    const liftedRoute = model.route.map((point) => {
      const next = point.clone();
      next.y += 0.12;
      return next;
    });

    if (liftedRoute.length > 1) {
      handles.routeGroup.add(makeTube(liftedRoute, 0.085, "#FFFFFF", 0.98));
      handles.routeGroup.add(makeTube(liftedRoute, 0.048, "#EF3B3B"));
    }

    if (liftedRoute[0]) {
      handles.routeGroup.add(makeMarker(liftedRoute[0], "#008955"));
    }

    if (liftedRoute.length > 1) {
      handles.routeGroup.add(makeMarker(liftedRoute[liftedRoute.length - 1], "#EF3B3B"));
    }

    if (current.userCoordinate) {
      const userPoint = toScenePoint(current.userCoordinate, model);
      handles.routeGroup.add(makeMarker(userPoint, "#2376D9"));
      handles.routeGroup.add(makeVerticalPin(userPoint, "#2376D9"));
    }
  }, []);

  useEffect(() => {
    rebuildScene();
  }, [geometrySignature, rebuildScene]);

  useEffect(
    () => () => {
      const handles = handlesRef.current;
      if (!handles) return;

      cancelAnimationFrame(handles.animationFrame);
      clearGroup(handles.terrainGroup);
      clearGroup(handles.routeGroup);
      handles.renderer.dispose();
      handlesRef.current = null;
    },
    []
  );

  const updateCamera = useCallback((camera: THREE.PerspectiveCamera) => {
    const current = propsRef.current;
    const scale = clamp(current.viewScale, 0.72, 1.95);
    const offsetX = clamp(current.viewOffset.x / 110, -3.2, 3.2);
    const offsetY = clamp(current.viewOffset.y / 120, -2.8, 2.8);
    const target = new THREE.Vector3(-offsetX * 0.62, 0.42, offsetY * 0.55);

    camera.zoom = scale;
    camera.position.set(
      -offsetX * 0.95,
      5.25 - scale * 0.62,
      6.95 + offsetY * 0.78
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

      const scene = new THREE.Scene();
      scene.fog = new THREE.Fog("#CFE9F2", 9, 17);
      scene.add(buildSkyDome());

      const camera = new THREE.PerspectiveCamera(48, width / height, 0.1, 80);
      updateCamera(camera);

      const terrainGroup = new THREE.Group();
      const routeGroup = new THREE.Group();
      scene.add(terrainGroup);
      scene.add(routeGroup);

      const hemiLight = new THREE.HemisphereLight("#DDF6FF", "#335C36", 1.5);
      const sunLight = new THREE.DirectionalLight("#FFF3D9", 2.7);
      const fillLight = new THREE.DirectionalLight("#A9CBE8", 0.6);
      sunLight.position.set(-4, 7, 5);
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
        animationFrame: 0,
        camera,
        gl,
        renderer,
        routeGroup,
        scene,
        terrainGroup,
      };
      rebuildScene();

      const render = () => {
        const handles = handlesRef.current;
        if (!handles) return;

        updateCamera(handles.camera);
        const drift = Math.sin(Date.now() / 4200) * 0.012;
        handles.terrainGroup.rotation.y = drift;
        handles.routeGroup.rotation.y = drift;
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
