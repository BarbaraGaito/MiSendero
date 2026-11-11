jest.mock("expo-gl", () => ({ GLView: "GLView" }));
jest.mock("../terrainGraphics", () => ({
  createTerrainRenderer: jest.fn().mockImplementation(() => ({ shadowMap: {}, render: jest.fn(), setClearColor: jest.fn(), dispose: jest.fn() })),
  loadTerrainTexture: jest.fn(() => new Promise(() => {})),
}));
import React from "react";
import * as THREE from "three";
import { createTerrainRenderer, loadTerrainTexture } from "../terrainGraphics";
import { Terrain3DScene, Terrain3DSceneHandle } from "../Terrain3DScene";
import { buildTerrainSceneModel, coordinateToTerrainScenePoint } from "../terrainSceneModel";
const renderer = require("react-test-renderer");
const grid = { size: 3, center: [0.5, 0.5], bounds: { north: 1, south: 0, west: 0, east: 1 }, sideLengthMeters: 1440, cellSizeMeters: 720, elevationsMeters: [100, 110, 120, 130, 140, 150, 160, 170, 180], minElevationMeters: 100, maxElevationMeters: 180 };
const terrain = buildTerrainSceneModel(grid as never, [[1, 0], [0, 1]])!;
let screen: any, frame: FrameRequestCallback | undefined;
beforeEach(() => {
  jest.clearAllMocks(); frame = undefined;
  jest.spyOn(global, "requestAnimationFrame").mockImplementation((callback) => { frame = callback; return 42; });
  jest.spyOn(global, "cancelAnimationFrame").mockImplementation(() => {});
});
afterEach(async () => { if (screen) await renderer.act(async () => screen.unmount()); screen = null; jest.restoreAllMocks(); });
const mount = async (extra = {}) => {
  await renderer.act(async () => { screen = renderer.create(<Terrain3DScene terrain={terrain} viewOffset={{ x: 0, y: 0 }} viewScale={1} satelliteTextureEnabled={false} {...extra} />); });
  const gl = { drawingBufferWidth: 320, drawingBufferHeight: 480, endFrameEXP: jest.fn() };
  await renderer.act(async () => screen.root.findByType("GLView").props.onContextCreate(gl));
  return { gl, gpu: (createTerrainRenderer as jest.Mock).mock.results.at(-1)!.value };
};
test("builds actual Three geometries from the DEM, frames them above ground, and disposes resources", async () => {
  const { gpu, gl } = await mount({ userCoordinate: [0.5, 0.5] });
  const [scene, camera] = gpu.render.mock.calls.at(-1);
  expect(scene).toBeInstanceOf(THREE.Scene);
  const groups = scene.children.filter((child: THREE.Object3D) => child instanceof THREE.Group);
  const ground = groups[1].children[0];
  expect(ground.geometry.getAttribute("position").count).toBe(81);
  expect(ground.geometry.index.count).toBe(384);
  expect(camera.position.y).toBeGreaterThan(terrain.maxHeight);
  expect(groups[2].children.length).toBeGreaterThanOrEqual(5); // route, endpoints and measured user marker
  expect(gl.endFrameEXP).toHaveBeenCalled();
  const disposed = jest.spyOn(ground.geometry, "dispose");
  await renderer.act(async () => screen.unmount()); screen = null;
  expect(disposed).toHaveBeenCalledTimes(1); expect(gpu.dispose).toHaveBeenCalledTimes(1);
  expect(cancelAnimationFrame).toHaveBeenCalledWith(42);
});
test.each(["Despejado", "Parcialmente con nubes", "Nublado", "Lluvia", "Tormenta", "Nieve"])("weather graphics follow the supplied forecast: %s", async (condition) => {
  const { gpu } = await mount({ weather: { condition, rainProbability: 0, temperatureC: 5 }, navigationMode: true });
  await renderer.act(async () => frame?.(100));
  const [scene, camera] = gpu.render.mock.calls.at(-1);
  const weather = scene.children[0];
  const precipitation = weather.children.find((child: THREE.Object3D) => child.name === "weather-precipitation");
  expect(!!precipitation).toBe(["Lluvia", "Tormenta", "Nieve"].includes(condition));
  if (precipitation) expect(precipitation.count).toBe(condition === "Tormenta" ? 150 : 95);
  expect(camera.zoom).toBe(1); expect(camera.fov).toBeGreaterThan(0);
  expect(gpu.render).toHaveBeenCalledTimes(2);
});
test("a changed model rebuilds geometries; an outside-grid user receives no invented height", async () => {
  const { gpu } = await mount({ userCoordinate: [0.5, 0.5] });
  const scene = gpu.render.mock.calls[0][0], group = scene.children[2];
  expect(group.getObjectByName("user-gps-marker")).toBeDefined();
  await renderer.act(async () => screen.update(<Terrain3DScene terrain={terrain} viewOffset={{ x: 20, y: 200 }} viewScale={2} satelliteTextureEnabled={false} userCoordinate={[5, 5]} />));
  expect(group.getObjectByName("user-gps-marker")).toBeUndefined();
  await renderer.act(async () => frame?.(100));
  expect(gpu.render.mock.calls.at(-1)[1].zoom).toBe(1.9); // public maximum zoom
});
test("late satellite images are disposed after scene replacement", async () => {
  let accept!: (texture: THREE.Texture) => void;
  (loadTerrainTexture as jest.Mock).mockReturnValueOnce(new Promise(resolve => { accept = resolve; }));
  const { gpu } = await mount({ satelliteTextureEnabled: true });
  const [url] = (loadTerrainTexture as jest.Mock).mock.calls[0];
  expect(url).toContain("bbox=0%2C0%2C1%2C1");
  const texture = new THREE.Texture(); const disposed = jest.spyOn(texture, "dispose");
  await renderer.act(async () => screen.update(<Terrain3DScene terrain={terrain} viewOffset={{ x: 0, y: 0 }} viewScale={1} satelliteTextureEnabled={false} />));
  expect(JSON.stringify(screen.toJSON())).not.toContain("Cargando imagen del terreno");
  await renderer.act(async () => { accept(texture); });
  expect(disposed).toHaveBeenCalledTimes(1);
  expect(gpu.render.mock.calls[0][0].children[1].children).toHaveLength(2);
});

