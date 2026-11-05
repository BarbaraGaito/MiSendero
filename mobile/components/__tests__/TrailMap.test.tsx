import "../../../testing/mobileSetup";
jest.mock("expo-network", () => ({ useNetworkState: jest.fn() }));
jest.mock("../../hooks/useDeviceLocation", () => ({ useDeviceLocation: jest.fn() }));
jest.mock("../../hooks/useTerrainElevation", () => ({ useTerrainElevation: jest.fn() }));
jest.mock("../Terrain3DScene", () => {
  const React = require("react");
  return { Terrain3DScene: React.forwardRef((props: any, ref: any) => {
    React.useImperativeHandle(ref, () => ({ pick: (...args: any[]) => mockPick3D(...args) }));
    return React.createElement("Terrain3DScene", props);
  }) };
});
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
const mockPick3D = jest.fn();
const route = [[-41, -71], [-41.001, -71], [-41.002, -71.001]];
const grid = { size: 3, center: [-41.001, -71.0005], bounds: { north: -40.99, south: -41.01, west: -71.01, east: -70.99 }, sideLengthMeters: 1440, cellSizeMeters: 720, elevationsMeters: [100,110,120,130,140,150,160,170,180], minElevationMeters: 100, maxElevationMeters: 180 };
beforeEach(() => {
  (useNetworkState as jest.Mock).mockReturnValue({ isConnected: true, isInternetReachable: true });
  (useDeviceLocation as jest.Mock).mockReturnValue({ location: { coordinate: [-41, -71], accuracy: 5 }, permissionDenied: false, error: null, isTestingLocation: false });
  (useTerrainElevation as jest.Mock).mockReturnValue({ status: "ready", data: { grid } });
  (resolveCachedTileUri as jest.Mock).mockResolvedValue(null);
  (readBasicOfflineMap as jest.Mock).mockResolvedValue(null);
  mockPick3D.mockReset();
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
  expect(gestures.onStartShouldSetPanResponder(one)).toBe(false); // buttons remain tappable
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

test("warnings are drawn at their map position, inspectable, and remain available on downloaded maps", async () => {
  const report = { id: 17, trail_id: trail.id, issue_summary: "Derrumbe", severity: "Alta", trail_state: "No transitable",
    blocks_path: true, latitude: -41.001, longitude: -71, route_progress_meters: 100, created_at: new Date().toISOString() };
  const tree = await mount(TrailMap, { trail, reports: [report], fitRoute: true, offlineOnly: true });
  await layout(tree);
  const marker = tree.root.findAll((node: any) => node.props.testID === "trail-report-17")[0];
  const position = marker.props.style[1];
  await tap(tree, position.left + 17, position.top + 34);
  const focusedPosition = tree.root.findAll((node: any) => node.props.testID === "trail-report-17")[0].props.style[1];
  expect(focusedPosition.left + 17).toBeCloseTo(160, 3);
  expect(focusedPosition.top + 34).toBeLessThan(200);
  expect(text(tree)).toContain("Derrumbe");
  expect(text(tree)).toContain("Bloquea el paso");
  expect(text(tree)).toContain("margen 150 m");
  expect(text(tree)).toContain("Guardado sin conexión");
  await press(tree, "Cerrar advertencia");
  expect(text(tree)).toMatch(/1\s+advertencia/);
});

test("3D report selection uses the actual terrain hit, snaps to the route, and ignores a pinch ending as one finger", async () => {
  const report = jest.fn();
  const tree = await mount(TrailMap, { trail, initialPerspective: true, onReportCoordinate: report });
  await layout(tree);
  await press(tree, "Reportar punto");
  mockPick3D.mockReturnValue({ coordinate: [-41.001, -71] });
  await tap(tree, 160, 240);
  expect(mockPick3D).toHaveBeenCalledWith(0, 0);
  expect(report).toHaveBeenCalledWith(expect.objectContaining({ coordinate: [-41.001, -71], perspective: true, routeProgressMeters: expect.any(Number) }));
  await press(tree, "Reportar punto");
  report.mockClear();
  await act(async () => {
    surface(tree).props.onTouchStart({ nativeEvent: { touches: [{}, {}], locationX: 160, locationY: 240 } });
    surface(tree).props.onTouchEnd({ nativeEvent: { touches: [{}], locationX: 160, locationY: 240 } });
    surface(tree).props.onTouchEnd({ nativeEvent: { touches: [], locationX: 160, locationY: 240 } });
  });
  expect(report).not.toHaveBeenCalled();
  mockPick3D.mockReturnValue(null);
  await tap(tree, 160, 10);
  expect(report).not.toHaveBeenCalled();
  expect(text(tree)).toContain("Tocá el sendero marcado");
});

test("a warning pin in 3D opens its report, and the picker shows the chosen point", async () => {
  const report = { id: 17, trail_id: trail.id, issue_summary: "Agua alta", severity: "Media", trail_state: "Precaucion",
    blocks_path: false, latitude: -41.001, longitude: -71, created_at: new Date().toISOString() };
  const tree = await mount(TrailMap, { trail, reports: [report], initialPerspective: true });
  await layout(tree);
  mockPick3D.mockReturnValue({ markerId: "17", coordinate: [-41.001, -71] });
  await tap(tree, 160, 240);
  expect(text(tree)).toContain("Agua alta");
  expect(tree.root.findByType("Terrain3DScene").props.focusCoordinate).toEqual([-41.001, -71]);
  expect(tree.root.findByType("Terrain3DScene").props.markers).toEqual([expect.objectContaining({ id: "17", precisionMeters: 150 })]);
  const picker = await mount(TrailMap, { trail, initialPerspective: true, selectedCoordinate: route[1], onSelectCoordinate: jest.fn() });
  expect(picker.root.findByType("Terrain3DScene").props.markers).toEqual([expect.objectContaining({ id: "selected", coordinate: route[1] })]);
});

test("3D imagery and contour views use the same actual route and forward detailed weather", async () => {
  const weather = { condition: "Nublado", temperature_c: 12, wind_kmh: 23, wind_direction_degrees: 270,
    cloud_cover_percent: 80, is_day: false, rain_probability: 70, observed_at: "2026-11-03T19:00:00Z", source: "Open-Meteo" };
  const tree = await mount(TrailMap, { trail, initialPerspective: true, weather });
  expect(tree.root.findByType("Terrain3DScene").props.weather).toMatchObject({ windKmh: 23, windDirectionDegrees: 270, isDay: false });
  await press(tree, "Ver relieve con curvas de nivel");
  expect(tree.root.findByType("Terrain3DScene").props).toMatchObject({ showContours: true, satelliteTextureEnabled: false });
  await press(tree, "Ver imagen satelital 3D");
  expect(tree.root.findByType("Terrain3DScene").props).toMatchObject({ showContours: false, satelliteTextureEnabled: true });
});

test("a selected affected section is visible on both map modes without replacing the actual route", async () => {
  const tree = await mount(TrailMap, { trail, selectedCoordinate: route[0], selectedEndCoordinate: route[1], selectedRouteRange: { start: 0, end: 111 } });
  await layout(tree);
  expect(tree.root.findAll((node: any) => node.props.testID === "selected-section-end").length).toBeGreaterThan(0);
  await press(tree, "Cambiar a perspectiva 3D");
  expect(tree.root.findByType("Terrain3DScene").props.highlightedSections).toEqual([expect.objectContaining({ id: "selected-range", coordinates: expect.any(Array) })]);
  expect(tree.root.findByType("Terrain3DScene").props.markers.map((marker: any) => marker.id)).toEqual(["selected", "selected-end"]);
});
