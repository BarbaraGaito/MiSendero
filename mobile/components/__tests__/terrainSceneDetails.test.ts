import * as THREE from "three";
import { buildTerrainSceneModel, buildTerrainMeshData } from "../terrainSceneModel";
import { buildTerrainContours, getTerrainRouteStations, getTerrainViewReadout, niceTerrainDistance, getReportedGroundKind } from "../terrainSceneDetails";
const grid = { size: 3, center: [0.5, 0.5] as [number, number], bounds: { north: 1, south: 0, west: 0, east: 1 },
  sideLengthMeters: 1440, cellSizeMeters: 720, elevationsMeters: [100,110,120,130,140,150,160,170,180], minElevationMeters: 100, maxElevationMeters: 180 };
const terrain = buildTerrainSceneModel(grid, [[1, 0], [0, 1]])!;
test("contours follow actual altitude levels on the same DEM triangles", () => {
  const contours = buildTerrainContours(terrain);
  const vertices = contours.geometry.getAttribute("position");
  expect(vertices.count).toBeGreaterThan(0);
  for (let index = 0; index < vertices.count; index += 2) {
    expect(vertices.getY(index)).toBeCloseTo(vertices.getY(index + 1), 6);
    const elevation = (vertices.getY(index) - 0.008) * terrain.metersPerUnit + terrain.minElevationMeters;
    expect(elevation / 10).toBeCloseTo(Math.round(elevation / 10), 4);
    expect(Math.abs(vertices.getX(index))).toBeLessThanOrEqual(7.20001);
    expect(Math.abs(vertices.getZ(index))).toBeLessThanOrEqual(7.20001);
  }
});
test("route stations retain actual route distances, endpoints and DEM elevations", () => {
  const stations = getTerrainRouteStations(terrain);
  expect(stations[0].label).toBe("Inicio"); expect(stations.at(-1)!.label).toBe("Llegada");
  expect(stations[0].point).toEqual(terrain.route[0]);
  expect(stations.at(-1)!.point).toEqual(terrain.route.at(-1));
  expect(stations[0].elevationMeters).toBe(100); expect(stations.at(-1)!.elevationMeters).toBe(180);
  expect(stations.length).toBeLessThanOrEqual(11);
});
test("the scale bar measures metres in the camera's actual ground footprint and responds to zoom", () => {
  const data = buildTerrainMeshData(terrain);
  const geometry = new THREE.BufferGeometry(); geometry.setIndex(data.indices);
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(data.positions, 3));
  const ground = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
  const camera = new THREE.PerspectiveCamera(43, 0.67, 0.03, 100);
  camera.position.set(0, 8, 8); camera.lookAt(0, 0.4, 0); camera.updateProjectionMatrix();
  const normal = getTerrainViewReadout(camera, ground, 100, 0)!;
  expect(normal.scaleFraction).toBeGreaterThan(0); expect(normal.scaleFraction).toBeLessThanOrEqual(0.2);
  expect(Math.abs(normal.northDegrees)).toBeLessThan(10);
  camera.zoom = 2; camera.updateProjectionMatrix();
  const zoomed = getTerrainViewReadout(camera, ground, 100, 0)!;
  expect(zoomed.scaleMeters).toBeLessThan(normal.scaleMeters);
  camera.lookAt(0, 100, -10);
  expect(getTerrainViewReadout(camera, ground, 100, 0)).toBeNull();
});
test("larger source grids add real samples while bounding the mobile render mesh", () => {
  const model = buildTerrainSceneModel({ ...grid, size: 33, cellSizeMeters: 45,
    elevationsMeters: Array.from({ length: 33 ** 2 }, (_, index) => 100 + Math.floor(index / 33)) }, [[1, 0], [0, 1]])!;
  expect(buildTerrainMeshData(model).verticesPerSide).toBeLessThanOrEqual(65);
  expect(buildTerrainMeshData(model).positions.length).toBeLessThanOrEqual(65 ** 2 * 3);
});
test("soil styles come from reported incidents, with no inferred mud from a forecast", () => {
  expect(getReportedGroundKind("Barro, Rocas sueltas")?.label).toBe("Barro");
  expect(getReportedGroundKind("Nieve o hielo")?.label).toBe("Nieve o hielo");
  expect(getReportedGroundKind("Agua alta")?.label).toBe("Agua alta");
  expect(getReportedGroundKind("Lluvia")).toBeNull();
  expect(niceTerrainDistance(480)).toBe(200);
});