test("covers the untextured ground until the satellite image has actually been rendered", async () => {
  let accept!: (texture: THREE.Texture) => void;
  (loadTerrainTexture as jest.Mock).mockReturnValueOnce(new Promise(resolve => { accept = resolve; }));
  const { gpu } = await mount({ satelliteTextureEnabled: true });
  expect(JSON.stringify(screen.toJSON())).toContain("Cargando imagen del terreno");
  const texture = new THREE.Texture();
  await renderer.act(async () => { accept(texture); });
  // Downloading is not enough: wait for the first frame with its texture.
  expect(JSON.stringify(screen.toJSON())).toContain("Cargando imagen del terreno");
  await renderer.act(async () => frame?.(100));
  expect(JSON.stringify(screen.toJSON())).not.toContain("Cargando imagen del terreno");
  expect(gpu.render.mock.calls.at(-1)[0].children[1].children[0].material.map).toBe(texture);
  expect(gpu.render.mock.calls.at(-1)[0].children[1].children[0].material).toBeInstanceOf(THREE.MeshBasicMaterial);
  expect(gpu.render.mock.calls.at(-1)[0].children[1].children[0].castShadow).toBe(false);
});

test("an image download error dismisses the loader and keeps the actual DEM usable", async () => {
  (loadTerrainTexture as jest.Mock).mockRejectedValueOnce(new Error("image unavailable"));
  const onError = jest.fn();
  const { gpu } = await mount({ satelliteTextureEnabled: true, informationVisible: true, onError });
  const text = JSON.stringify(screen.toJSON());
  expect(text).not.toContain("Cargando imagen del terreno");
  expect(text).toContain("Imagen satelital no disponible");
  expect(text).toContain("Color por altitud");
  expect(gpu.render.mock.calls.at(-1)[0].children[1].children[0].geometry.getAttribute("position").count).toBe(81);
  expect(onError).not.toHaveBeenCalled();
});

