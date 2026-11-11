import * as THREE from "three";
import type { Coordinate } from "../../services/geoUtils";
import { clampTerrainScale, getTerrainPerspectiveFov } from "../../services/mapGestures";
import {
  coordinateToTerrainScenePoint, getTerrainSceneHeight,
  type TerrainSceneModel,
} from "./terrainSceneModel";

export type NavigationView = { anchor: THREE.Vector3; direction: THREE.Vector3 };

type TerrainCameraOptions = {
  viewOffset: { x: number; y: number };
  viewScale: number;
  navigationMode: boolean;
  navigationView?: NavigationView | null;
  alignmentRotation: number;
  focusCoordinate?: Coordinate | null;
  viewport: { width: number; height: number };
  topInset: number;
  bottomInset: number;
};

const Y_AXIS = new THREE.Vector3(0, 1, 0);
const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

const heightAtWorld = (model: TerrainSceneModel, x: number, z: number, rotation: number) =>
  getTerrainSceneHeight(model, x * Math.cos(rotation) - z * Math.sin(rotation),
    x * Math.sin(rotation) + z * Math.cos(rotation));

export function updateTerrainCamera(camera: THREE.PerspectiveCamera, model: TerrainSceneModel, options: TerrainCameraOptions) {
  const { navigationMode, navigationView, alignmentRotation } = options;
  const scale = clampTerrainScale(options.viewScale);
  const orbitAngle = options.viewOffset.x / 100;
  const tilt = clamp(options.viewOffset.y / 120, -1.65, 1.65);
  const focus = options.focusCoordinate ? coordinateToTerrainScenePoint(model, options.focusCoordinate) : null;
  const height = options.viewport.height || 480;
  const width = options.viewport.width || height * camera.aspect;
  const top = navigationMode ? clamp(options.topInset, 0, height * 0.7) : 0;
  const bottom = navigationMode ? clamp(options.bottomInset, 0, Math.max(0, height - top - 80)) : 0;
  const visibleFraction = (height - top - bottom) / height;

  if (navigationMode) {
    // Centre the ground in the space between the route controls and footer.
    camera.setViewOffset(width, height, 0, (bottom - top) / 2, width, height);
  } else {
    camera.clearViewOffset();
  }

  if (navigationMode && navigationView && !focus) {
    // Stay above the measured terrain at the GPS point (or the labelled trail
    // start preview). A small clearance keeps the coarse DEM from clipping
    // the lens while preserving a first-person perspective.
    const anchor = navigationView.anchor;
    const direction = navigationView.direction.clone().setY(0).applyAxisAngle(Y_AXIS, orbitAngle).normalize();
    const eyeMeters = clamp(model.grid.cellSizeMeters * 0.05, 3, 6);
    const lookMeters = clamp(model.grid.cellSizeMeters * 3, 160, 320);
    const lookDistance = lookMeters / model.metersPerUnit;
    const targetX = anchor.x + direction.x * lookDistance;
    const targetZ = anchor.z + direction.z * lookDistance;
    const groundAhead = heightAtWorld(model, targetX, targetZ, alignmentRotation);
    const eyeY = anchor.y + eyeMeters / model.metersPerUnit;
    const naturalTargetY = groundAhead + eyeMeters * 0.3 / model.metersPerUnit;
    // Look slightly toward the ground so the useful space beneath the route
    // controls shows the trail and imagery rather than mostly sky.
    const pitchRadians = (10 + tilt * 6) * Math.PI / 180;
    const pitchMeters = lookMeters * Math.tan(pitchRadians) / model.metersPerUnit;
    camera.fov = getTerrainPerspectiveFov(scale);
    camera.near = Math.max(0.0002, 0.2 / model.metersPerUnit);
    camera.zoom = 1;
    camera.position.set(anchor.x, eyeY, anchor.z);
    camera.lookAt(targetX, naturalTargetY - pitchMeters, targetZ);
    camera.updateProjectionMatrix();
    return;
  }

  // Route overview is still used when inspecting a focused point.
  const targetY = focus ? focus.y + 0.58 : Math.max(0.58, model.maxHeight * 0.4);
  const target = focus ? new THREE.Vector3(focus.x, targetY, focus.z).applyAxisAngle(Y_AXIS, alignmentRotation)
    : new THREE.Vector3(0, targetY, 0);
  const halfAngle = Math.min(Math.atan(Math.tan(43 * Math.PI / 360) * visibleFraction),
    Math.atan(Math.tan(43 * Math.PI / 360) * camera.aspect));
  const routeRadius = model.route.reduce((radius, point) =>
    Math.max(radius, Math.hypot(point.x, point.y - targetY, point.z)), 0);
  const distance = focus ? 8 / visibleFraction : Math.max(8, routeRadius / Math.sin(halfAngle) * 1.12);
  const pitch = clamp(0.55 - tilt * 0.2, 0.22, 1.05);
  const radius = distance * Math.cos(pitch);
  const x = target.x + Math.sin(orbitAngle) * radius;
  const z = target.z + Math.cos(orbitAngle) * radius;
  camera.fov = 43;
  camera.near = 0.03;
  camera.zoom = scale;
  camera.position.set(x, Math.max(targetY + distance * Math.sin(pitch),
    heightAtWorld(model, x, z, alignmentRotation) + 0.8), z);
  camera.lookAt(target);
  camera.updateProjectionMatrix();
}
