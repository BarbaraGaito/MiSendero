import * as THREE from "three";
import { updateTerrainCamera } from "../terrainCamera";
import { buildTerrainSceneModel, coordinateToTerrainScenePoint, getTerrainSceneHeight } from "../terrainSceneModel";
import type { TerrainElevationGrid } from "../../../services/terrainElevation";

const grid: TerrainElevationGrid = {
  size: 17, center: [0.5, 0.5], bounds: { north: 1, south: 0, west: 0, east: 1 },
  sideLengthMeters: 1440, cellSizeMeters: 90,
  elevationsMeters: Array.from({ length: 17 * 17 }, (_, index) =>
    100 + Math.sin(Math.floor(index / 17) / 16 * Math.PI) * 600 + index % 17 * 10),
  minElevationMeters: 100, maxElevationMeters: 860,
};
const model = buildTerrainSceneModel(grid, [[0.85, 0.15], [0.5, 0.5], [0.15, 0.85]])!;
const axis = new THREE.Vector3(0, 1, 0);
const base = { viewOffset: { x: 0, y: 0 }, viewScale: 1, navigationMode: true,
  alignmentRotation: 0, viewport: { width: 393, height: 852 }, topInset: 320, bottomInset: 260 };
const camera = () => new THREE.PerspectiveCamera(43, 393 / 852, 0.03, 1500);

test.each([0.4, 1, 1.9])("first-person camera stays over the trail and looks forward at zoom %s", scale => {
  for (const rotation of [0, Math.PI / 3, Math.PI / 2]) {
    for (const offset of [-180, 0, 180]) {
      const point = coordinateToTerrainScenePoint(model, [0.5, 0.5])!;
      const anchor = new THREE.Vector3(point.x, point.y, point.z).applyAxisAngle(axis, rotation);
      const routeDirection = new THREE.Vector3(1, 0, -1).normalize().applyAxisAngle(axis, rotation);
      const view = camera();
      updateTerrainCamera(view, model, { ...base, alignmentRotation: rotation, viewScale: scale,
        viewOffset: { x: offset, y: offset },
        navigationView: { anchor, direction: routeDirection } });
      view.updateMatrixWorld(true);
      const localCamera = view.position.clone().applyAxisAngle(axis, -rotation);
      const ground = getTerrainSceneHeight(model, localCamera.x, localCamera.z);
      expect(view.position.x).toBeCloseTo(anchor.x, 6);
      expect(view.position.z).toBeCloseTo(anchor.z, 6);
      expect((view.position.y - ground) * model.metersPerUnit).toBeGreaterThanOrEqual(3);
      expect((view.position.y - ground) * model.metersPerUnit).toBeLessThanOrEqual(6.01);
      const heading = view.getWorldDirection(new THREE.Vector3()).setY(0).normalize();
      expect(heading.dot(routeDirection.clone().applyAxisAngle(axis, offset / 100))).toBeGreaterThan(0.99);
      expect(view.view?.enabled).toBe(true);
    }
  }
});

test("first-person preview points the visible viewport at nearby ground", () => {
  const flat = buildTerrainSceneModel({ ...grid, elevationsMeters: Array(17 * 17).fill(100),
    minElevationMeters: 100, maxElevationMeters: 100 }, [[0.85, 0.15], [0.5, 0.5]])!;
  const anchor = new THREE.Vector3(flat.route[0].x, flat.route[0].y, flat.route[0].z);
  const view = camera();
  updateTerrainCamera(view, flat, { ...base, navigationView: {
    anchor, direction: new THREE.Vector3(1, 0, 1).normalize(),
  } });
  view.updateMatrixWorld(true);
  const ray = new THREE.Raycaster();
  ray.setFromCamera(new THREE.Vector2(0, 0), view);
  const forwardMeters = -view.position.y / ray.ray.direction.y * flat.metersPerUnit;
  expect(ray.ray.direction.y).toBeLessThan(0);
  expect(forwardMeters).toBeGreaterThan(2);
  expect(forwardMeters).toBeLessThan(500);
});

test("without a usable GPS pose the entire route fits the available navigation viewport", () => {
  const view = camera(), rotation = 0.7;
  updateTerrainCamera(view, model, { ...base, alignmentRotation: rotation, navigationView: null });
  view.updateMatrixWorld(true);
  for (const point of model.route) {
    const projected = new THREE.Vector3(point.x, point.y, point.z).applyAxisAngle(axis, rotation).project(view);
    const y = (1 - projected.y) * base.viewport.height / 2;
    expect(Math.abs(projected.x)).toBeLessThan(0.95);
    expect(y).toBeGreaterThan(base.topInset);
    expect(y).toBeLessThan(base.viewport.height - base.bottomInset);
  }
});

test("leaving navigation removes the reserved header/footer projection offset", () => {
  const view = camera();
  updateTerrainCamera(view, model, { ...base, navigationView: null });
  expect(view.view?.enabled).toBe(true);
  updateTerrainCamera(view, model, { ...base, navigationMode: false });
  expect(view.view?.enabled).toBe(false);
  expect(view.zoom).toBe(1);
});