test("a stalled image stops loading after the deadline and its late texture is discarded", async () => {
  jest.useFakeTimers({ doNotFake: ["requestAnimationFrame", "cancelAnimationFrame"] });
  try {
    let accept!: (texture: THREE.Texture) => void;
    (loadTerrainTexture as jest.Mock).mockReturnValueOnce(new Promise(resolve => { accept = resolve; }));
    await mount({ satelliteTextureEnabled: true });
    expect(JSON.stringify(screen.toJSON())).toContain("Cargando imagen del terreno");
    await renderer.act(async () => { await jest.advanceTimersByTimeAsync(20000); });
    expect(JSON.stringify(screen.toJSON())).not.toContain("Cargando imagen del terreno");
    const texture = new THREE.Texture(), disposed = jest.spyOn(texture, "dispose");
    await renderer.act(async () => { accept(texture); });
    expect(disposed).toHaveBeenCalledTimes(1);
  } finally { jest.useRealTimers(); }
});

test("a previous route's image failure cannot dismiss the current route's loader", async () => {
  let rejectOld!: (reason: Error) => void, acceptNew!: (texture: THREE.Texture) => void;
  (loadTerrainTexture as jest.Mock)
    .mockReturnValueOnce(new Promise((_resolve, reject) => { rejectOld = reject; }))
    .mockReturnValueOnce(new Promise(resolve => { acceptNew = resolve; }));
  await mount({ satelliteTextureEnabled: true });
  const changed = buildTerrainSceneModel(terrain.grid, [[1, 0], [0.1, 0.9]])!;
  await renderer.act(async () => screen.update(<Terrain3DScene terrain={changed} viewOffset={{ x: 0, y: 0 }}
    viewScale={1} satelliteTextureEnabled />));
  await renderer.act(async () => { rejectOld(new Error("old request failed")); });
  expect(JSON.stringify(screen.toJSON())).toContain("Cargando imagen del terreno");
  await renderer.act(async () => { acceptNew(new THREE.Texture()); });
  await renderer.act(async () => frame?.(100));
  expect(JSON.stringify(screen.toJSON())).not.toContain("Cargando imagen del terreno");
});

test("a native renderer failure returns control to the 2D viewer", async () => {
  const error = new Error("GL unavailable"), onError = jest.fn();
  (createTerrainRenderer as jest.Mock).mockImplementationOnce(() => { throw error; });
  await mount({onError});
  expect(onError).toHaveBeenCalledWith(error);
});

test("3D picking returns geographic coordinates after rotation and zoom, and never selects the sky", async () => {
  const ref = React.createRef<Terrain3DSceneHandle>();
  const { gpu } = await mount({ ref });
  await renderer.act(async () => screen.update(<Terrain3DScene ref={ref} terrain={terrain}
    viewOffset={{ x: 80, y: -35 }} viewScale={1.4} satelliteTextureEnabled={false} />));
  await renderer.act(async () => frame?.(100));
  const [scene, camera] = gpu.render.mock.calls.at(-1);
  scene.updateMatrixWorld(true); camera.updateMatrixWorld(true);
  const local = coordinateToTerrainScenePoint(terrain, [0.55, 0.6])!;
  const projected = new THREE.Vector3(local.x, local.y, local.z).applyMatrix4(scene.children[1].matrixWorld).project(camera);
  const hit = ref.current!.pick(projected.x, projected.y)!;
  expect(hit.coordinate![0]).toBeCloseTo(0.55, 5);
  expect(hit.coordinate![1]).toBeCloseTo(0.6, 5);
  expect(ref.current!.pick(0, 100)).toBeNull();
});

test("warning pins sit on their geographic location and can be inspected without rebuilding the DEM", async () => {
  const ref = React.createRef<Terrain3DSceneHandle>();
  const markers = [{ id: "17", coordinate: [0.5, 0.5] as [number, number], color: "#BD332B", precisionMeters: 150 }];
  const { gpu } = await mount({ ref, markers });
  const [scene, camera] = gpu.render.mock.calls.at(-1);
  scene.updateMatrixWorld(true); camera.updateMatrixWorld(true);
  const head = scene.children[3].children[0].getObjectByName("map-marker-head");
  const screenPoint = head.getWorldPosition(new THREE.Vector3()).project(camera);
  expect(ref.current!.pick(screenPoint.x, screenPoint.y)?.markerId).toBe("17");
  const ground = scene.children[1].children[0];
  await renderer.act(async () => screen.update(<Terrain3DScene ref={ref} terrain={terrain} viewOffset={{ x: 0, y: 0 }} viewScale={1}
    satelliteTextureEnabled={false} markers={[{ ...markers[0], coordinate: [5, 5] }]} />));
  expect(scene.children[1].children[0]).toBe(ground);
  expect(scene.children[3].children).toHaveLength(0);
});

