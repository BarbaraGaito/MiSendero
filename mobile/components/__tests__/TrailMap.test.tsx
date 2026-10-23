import "../../../testing/mobileSetup";
jest.mock("expo-network", () => ({ useNetworkState: jest.fn() }));
jest.mock("../../hooks/useDeviceLocation", () => ({ useDeviceLocation: jest.fn() }));
jest.mock("../../hooks/useTerrainElevation", () => ({ useTerrainElevation: jest.fn() }));
jest.mock("../Terrain3DScene", () => ({ Terrain3DScene: "Terrain3DScene" }));
jest.mock("../../../services/basicOfflineMap", () => ({
  ...jest.requireActual("../../../services/basicOfflineMap"), readBasicOfflineMap:jest.fn().mockResolvedValue(null),
}));
jest.mock("../../../services/mapTileCache", () => ({
  ...jest.requireActual("../../../services/mapTileCache"), resolveCachedTileUri: jest.fn().mockResolvedValue(null), getOfflineTilePlanForTrail: jest.fn(() => [{ zoom: 12 }]),
}));
import { Image, PanResponder } from "react-native";
import { useNetworkState } from "expo-network";
import { router } from "expo-router";
import { useDeviceLocation } from "../../hooks/useDeviceLocation";
import { useTerrainElevation } from "../../hooks/useTerrainElevation";
import { resolveCachedTileUri } from "../../../services/mapTileCache";
import { readBasicOfflineMap } from "../../../services/basicOfflineMap";
import { TrailMap } from "../TrailMap";
import { trail } from "../../../testing/fixtures";
import { act, mount, press, text, flush } from "../../../testing/mobileHarness";
let gestures: any;
const route = [[-41, -71], [-41.001, -71], [-41.002, -71.001]];
const grid = { size: 3, center: [-41.001, -71.0005], bounds: { north: -40.99, south: -41.01, west: -71.01, east: -70.99 }, sideLengthMeters: 1440, cellSizeMeters: 720, elevationsMeters: [100,110,120,130,140,150,160,170,180], minElevationMeters: 100, maxElevationMeters: 180 };
beforeEach(() => {
  (useNetworkState as jest.Mock).mockReturnValue({ isConnected: true, isInternetReachable: true });
  (useDeviceLocation as jest.Mock).mockReturnValue({ location: { coordinate: [-41, -71], accuracy: 5 }, permissionDenied: false, error: null, isTestingLocation: false });
  (useTerrainElevation as jest.Mock).mockReturnValue({ status: "ready", data: { grid } });
  (resolveCachedTileUri as jest.Mock).mockResolvedValue(null);
  (readBasicOfflineMap as jest.Mock).mockResolvedValue(null);
  jest.spyOn(PanResponder, "create").mockImplementation((config) => { gestures = config; return { panHandlers: {} } as any; });
});
const surface = (tree: any) => tree.root.findAll((node: any) => typeof node.props.onTouchStart === "function" && typeof node.props.onLayout === "function")[0];
const layout = async (tree: any) => act(async () => { surface(tree).props.onLayout({ nativeEvent: { layout: { width: 320, height: 480 } } }); await flush(); });
const tap = async (tree: any, x: number, y: number) => act(async () => {
  surface(tree).props.onTouchStart({ nativeEvent: { touches: [{}], locationX: x, locationY: y } });
  surface(tree).props.onTouchEnd({ nativeEvent: { touches: [], locationX: x, locationY: y } }); await flush();
});
test("2D route uses local tile files where available and switches visible source layers", async () => {
  (resolveCachedTileUri as jest.Mock).mockResolvedValue("file:///saved-tile.png");
  const tree = await mount(TrailMap, { trail, fitRoute: true, selectedCoordinate: route[1] }); await layout(tree);
  expect(tree.root.findAllByType(Image).some((node: any) => node.props.source?.uri === "file:///saved-tile.png")).toBe(true);
  await press(tree, "Mapa"); expect(text(tree)).toContain("OpenStreetMap");
  await press(tree, "Satelite"); expect(text(tree)).toContain("© Esri");
  expect(text(tree)).not.toContain("Earthstar Geographics");
  const credits = tree.root.findAll((node: any) => node.props.accessibilityLabel === "Fuentes y licencias del mapa")[0];
  await act(async () => credits.props.onPress());
  expect(router.push).toHaveBeenCalledWith({ pathname: "/atribuciones", params: { trailId: String(trail.id) } });
  await press(tree, "Terreno"); expect(text(tree)).toContain(trail.name);
});
test("a selected point is snapped to the route, distant points and dragged taps are rejected", async () => {
  const select = jest.fn(), reject = jest.fn(); const tree = await mount(TrailMap, { trail, fitRoute: true, onSelectCoordinate: select, onSelectionRejected: reject, selectionToleranceMeters: 80 });
  await layout(tree); await tap(tree, 160, 240);
  expect(select).toHaveBeenCalledWith(expect.objectContaining({ distanceToRouteMeters: expect.any(Number), routeProgressMeters: expect.any(Number) }));
  await tap(tree, 0, 0); expect(reject).toHaveBeenCalledWith(expect.any(Number));
  select.mockClear(); await act(async () => {
    surface(tree).props.onTouchStart({ nativeEvent: { touches: [{}], locationX: 160, locationY: 240 } });
    surface(tree).props.onTouchMove({ nativeEvent: { locationX: 200, locationY: 240 } });
    surface(tree).props.onTouchEnd({ nativeEvent: { touches: [], locationX: 200, locationY: 240 } });
  }); expect(select).not.toHaveBeenCalled();
});
test("pan and pinch gestures finish interactions and update scale in both map modes", async () => {
  const interacting = jest.fn(); const tree = await mount(TrailMap, { trail, fitRoute: true, onInteractionChange: interacting }); await layout(tree);
  const one = { nativeEvent: { touches: [{ pageX: 0, pageY: 0 }] } };
  const pinch = (distance: number) => ({ nativeEvent: { touches: [{ pageX: 0, pageY: 0 }, { pageX: distance, pageY: 0 }] } });
  expect(gestures.onStartShouldSetPanResponder(one)).toBe(true);
  await act(async () => { gestures.onPanResponderGrant(one); gestures.onPanResponderMove(one, { dx: 15, dy: 12 }); });
  await act(async () => gestures.onPanResponderRelease({}, { dx: 15, dy: 12 }));
  await act(async () => { gestures.onPanResponderGrant(pinch(100)); gestures.onPanResponderMove(pinch(180), { dx: 0, dy: 0 }); });
  await act(async () => gestures.onPanResponderRelease({}, { dx: 0, dy: 0 }));
  await press(tree, "Cambiar a perspectiva 3D");
  expect(tree.root.findAllByType("Terrain3DScene")).toHaveLength(1);
  expect(text(tree)).not.toContain("LECTURA DEL TERRENO");
  expect(text(tree)).not.toContain("ESCALA REAL");
  expect(text(tree)).toContain("Open-Meteo");
  await act(async () => { gestures.onPanResponderGrant(pinch(100)); gestures.onPanResponderMove(pinch(150), { dx: 0, dy: 0 }); });
  await act(async () => gestures.onPanResponderRelease({}, { dx: 0, dy: 0 }));
  expect(tree.root.findByType("Terrain3DScene").props.viewScale).toBe(1.5);
  await act(async () => { gestures.onPanResponderGrant(one); gestures.onPanResponderMove(one, { dx: 20, dy: 30 }); });
  await act(async () => gestures.onPanResponderRelease({}, { dx: 20, dy: 30 }));
  expect(tree.root.findByType("Terrain3DScene").props.viewOffset).toEqual({ x: 20, y: 30 });
  await act(async () => gestures.onPanResponderTerminate()); expect(interacting).toHaveBeenLastCalledWith(false);
});
test.each(["offline", "no-route", "provider-error"])("missing DEM data (%s) never produces a fabricated 3D surface", async (reason) => {
  (useTerrainElevation as jest.Mock).mockReturnValue({ status: "unavailable", reason });
  const tree = await mount(TrailMap, { trail, initialPerspective: true }); expect(text(tree)).toContain("Relieve 3D no disponible"); expect(tree.root.findAllByType("Terrain3DScene")).toHaveLength(0);
});
test("offline mode uses only the basic local map, with no satellite, terrain or 3D requests", async () => {
  (useNetworkState as jest.Mock).mockReturnValue({ isConnected: false });
  (useDeviceLocation as jest.Mock).mockReturnValue({ location: null, permissionDenied: true, error: null, isTestingLocation: false });
  const tree = await mount(TrailMap, { trail }); await layout(tree);
  expect(text(tree)).not.toContain("Satelite"); expect(text(tree)).toContain("Activa la ubicacion");
  expect(text(tree)).not.toContain("Terreno");
  expect(text(tree)).not.toContain("3D");
  expect(Image.prefetch).not.toHaveBeenCalled();
  expect(tree.root.findAllByType(Image).some((node: any) => node.props.source?.uri?.startsWith("http"))).toBe(false);
});

test("opening a downloaded map while connected displays the saved 2D features without remote requests", async () => {
  (readBasicOfflineMap as jest.Mock).mockResolvedValue({version:1,id:"saved",attribution:"© OpenStreetMap contributors",bounds:{south:-42,north:-40,west:-72,east:-70},
    features:[{id:"path1",kind:"path",name:"Camino guardado",points:route}]});
  const tree = await mount(TrailMap,{trail,offlineOnly:true,initialPerspective:true}); await layout(tree);
  expect(tree.root.findAll((node: any) => node.props.testID === "offline-basic-map").length).toBeGreaterThan(0);
  expect(text(tree)).toContain("Mapa descargado");
  expect(text(tree)).not.toContain("Satelite");
  expect(tree.root.findAllByType("Terrain3DScene")).toHaveLength(0);
  expect(Image.prefetch).not.toHaveBeenCalled();
  expect(tree.root.findAllByType(Image)).toHaveLength(0);
});
