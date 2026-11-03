import * as THREE from "three";
import {
  TerrainSceneModel, TerrainScenePoint, buildTerrainMeshData, getTerrainSceneHeight,
} from "./terrainSceneModel";

export const niceTerrainDistance = (target: number) => {
  if (!Number.isFinite(target) || target <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(target));
  const amount = target / power;
  return (amount >= 5 ? 5 : amount >= 2 ? 2 : 1) * power;
};

export const getTerrainContourInterval = (model: TerrainSceneModel) =>
  Math.max(10, niceTerrainDistance((model.maxElevationMeters - model.minElevationMeters) / 8));

// Intersections are taken from the rendered DEM triangles, at their actual altitude.
export function buildTerrainContours(model: TerrainSceneModel) {
  const data = buildTerrainMeshData(model);
  const interval = getTerrainContourInterval(model);
  const positions: number[] = [];
  const vertex = (index: number) => new THREE.Vector3(...data.positions.slice(index * 3, index * 3 + 3) as [number, number, number]);
  for (let offset = 0; offset < data.indices.length; offset += 3) {
    const triangle = data.indices.slice(offset, offset + 3).map(vertex);
    const min = Math.min(...triangle.map(point => point.y * model.metersPerUnit + model.minElevationMeters));
    const max = Math.max(...triangle.map(point => point.y * model.metersPerUnit + model.minElevationMeters));
    for (let elevation = Math.ceil(min / interval) * interval; elevation < max; elevation += interval) {
      const height = (elevation - model.minElevationMeters) / model.metersPerUnit;
      const hits: THREE.Vector3[] = [];
      triangle.forEach((start, index) => {
        const end = triangle[(index + 1) % 3];
        if ((start.y <= height && end.y > height) || (end.y <= height && start.y > height)) {
          hits.push(start.clone().lerp(end, (height - start.y) / (end.y - start.y)));
        }
      });
      if (hits.length === 2) hits.forEach(point => positions.push(point.x, point.y + 0.008, point.z));
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  const lines = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({
    color: "#443E32", transparent: true, opacity: 0.32, depthWrite: false,
  }));
  lines.name = "terrain-contours";
  return lines;
}

export type TerrainRouteStation = { point: TerrainScenePoint; label: string; elevationMeters: number };

export function getTerrainRouteStations(model: TerrainSceneModel): TerrainRouteStation[] {
  const total = model.routeDistancesMeters.at(-1) ?? 0;
  const stations: TerrainRouteStation[] = [];
  const spacing = Math.max(250, niceTerrainDistance(total / 6));
  const at = (distance: number, label: string) => {
    const index = Math.max(1, model.routeDistancesMeters.findIndex(value => value >= distance));
    const previous = model.route[index - 1], next = model.route[index];
    if (!previous || !next) return;
    const length = model.routeDistancesMeters[index] - model.routeDistancesMeters[index - 1];
    const ratio = length > 0 ? (distance - model.routeDistancesMeters[index - 1]) / length : 0;
    const x = previous.x + (next.x - previous.x) * ratio;
    const z = previous.z + (next.z - previous.z) * ratio;
    const y = getTerrainSceneHeight(model, x, z);
    stations.push({ point: { x, y, z }, label, elevationMeters: Math.round(model.minElevationMeters + y * model.metersPerUnit) });
  };
  at(0, "Inicio");
  for (let distance = spacing; distance < total - spacing * 0.25 && stations.length < 9; distance += spacing) {
    at(distance, distance >= 1000 ? `${Number((distance / 1000).toFixed(1))} km` : `${Math.round(distance)} m`);
  }
  at(total, "Llegada");
  return stations;
}

export function buildTerrainRouteArrows(model: TerrainSceneModel, route: THREE.Vector3[]) {
  const positions: number[] = [];
  let accumulated = 0;
  const spacing = Math.max(0.45, (model.routeDistancesMeters.at(-1) ?? 0) / model.metersPerUnit / 20);
  route.forEach((point, index) => {
    if (index === 0) return;
    const previous = route[index - 1];
    accumulated += Math.hypot(point.x - previous.x, point.z - previous.z);
    if (accumulated < spacing) return;
    accumulated = 0;
    const direction = point.clone().sub(previous); direction.y = 0; direction.normalize();
    const normal = new THREE.Vector3(-direction.z, 0, direction.x);
    const tip = point.clone().addScaledVector(direction, 0.07);
    [-1, 1].forEach(side => {
      const tail = point.clone().addScaledVector(direction, -0.05).addScaledVector(normal, 0.055 * side);
      [tail, tip].forEach(vertex => positions.push(vertex.x, getTerrainSceneHeight(model, vertex.x, vertex.z) + 0.023, vertex.z));
    });
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  const arrows = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ color: "#FFFFFF" }));
  arrows.name = "route-direction-arrows";
  return arrows;
}