test("navigation camera follows measured GPS progress instead of staying at the trail start", async () => {
  const { gpu } = await mount({ navigationMode: true, userCoordinate: [0.8, 0.2] });
  const first = gpu.render.mock.calls.at(-1)[1].position.clone();
  await renderer.act(async () => screen.update(<Terrain3DScene terrain={terrain} viewOffset={{ x: 0, y: 0 }} viewScale={1}
    navigationMode satelliteTextureEnabled={false} userCoordinate={[0.4, 0.6]} />));
  await renderer.act(async () => frame?.(100));
  const [scene, camera] = gpu.render.mock.calls.at(-1);
  expect(camera.position.distanceTo(first)).toBeGreaterThan(1);
  scene.updateMatrixWorld(true); camera.updateMatrixWorld(true);
  expect(scene.getObjectByName("user-gps-marker")).toBeUndefined();
  const point = coordinateToTerrainScenePoint(terrain, [0.4, 0.6])!;
  const anchor = new THREE.Vector3(point.x, point.y, point.z).applyMatrix4(scene.children[2].matrixWorld);
  expect(camera.position.x).toBeCloseTo(anchor.x, 5);
  expect(camera.position.z).toBeCloseTo(anchor.z, 5);
  expect((camera.position.y - anchor.y) * terrain.metersPerUnit).toBeLessThan(7);
});

test("GPS outside the DEM shows a labelled first-person preview from the trail start", async () => {
  const { gpu } = await mount({ navigationMode: true, userCoordinate: [-34.6, -58.4] });
  const [scene, camera] = gpu.render.mock.calls.at(-1);
  const first = camera.position.clone();
  expect(scene.getObjectByName("user-gps-marker")).toBeUndefined();
  expect(screen.root.findByProps({ testID: "terrain-preview-label" })).toBeDefined();
  scene.updateMatrixWorld(true);
  const start = new THREE.Vector3(terrain.route[0].x, terrain.route[0].y, terrain.route[0].z)
    .applyMatrix4(scene.children[2].matrixWorld);
  expect(camera.position.x).toBeCloseTo(start.x, 5);
  expect(camera.position.z).toBeCloseTo(start.z, 5);
  await renderer.act(async () => screen.update(<Terrain3DScene terrain={terrain} viewOffset={{ x: 0, y: 0 }}
    viewScale={1} navigationMode satelliteTextureEnabled={false} />));
  await renderer.act(async () => frame?.(100));
  expect(camera.position.distanceTo(first)).toBeCloseTo(0, 5);
  expect((camera.position.y - start.y) * terrain.metersPerUnit).toBeLessThan(7);
});

test("inspecting a warning focuses its location and closing it resumes the GPS camera", async () => {
  const { gpu } = await mount({ navigationMode: true, userCoordinate: [0.8, 0.2] });
  const [scene, camera] = gpu.render.mock.calls.at(-1);
  const navigationPosition = camera.position.clone();
  const ground = scene.children[1].children[0];
  await renderer.act(async () => screen.update(<Terrain3DScene terrain={terrain} viewOffset={{ x: 0, y: 0 }} viewScale={1}
    navigationMode userCoordinate={[0.8, 0.2]} satelliteTextureEnabled={false} focusCoordinate={[0.2, 0.8]} />));
  await renderer.act(async () => frame?.(100));
  scene.updateMatrixWorld(true); camera.updateMatrixWorld(true);
  const local = coordinateToTerrainScenePoint(terrain, [0.2, 0.8])!;
  const projected = new THREE.Vector3(local.x, local.y, local.z).applyMatrix4(scene.children[1].matrixWorld).project(camera);
  expect(projected.x).toBeCloseTo(0, 5);
  expect(scene.children[1].children[0]).toBe(ground);
  await renderer.act(async () => screen.update(<Terrain3DScene terrain={terrain} viewOffset={{ x: 0, y: 0 }} viewScale={1}
    navigationMode userCoordinate={[0.8, 0.2]} satelliteTextureEnabled={false} />));
  await renderer.act(async () => frame?.(100));
  expect(camera.position.distanceTo(navigationPosition)).toBeCloseTo(0, 5);
});

