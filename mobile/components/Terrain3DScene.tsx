import { GLView, ExpoWebGLRenderingContext } from "expo-gl";
import { Renderer, TextureLoader } from "expo-three";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { StyleSheet } from "react-native";
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
  coordinateToTerrainScenePoint,
  drapeRouteOnTerrain,
  getTerrainSceneHeight,
  getTerrainWeatherKind,
} from "./terrainSceneModel";

type Terrain3DSceneProps = {
  terrain: TerrainSceneModel;
  userCoordinate?: Coordinate | null;
  viewOffset: { x: number; y: number };
  viewScale: number;
  weather?: TerrainSceneWeather | null;
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
  model: TerrainSceneModel | null;
  terrainRoute: THREE.Vector3[];
  trackedObject: THREE.Object3D | null;
  rebuildId: number;
};

const DEFAULT_CAMERA_TARGET_Y = 0.58;
const CAMERA_GROUND_CLEARANCE = 0.8;

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
  const low = new THREE.Color("#5F7F5A");
  const middle = new THREE.Color("#A39676");
  const high = new THREE.Color("#D6D1C4");
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
    roughness: 0.88,
    metalness: 0.02,
    vertexColors: true,
  });
  const terrain = new THREE.Mesh(geometry, material);
  terrain.receiveShadow = true;

  return terrain;
};

const getSatelliteTextureUrl = (model: TerrainSceneModel) => {
  const { north, south, east, west } = model.grid.bounds;
  const params = new URLSearchParams({
    bbox: `${west},${south},${east},${north}`,
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
  model: TerrainSceneModel,
  onLoad: (texture: THREE.Texture) => void
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
    // Si la imagen falla, el relieve conserva el tinte por altura.
    () => undefined
  );
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

const getSmoothedCrossSlopes = (
  centerLine: THREE.Vector3[],
  model: TerrainSceneModel
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
    const leftHeight = getTerrainSceneHeight(
      model,
      point.x - normalX * sampleDistance,
      point.z - normalZ * sampleDistance
    );
    const rightHeight = getTerrainSceneHeight(
      model,
      point.x + normalX * sampleDistance,
      point.z + normalZ * sampleDistance
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
  const crossSlopes = getSmoothedCrossSlopes(centerLine, model);

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
        point.y + crossSlopes[index] * offset + lift,
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
  // Fuera de la grilla real no hay altura conocida: no se dibuja el marcador.
  const scenePoint = coordinateToTerrainScenePoint(model, userCoordinate);
  if (!scenePoint) return;
  const userPoint = toVector3(scenePoint);
  const markerGroup = new THREE.Group();
  markerGroup.add(makeUserMarker(userPoint), makeVerticalPin(userPoint, "#2376D9"));
  handles.routeGroup.add(markerGroup);
  handles.trackedObject = markerGroup;
};

const buildSkyDome = (kind: TerrainWeatherKind | null) => {
  const colorsByKind = {
    clear: ["#418BC1", "#D9EFF5"],
    "partly-cloudy": ["#648FAC", "#D8E5E9"],
    cloudy: ["#667681", "#C4CDD0"],
    rain: ["#405565", "#9BAAB1"],
    storm: ["#273743", "#73838B"],
    snow: ["#839BAA", "#E8F0F1"],
  } as const;
  // Sin pronostico real se usa un degradado neutro.
  const [topColor, bottomColor] = kind ? colorsByKind[kind] : ["#8EA4B2", "#E4EBEE"];
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

// Efectos solo para un pronostico real. Las posiciones siguen una grilla fija
// y se elevan sobre el punto mas alto del relieve.
const addWeatherGraphics = (
  group: THREE.Group,
  kind: TerrainWeatherKind | null,
  baseHeight: number
) => {
  if (!kind) return;
  const cloudKinds = ["partly-cloudy", "cloudy", "rain", "storm", "snow"];

  if (kind === "clear" || kind === "partly-cloudy") {
    const sun = new THREE.Mesh(
      new THREE.SphereGeometry(0.58, 24, 18),
      new THREE.MeshBasicMaterial({ color: "#FFD466", fog: false })
    );
    sun.position.set(-4.8, 5.9 + baseHeight, -5.8);
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
      const x = -5.8 + (index % 4) * 3.8;
      const y = 4.6 + Math.floor(index / 4) * 1.15 + baseHeight;
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
      cloud.userData.speed = 0.024;
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
    group.add(precipitation);
  }
};

export function Terrain3DScene({
  terrain,
  userCoordinate,
  viewOffset,
  viewScale,
  weather,
  navigationMode = false,
  satelliteTextureEnabled = true,
}: Terrain3DSceneProps) {
  const handlesRef = useRef<SceneHandles | null>(null);
  const propsRef = useRef({
    terrain,
    userCoordinate,
    viewOffset,
    viewScale,
    weather,
    navigationMode,
    satelliteTextureEnabled,
  });
  const geometrySignature = useMemo(
    () =>
      JSON.stringify({
        weather,
        navigationMode,
        satelliteTextureEnabled,
      }),
    [
      weather,
      navigationMode,
      satelliteTextureEnabled,
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
    };
  }, [
    terrain,
    userCoordinate,
    viewOffset,
    viewScale,
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
    const model = current.terrain;
    clearGroup(handles.terrainGroup);
    clearGroup(handles.routeGroup);
    clearGroup(handles.weatherGroup);
    handles.trackedObject = null;
    const weatherKind = getTerrainWeatherKind(current.weather);
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
    handles.weatherGroup.add(buildSkyDome(weatherKind));
    addWeatherGraphics(handles.weatherGroup, weatherKind, model.maxHeight);
    const terrain = buildTerrainMesh(model);
    handles.terrainGroup.add(terrain);
    if (current.satelliteTextureEnabled) {
      applySatelliteTexture(terrain, model, (texture) => {
        if (handlesRef.current !== handles || handles.rebuildId !== rebuildId) {
          texture.dispose();
        }
      });
    }
    handles.terrainGroup.add(buildTerrainSkirt(model));
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

    const terrainRoute = drapeRouteOnTerrain(model).map(toVector3);
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
  }, [terrain, geometrySignature, rebuildScene]);

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

  const updateCamera = useCallback((
    camera: THREE.PerspectiveCamera,
    navigationView?: NavigationView | null,
    alignmentRotation = 0
  ) => {
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

    // El relieve real puede ser mas alto que la vista por defecto: se eleva el
    // objetivo con el relieve y la camara nunca queda debajo del terreno.
    const model = current.terrain;
    const targetY = Math.max(DEFAULT_CAMERA_TARGET_Y, model.maxHeight * 0.4);
    const target = new THREE.Vector3(0, targetY, 0);
    const radius = 8 + Math.max(0, tilt) * 0.28;
    const height = clamp(3.78 - tilt * 1.12, 1.65, 5.7) + targetY - DEFAULT_CAMERA_TARGET_Y;
    const cameraX = Math.sin(orbitAngle) * radius;
    const cameraZ = Math.cos(orbitAngle) * radius;
    const groundY = getTerrainSceneHeight(
      model,
      cameraX * Math.cos(alignmentRotation) - cameraZ * Math.sin(alignmentRotation),
      cameraX * Math.sin(alignmentRotation) + cameraZ * Math.cos(alignmentRotation)
    );

    camera.fov = 43;
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

        updateCamera(handles.camera, handles.navigationView, handles.alignmentRotation);
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
