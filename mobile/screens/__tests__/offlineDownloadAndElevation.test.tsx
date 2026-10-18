import "../../../testing/mobileSetup";
jest.mock("../../../services/api", () => ({ getTrailById: jest.fn(), getTrailReports: jest.fn() }));
jest.mock("../../../services/trailRepository", () => ({ getTrailById: jest.fn() }));
jest.mock("../../../services/offlineMaps", () => ({ saveOfflineTrailMap: jest.fn(), getOfflineMaps: jest.fn(), deleteOfflineMap: jest.fn(), getVerifiedOfflineMapByTrailId: jest.fn() }));
import { useLocalSearchParams, router } from "expo-router";
import { Linking } from "react-native";
import { mount, press, text, act, flush } from "../../../testing/mobileHarness";
import { trail } from "../../../testing/fixtures";
import * as api from "../../../services/api";
import * as maps from "../../../services/offlineMaps";
import { getTrailById } from "../../../services/trailRepository";
import Download from "../offline-flow/OfflineDownload21Screen";
import Downloaded from "../offline-flow/OfflineDownloadedMaps23Screen";
import Elevation from "../TrailElevationScreen";
const saved = { id: 3, trail, name: trail.name, status: "disponible", totalTiles: 4, downloadedTiles: 4, sizeMb: 8, updatedAt: Date.UTC(2026, 9, 16), verifiedAt: Date.UTC(2026, 9, 16) };
const elevation = { source: "Copernicus DEM", source_url: "https://example.test/dem", min_m: 100, max_m: 200, ascent_m: 100, descent_m: 0, distance_m: 1000, resolution_m: 90, points: [{ distance_m: 0, elevation_m: 100 }, { distance_m: 500, elevation_m: 150 }, { distance_m: 1000, elevation_m: 200 }] };
beforeEach(() => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "7" }); (api.getTrailById as jest.Mock).mockResolvedValue(trail); (api.getTrailReports as jest.Mock).mockResolvedValue([]);
  (maps.saveOfflineTrailMap as jest.Mock).mockResolvedValue({ ...saved, terrain: {} }); (maps.getOfflineMaps as jest.Mock).mockResolvedValue([saved]); (maps.deleteOfflineMap as jest.Mock).mockResolvedValue(undefined); (maps.getVerifiedOfflineMapByTrailId as jest.Mock).mockResolvedValue(saved);
  (getTrailById as jest.Mock).mockResolvedValue({ ...trail, elevation });
});
test("download displays actual tile progress and becomes available only after persistence completes", async () => {
  let complete!: (result: any) => void;
  (maps.saveOfflineTrailMap as jest.Mock).mockImplementation((_trail, _reports, progress) => { progress(2, 4); return new Promise((resolve) => { complete = resolve; }); });
  const tree = await mount(Download); expect(text(tree)).toContain("50%"); expect(text(tree)).not.toContain("Mapa descargado"); expect(maps.saveOfflineTrailMap).toHaveBeenCalledWith(trail, [], expect.any(Function), expect.objectContaining({ shouldCancel: expect.any(Function) }));
  await act(async () => { complete(saved); await flush(); }); expect(text(tree)).toContain("100%"); expect(text(tree)).toContain("Mapa básico y recorrido disponibles"); expect(text(tree)).not.toContain("relieve 3D"); await press(tree, "Abrir ruta"); expect(router.push).toHaveBeenCalledWith({ pathname: "/route-map", params: { id: "7" } });
});
test.each([["offline-map-incomplete: 3/4", "descarga quedo incompleta"], ["timeout", "mapa completo"]])("download failure %s never offers an incomplete map as available", async (reason, message) => {
  (maps.saveOfflineTrailMap as jest.Mock).mockRejectedValue(new Error(reason)); const tree = await mount(Download); expect(text(tree)).toContain(message); expect(text(tree)).not.toContain("Abrir ruta"); await press(tree, "Reintentar"); expect(router.replace).toHaveBeenCalledWith({ pathname: "/offline-descarga", params: { id: "7" } });
});
test("invalid download does no work and unmount signals cancellation to tile persistence", async () => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "invalid" }); const invalid = await mount(Download); expect(text(invalid)).toContain("No se encontro"); expect(api.getTrailById).not.toHaveBeenCalled();
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "7" }); (maps.saveOfflineTrailMap as jest.Mock).mockImplementation(() => new Promise(() => {})); const tree = await mount(Download); const options = (maps.saveOfflineTrailMap as jest.Mock).mock.calls[0][3]; expect(options.shouldCancel()).toBe(false); await act(async () => tree.unmount()); expect(options.shouldCancel()).toBe(true);
});