test("the initial overview fits the entire route on a tall mobile screen", async () => {
  const { gpu } = await mount();
  const [scene, camera] = gpu.render.mock.calls.at(-1);
  scene.updateMatrixWorld(true); camera.updateMatrixWorld(true);
  terrain.route.forEach(point => {
    const projected = new THREE.Vector3(point.x, point.y, point.z).applyMatrix4(scene.children[2].matrixWorld).project(camera);
    expect(Math.abs(projected.x)).toBeLessThan(0.95);
    expect(Math.abs(projected.y)).toBeLessThan(0.95);
  });
});

test("satellite exports match the geographic aspect ratio instead of shifting the image extent", async () => {
  const model = buildTerrainSceneModel({ ...grid, bounds: { north: -41, south: -41.02, east: -71, west: -71.04 } } as never,
    [[-41, -71.04], [-41.02, -71]])!;
  await mount({ terrain: model, satelliteTextureEnabled: true });
  const url = new URL((loadTerrainTexture as jest.Mock).mock.calls[0][0]);
  expect(url.searchParams.get("size")).toBe("2048,1024");
  expect(url.searchParams.get("imageSR")).toBe("4326");
});

test.each([0, 600])("navigation keeps nearby ground in view with a %i m drop per row", async (drop) => {
  const elevationsMeters = grid.elevationsMeters.map((_, index) => (2 - Math.floor(index / 3)) * drop);
  const model = buildTerrainSceneModel({ ...grid, elevationsMeters } as never, [[0.7, 0.5], [0.3, 0.5]])!;
  const { gpu } = await mount({ terrain: model, navigationMode: true });
  const [scene, camera] = gpu.render.mock.calls.at(-1);
  scene.updateMatrixWorld(true);
  const below = new THREE.Raycaster(camera.position, new THREE.Vector3(0, -1, 0));
  const ray = new THREE.Raycaster(camera.position, camera.getWorldDirection(new THREE.Vector3()));
  const mesh = scene.getObjectByName("terrain-dem-surface");
  const [clearance] = below.intersectObject(mesh, false);
  const [ground] = ray.intersectObject(mesh, false);
  expect(clearance.distance * model.metersPerUnit).toBeCloseTo(6);
  expect(ground.distance * model.metersPerUnit).toBeLessThan(60);
  expect(loadTerrainTexture).not.toHaveBeenCalled();
});

test("navigation loads detail for the current area, discarding stale requests and retaining the base image", async () => {
  let resolveStart!: (texture: THREE.Texture) => void;
  const base = new THREE.Texture();
  const stale = new THREE.Texture();
  const detail = new THREE.Texture();
  const disposeStale = jest.spyOn(stale, "dispose");
  const disposeDetail = jest.spyOn(detail, "dispose");
  const loadTexture = loadTerrainTexture as jest.Mock;
  loadTexture.mockResolvedValueOnce(base)
    .mockReturnValueOnce(new Promise(resolve => { resolveStart = resolve; }))
    .mockResolvedValueOnce(detail);

  const { gpu } = await mount({ navigationMode: true, satelliteTextureEnabled: true });
  const [scene] = gpu.render.mock.calls.at(-1);
  const ground = scene.getObjectByName("terrain-dem-surface") as THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial>;
  const updatePosition = (coordinate: [number, number]) => renderer.act(async () => screen.update(
    <Terrain3DScene terrain={terrain} viewOffset={{ x: 0, y: 0 }} viewScale={1}
      navigationMode userCoordinate={coordinate} satelliteTextureEnabled />
  ));
  expect(ground.material.map).toBe(base);
  expect(loadTexture).toHaveBeenCalledTimes(2);
  await updatePosition([0.98, 0.02]);
  await updatePosition([0.25, 0.65]);
  expect(loadTexture).toHaveBeenCalledTimes(2);
  await renderer.act(async () => { resolveStart(stale); });
  expect(disposeStale).toHaveBeenCalledTimes(1);
  expect(loadTexture).toHaveBeenCalledTimes(3);

  const request = new URL(loadTexture.mock.calls[2][0]);
  const [west, south, east, north] = request.searchParams.get("bbox")!.split(",").map(Number);
  expect(request.searchParams.get("size")).toBe("1024,1024");
  expect(east - west).toBeCloseTo(384 / grid.sideLengthMeters);
  expect(west).toBeLessThan(0.65);
  expect(east).toBeGreaterThan(0.65);
  expect(south).toBeLessThan(0.25);
  expect(north).toBeGreaterThan(0.25);
  const shader = { ...THREE.ShaderLib.basic, uniforms: {} } as Parameters<typeof ground.material.onBeforeCompile>[0];
  ground.material.onBeforeCompile(shader, gpu);
  expect(shader.uniforms.terrainDetailMap.value).toBe(detail);
  const [u, v, width, height] = shader.uniforms.terrainDetailBounds.value.toArray();
  expect(u).toBeCloseTo(west);
  expect(v).toBeCloseTo(south);
  expect(u + width).toBeCloseTo(east);
  expect(v + height).toBeCloseTo(north);
  expect(detail.minFilter).toBe(THREE.LinearMipmapLinearFilter);

  await updatePosition([0.251, 0.651]);
  expect(loadTexture).toHaveBeenCalledTimes(3);
  loadTexture.mockRejectedValueOnce(new Error("Imagery unavailable"));
  await updatePosition([0.8, 0.8]);
  expect(loadTexture).toHaveBeenCalledTimes(4);
  expect(ground.material.map).toBe(base);
  expect(shader.uniforms.terrainDetailMap.value).toBe(detail);
  await renderer.act(async () => screen.unmount()); screen = null;
  expect(disposeDetail).toHaveBeenCalledTimes(1);
});

