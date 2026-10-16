jest.mock("expo-gl", () => ({ GLView: "GLView" }));
jest.mock("expo-three", () => ({
  Renderer: jest.fn().mockImplementation(() => ({ shadowMap: {}, render: jest.fn(), setClearColor: jest.fn(), dispose: jest.fn() })),
  TextureLoader: jest.fn().mockImplementation(() => ({ setCrossOrigin: jest.fn(), load: jest.fn() })),
}));
import React from "react";
import * as THREE from "three";
import { Renderer, TextureLoader } from "expo-three";
import { Terrain3DScene } from "../Terrain3DScene";
import { buildTerrainSceneModel } from "../terrainSceneModel";
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
  return { gl, gpu: (Renderer as jest.Mock).mock.results.at(-1)!.value };
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
  expect(group.children).toHaveLength(5);
  await renderer.act(async () => screen.update(<Terrain3DScene terrain={terrain} viewOffset={{ x: 20, y: 200 }} viewScale={2} satelliteTextureEnabled={false} userCoordinate={[5, 5]} />));
  expect(group.children).toHaveLength(4);
  await renderer.act(async () => frame?.(100));
  expect(gpu.render.mock.calls.at(-1)[1].zoom).toBe(1.9); // public maximum zoom
});
test("late satellite images are disposed after scene replacement and network errors keep DEM geometry", async () => {
  const { gpu } = await mount({ satelliteTextureEnabled: true });
  const loader = (TextureLoader as unknown as jest.Mock).mock.results[0].value;
  const [url, accept, , reject] = loader.load.mock.calls[0];
  expect(url).toContain("bbox=0%2C0%2C1%2C1");
  const texture = new THREE.Texture(); const disposed = jest.spyOn(texture, "dispose");
  await renderer.act(async () => screen.update(<Terrain3DScene terrain={terrain} viewOffset={{ x: 0, y: 0 }} viewScale={1} satelliteTextureEnabled={false} />));
  accept(texture); reject(new Error("offline"));
  expect(disposed).toHaveBeenCalledTimes(1);
  expect(gpu.render.mock.calls[0][0].children[1].children).toHaveLength(2);
});