export type TerrainViewReadout = { scaleMeters: number; scaleFraction: number; northDegrees: number };

// The scale is measured on the ground at the view centre, rather than inferred
// from a zoom number. Its screen width therefore changes with camera tilt.
export function getTerrainViewReadout(camera: THREE.PerspectiveCamera, ground: THREE.Mesh, metersPerUnit: number, rotation: number): TerrainViewReadout | null {
  camera.updateMatrixWorld(true); ground.updateWorldMatrix(true, false);
  const ray = new THREE.Raycaster();
  const at = (x: number) => {
    ray.setFromCamera(new THREE.Vector2(x, -0.25), camera);
    return ray.intersectObject(ground, false)[0]?.point;
  };
  const left = at(-0.1), right = at(0.1);
  if (!left || !right) return null;
  const distance = Math.hypot(right.x - left.x, right.z - left.z) * metersPerUnit;
  if (!Number.isFinite(distance) || distance <= 0) return null;
  const scaleMeters = niceTerrainDistance(distance * 2);
  const north = new THREE.Vector3(-Math.sin(rotation), 0, -Math.cos(rotation));
  const originScreen = left.clone().project(camera);
  const northScreen = left.clone().add(north).project(camera);
  return { scaleMeters, scaleFraction: scaleMeters / distance * 0.1,
    northDegrees: Math.atan2(northScreen.x - originScreen.x, northScreen.y - originScreen.y) * 180 / Math.PI };
}

export function makeCloudTexture() {
  const size = 64;
  const pixels = new Uint8Array(size * size * 4);
  const lobes = [[0.28, 0.58, 0.2, 0.2], [0.5, 0.42, 0.23, 0.26], [0.74, 0.58, 0.2, 0.19], [0.5, 0.63, 0.32, 0.17]];
  for (let y = 0; y < size; y += 1) for (let x = 0; x < size; x += 1) {
    const density = Math.max(...lobes.map(([cx, cy, sx, sy]) => Math.exp(-2 * (((x / size - cx) / sx) ** 2 + ((y / size - cy) / sy) ** 2))));
    const offset = (y * size + x) * 4;
    pixels.set([255, 255, 255, Math.round(Math.max(0, density - 0.03) * 230)], offset);
  }
  const texture = new THREE.DataTexture(pixels, size, size);
  texture.magFilter = THREE.LinearFilter;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.generateMipmaps = true;
  texture.needsUpdate = true;
  return texture;
}

export const getReportedGroundKind = (summary: string) => {
  const normalized = summary.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  if (/nieve|hielo/.test(normalized)) return { label: "Nieve o hielo", color: "#B6DDEB" };
  if (/barro/.test(normalized)) return { label: "Barro", color: "#88552F" };
  if (/agua alta/.test(normalized)) return { label: "Agua alta", color: "#218BAC" };
  if (/rocas|derrumbe/.test(normalized)) return { label: "Rocas o derrumbe", color: "#6D6270" };
  return null;
};