test("an unavailable map source is distinguished from a failed connection", async () => {
  (maps.saveOfflineTrailMap as jest.Mock).mockRejectedValue(Object.assign(new Error("provider-not-configured"), { code: "provider-not-configured" }));
  const tree = await mount(Download);
  expect(text(tree)).toContain("Las descargas de mapas todavía no están disponibles");
  expect(text(tree)).not.toContain("Revisa tu conexion");
  expect(text(tree)).not.toContain("Abrir ruta");
});
test("download list verifies local files again before opening and offers redownload for a damaged map", async () => {
  const tree = await mount(Downloaded); expect(text(tree)).toContain("Disponible sin conexión"); await press(tree, "Abrir"); expect(router.push).toHaveBeenLastCalledWith({ pathname: "/route-map", params: { id: "7" } });
  (maps.getVerifiedOfflineMapByTrailId as jest.Mock).mockResolvedValue(null); await press(tree, "Abrir"); expect(router.push).toHaveBeenLastCalledWith({ pathname: "/offline-descarga", params: { id: "7" } });
  (maps.getOfflineMaps as jest.Mock).mockResolvedValue([]); await press(tree, "Eliminar"); expect(maps.deleteOfflineMap).toHaveBeenCalledWith(3); expect(text(tree)).toContain("No hay mapas descargados");
});
test("download list distinguishes unreadable storage, incomplete tiles and failed deletion", async () => {
  (maps.getOfflineMaps as jest.Mock).mockRejectedValue(new Error("read")); const failed = await mount(Downloaded); expect(text(failed)).toContain("No pudimos cargar");
  (maps.getOfflineMaps as jest.Mock).mockResolvedValue([{ ...saved, status: "error", totalTiles: 0, downloadedTiles: 0 }]); const tree = await mount(Downloaded); expect(text(tree)).toContain("Reintentar descarga"); expect(text(tree)).toContain("Reintentar"); (maps.deleteOfflineMap as jest.Mock).mockRejectedValue(new Error("storage")); await press(tree, "Eliminar"); expect(text(tree)).toContain("No pudimos eliminar");
});
test("elevation profile exposes measured extrema, keyboard-adjustable samples and touch selection within bounds", async () => {
  jest.spyOn(Linking, "openURL").mockResolvedValue(undefined); const tree = await mount(Elevation); expect(text(tree)).toContain("Subida acumulada"); expect(text(tree)).toContain("200 m");
  const chart = () => tree.root.findAll((node: any) => node.props.accessibilityRole === "adjustable")[0];
  await act(async () => chart().props.onAccessibilityAction({ nativeEvent: { actionName: "increment" } })); expect(chart().props.accessibilityValue.now).toBe(1);
  await act(async () => chart().props.onAccessibilityAction({ nativeEvent: { actionName: "decrement" } })); expect(chart().props.accessibilityValue.now).toBe(0);
  const surface = tree.root.findAll((node: any) => typeof node.props.onResponderGrant === "function" && typeof node.props.onLayout === "function")[0];
  await act(async () => { surface.props.onLayout({ nativeEvent: { layout: { width: 640 } } }); });
  await act(async () => surface.props.onResponderGrant({ nativeEvent: { locationX: 999 } })); expect(chart().props.accessibilityValue.now).toBe(2);
  await act(async () => surface.props.onResponderMove({ nativeEvent: { locationX: -50 } })); expect(chart().props.accessibilityValue.now).toBe(0);
  await press(tree, "Copernicus DEM"); expect(Linking.openURL).toHaveBeenCalledWith(elevation.source_url);
});
test("unavailable elevation offers retry and rejects an invalid trail identifier without requesting data", async () => {
  (getTrailById as jest.Mock).mockResolvedValueOnce({ ...trail, elevation: null }); const tree = await mount(Elevation); expect(text(tree)).toContain("Perfil no disponible"); await press(tree, "Reintentar"); expect(text(tree)).toContain("Subida acumulada");
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "-1" }); const invalid = await mount(Elevation); expect(text(invalid)).toContain("Altimetria no disponible"); expect(getTrailById).toHaveBeenCalledTimes(2);
});