test("night, fog and probability-only forecasts use their actual atmospheric states", async () => {
  const { gpu } = await mount({ weather: { condition: "Niebla", temperatureC: 4, rainProbability: 95, isDay: false } });
  const [scene] = gpu.render.mock.calls.at(-1);
  expect(scene.children[0].getObjectByName("weather-precipitation")).toBeUndefined();
  const sun = scene.children.find((child: THREE.Object3D) => child instanceof THREE.DirectionalLight);
  expect(sun.intensity).toBeLessThan(0.3);
});

test("terrain details and copyright stay hidden until information opens without rebuilding the scene", async () => {
  const markers = [{ id: "17", coordinate: [0.5, 0.5], color: "#BD332B", precisionMeters: 150, issueSummary: "Barro" }];
  const weather = { condition: "Despejado", temperatureC: 15, rainProbability: 90 };
  const { gpu } = await mount({ markers, showContours: true, weather });
  const [scene] = gpu.render.mock.calls.at(-1);
  expect(scene.children[1].getObjectByName("terrain-contours")).toBeDefined();
  expect(scene.children[3].getObjectByName("reported-ground-section")).toBeDefined();
  expect(JSON.stringify(screen.toJSON())).not.toContain("Altura ×1");
  await renderer.act(async () => screen.update(<Terrain3DScene terrain={terrain} viewOffset={{ x: 0, y: 0 }}
    viewScale={1} satelliteTextureEnabled={false} markers={markers as never} showContours weather={weather}
    informationVisible mapAttribution="Elevación: Mapzen Terrain Tiles · Imagen: Esri World Imagery" />));
  const text = JSON.stringify(screen.toJSON());
  expect(text).toContain("Información del mapa");
  expect(text).toContain("Suelo reportado: Barro");
  expect(text).toContain("Altura ×1");
  expect(text).toContain("detalle ≈");
  expect(text).toContain("Mapzen Terrain Tiles");
  expect(text).toContain("Esri World Imagery");
  expect(createTerrainRenderer).toHaveBeenCalledTimes(1);
  expect(scene.children[0].getObjectByName("weather-precipitation")).toBeUndefined();
});

test("changing an affected section updates its terrain overlay while retaining the DEM and report picking", async () => {
  const { gpu } = await mount({ highlightedSections: [{ id: "test", coordinates: [[0.8, 0.2], [0.6, 0.4]], color: "#087F4F" }] });
  const [scene] = gpu.render.mock.calls.at(-1), ground = scene.children[1].children[0];
  expect(scene.children[3].getObjectByName("report-section-test")).toBeDefined();
  await renderer.act(async () => screen.update(<Terrain3DScene terrain={terrain} viewOffset={{ x: 0, y: 0 }} viewScale={1} satelliteTextureEnabled={false}
    highlightedSections={[{ id: "updated", coordinates: [[0.7, 0.3], [0.5, 0.5]], color: "#087F4F" }]} />));
  expect(scene.children[3].getObjectByName("report-section-test")).toBeUndefined();
  expect(scene.children[3].getObjectByName("report-section-updated")).toBeDefined();
  expect(scene.children[1].children[0]).toBe(ground);
});
