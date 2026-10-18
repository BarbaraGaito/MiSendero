import "../../../testing/mobileSetup";
jest.mock("../../components/TrailMap", () => ({ TrailMap: "TrailMap" }));
jest.mock("../../../services/trailRepository", () => ({ getTrailById: jest.fn(), getTrailReports: jest.fn(), getTrailWeather: jest.fn() }));
jest.mock("../../../services/offlineMaps", () => ({ getOfflineMapByTrailId: jest.fn(), getVerifiedOfflineMapByTrailId: jest.fn() }));
jest.mock("../../../services/routeSession", () => ({ ensureRouteSession: jest.fn(), getRouteSession: jest.fn(), getSimulatedRouteTrackingSummary: jest.fn(), activeRouteSeconds: jest.fn().mockReturnValue(120), pauseRouteSession: jest.fn(), resumeRouteSession: jest.fn() }));
jest.mock("../../../services/routeTracking", () => ({ getRouteTrackingSummary: jest.fn() }));
jest.mock("../../../services/wearableMetrics", () => ({ getWearableRuntimeStatus: jest.fn(), syncNativeWearableSampleWithStatus: jest.fn(), createDevelopmentMetricSequence: jest.fn() }));
jest.mock("../../hooks/useDeviceLocation", () => ({ useDeviceLocation: jest.fn() }));
jest.mock("../../../services/authSession", () => ({ getAuthSession: jest.fn() }));
jest.mock("../../../services/api", () => ({ createTrailReport: jest.fn() }));
jest.mock("../../../services/syncQueue", () => ({ isOnline: jest.fn(), enqueue: jest.fn(), runSync: jest.fn().mockResolvedValue({ processed: 0, failed: 0 }) }));
jest.mock("expo-network", () => ({ getNetworkStateAsync: jest.fn(), NetworkStateType: { WIFI: "WIFI" } }));
import { router, useLocalSearchParams } from "expo-router";
import * as Network from "expo-network";
import { TextInput } from "react-native";
import { mount, text, press, act, flush } from "../../../testing/mobileHarness";
import { trail } from "../../../testing/fixtures";
import * as repository from "../../../services/trailRepository";
import * as maps from "../../../services/offlineMaps";
import * as sessions from "../../../services/routeSession";
import * as wearable from "../../../services/wearableMetrics";
import * as queue from "../../../services/syncQueue";
import { getRouteTrackingSummary } from "../../../services/routeTracking";
import { getAuthSession } from "../../../services/authSession";
import { createTrailReport } from "../../../services/api";
import { useDeviceLocation } from "../../hooks/useDeviceLocation";
import { DepartureMessageRequiredError } from "../../../services/departureMessages";
import Route from "../RouteMap";
import Report from "../ReportTerrainScreen";
const startedAt = Date.UTC(2026, 9, 16, 10);
const gps = { coordinate: [-41, -71], accuracy: 5, timestamp: startedAt };
const summary = { distanceMeters: 123, lastRecordedAt: startedAt, lastPoint: null };
const runtime = { status: "linked", displayName: "Sensor", connection: { linked: true, provider: "apple_healthkit" }, latestSample: null, prediction: null };
beforeEach(() => {
  jest.useFakeTimers({ now: startedAt });
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "7", startedAt: String(startedAt) });
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ type: "WIFI", isConnected: true, isInternetReachable: true });
  (repository.getTrailById as jest.Mock).mockResolvedValue(trail); (repository.getTrailReports as jest.Mock).mockResolvedValue([]);
  (repository.getTrailWeather as jest.Mock).mockResolvedValue({ temperature_c: 10, condition: "Nublado", wind_kmh: 12, rain_probability: 20, risk_level: "medio", recommendation: "Abrigo", source: "Fixture" });
  (maps.getOfflineMapByTrailId as jest.Mock).mockResolvedValue(null); (maps.getVerifiedOfflineMapByTrailId as jest.Mock).mockResolvedValue(null);
  (sessions.ensureRouteSession as jest.Mock).mockResolvedValue(undefined); (sessions.getRouteSession as jest.Mock).mockResolvedValue({ state: "active", simulated: false });
  (sessions.pauseRouteSession as jest.Mock).mockResolvedValue(undefined); (sessions.resumeRouteSession as jest.Mock).mockResolvedValue(undefined);
  (getRouteTrackingSummary as jest.Mock).mockResolvedValue(summary); (sessions.getSimulatedRouteTrackingSummary as jest.Mock).mockReturnValue(summary);
  (wearable.getWearableRuntimeStatus as jest.Mock).mockResolvedValue(runtime); (wearable.createDevelopmentMetricSequence as jest.Mock).mockResolvedValue([]); (wearable.syncNativeWearableSampleWithStatus as jest.Mock).mockResolvedValue("no_data");
  (useDeviceLocation as jest.Mock).mockReturnValue({ location: gps, isLoading: false, permissionDenied: false, isTestingLocation: false });
  (getAuthSession as jest.Mock).mockResolvedValue({ token: "token", user: { id: 31 } });
  (queue.isOnline as jest.Mock).mockResolvedValue(true); (queue.enqueue as jest.Mock).mockResolvedValue(1); (createTrailReport as jest.Mock).mockResolvedValue({ id: 1 });
});
afterEach(() => { jest.useRealTimers(); });
const active = () => (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "7", active: "1", startedAt: String(startedAt) });
test("route preview shows weather and blocking reports and offers the actual trail download/start", async () => {
  (repository.getTrailReports as jest.Mock).mockResolvedValue([{ id: 1, user_id: 99, blocks_path: true, severity: "Alta", issue_summary: "Puente cerrado", trail_state: "No transitable", route_progress_meters: 1000, details: "Crece el río", observed_at: "invalid", created_at: "2026-10-16T10:00:00Z" }]);
  const tree = await mount(Route); expect(text(tree)).toContain("Puente cerrado"); expect(text(tree)).toContain("Riesgo medio"); expect(text(tree)).toContain("Abrigo");
  await press(tree, "Descargar mapa"); expect(router.push).toHaveBeenLastCalledWith({ pathname: "/offline-descarga", params: { id: "7" } });
  await press(tree, "Iniciar recorrido"); expect(router.push).toHaveBeenLastCalledWith({ pathname: "/trail-start", params: { id: "7" } });
});
test.each([false, true])("offline route loads cached context, including when the network request failed (%s)", async (requestFails) => {
  if (requestFails) (repository.getTrailById as jest.Mock).mockRejectedValue(new Error("offline"));
  else (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: false });
  (maps.getOfflineMapByTrailId as jest.Mock).mockResolvedValue({ trail, reports: [], status: "disponible" });
  const tree = await mount(Route); expect(tree.root.findByType("TrailMap").props).toMatchObject({ trail, allowSatellite: false }); expect(repository.getTrailWeather).not.toHaveBeenCalled(); expect(text(tree)).not.toContain("Descargar mapa");
});
test("missing offline map is an explicit failure, not an invented route", async () => {
  (Network.getNetworkStateAsync as jest.Mock).mockRejectedValue(new Error("network unavailable")); const tree = await mount(Route); expect(text(tree)).toContain("No pudimos cargar el mapa"); expect(tree.root.findByType("TrailMap").props.trail).toBeNull();
});
test("active route pauses durably before navigating and passes measured distance when finishing", async () => {
  active(); const tree = await mount(Route); expect(text(tree)).toContain("Ultimo punto guardado");
  await press(tree, "Pausa"); expect(sessions.pauseRouteSession).toHaveBeenCalledWith(7, startedAt); expect(router.push).toHaveBeenCalledWith(expect.objectContaining({ pathname: "/descanso", params: expect.objectContaining({ traveledMeters: "123" }) }));
  await press(tree, "Terminar ruta Guardar actividad y dejar opinion"); expect(router.push).toHaveBeenLastCalledWith(expect.objectContaining({ pathname: "/recorrido-finalizado", params: expect.objectContaining({ traveledMeters: "123", endedLatitude: "-41" }) }));
  await press(tree, "SOS"); expect(router.push).toHaveBeenLastCalledWith({ pathname: "/confirmar-sos", params: { id: "7", startedAt: String(startedAt), sendSms: "1" } });
});
test("resume, failed pause and departure precondition are kept distinct", async () => {
  active(); (sessions.getRouteSession as jest.Mock).mockResolvedValue({ state: "paused" }); const paused = await mount(Route); await press(paused, "Reanudar"); expect(sessions.resumeRouteSession).toHaveBeenCalledWith(7, startedAt);
  (sessions.getRouteSession as jest.Mock).mockResolvedValue({ state: "active" }); (sessions.pauseRouteSession as jest.Mock).mockRejectedValue(new Error("disk")); const tree = await mount(Route); await press(tree, "Pausa"); expect(text(tree)).toContain("No pudimos guardar la pausa");
  (sessions.ensureRouteSession as jest.Mock).mockRejectedValue(new DepartureMessageRequiredError()); await mount(Route); expect(router.replace).toHaveBeenCalledWith({ pathname: "/trail-start", params: { id: "7" } });
});
test("real GPS deviation warns and opens recovery while a completed route redirects to history", async () => {
  active(); (useDeviceLocation as jest.Mock).mockReturnValue({ location: { ...gps, coordinate: [-41.01, -71.01] }, isLoading: false, isTestingLocation: false });
  const tree = await mount(Route); expect(text(tree)).toContain("Te alejaste"); await press(tree, "Ver"); expect(router.push).toHaveBeenCalledWith(expect.objectContaining({ pathname: "/alerta-ruta", params: expect.objectContaining({ distance: expect.any(String) }) }));
  (sessions.getRouteSession as jest.Mock).mockResolvedValue({ state: "completed" }); await act(async () => { jest.advanceTimersByTime(1000); await flush(); }); expect(router.replace).toHaveBeenCalledWith("/mis-actividades");
});
test("a simulated critical wearable reading always routes SOS into testing mode", async () => {
  active(); (useDeviceLocation as jest.Mock).mockReturnValue({ location: gps, isLoading: false, isTestingLocation: true });
  (sessions.getRouteSession as jest.Mock).mockResolvedValue({ state: "active", simulated: true });
  (wearable.getWearableRuntimeStatus as jest.Mock).mockResolvedValue({ ...runtime, latestSample: { simulated: true, heartRateBpm: 180, speedKmh: 4, steps: 200, oxygenSaturation: 98 }, prediction: { level: "high", title: "Riesgo alto", message: "Detenete", recommendedAction: "Descansar", factors: ["Pulso"], riskLabel: "alto", fatigue: "alta" } });
  const tree = await mount(Route); await press(tree, "Ver metricas del reloj"); expect(text(tree)).toContain("Metricas simuladas"); await press(tree, "Cerrar metricas del reloj");
  await press(tree, "Riesgo"); expect(wearable.createDevelopmentMetricSequence).toHaveBeenCalledWith("riesgo_fisiologico", 8);
  await press(tree, "Probar SOS (no se envía)"); expect(router.push).toHaveBeenLastCalledWith(expect.objectContaining({ pathname: "/confirmar-sos", params: expect.objectContaining({ simulated: "1" }) }));
});
test("online report is durably queued before sync with stable event identity", async () => {
  const tree = await mount(Report); await press(tree, "Alta"); await press(tree, "Derrumbe");
  await act(async () => tree.root.findAllByType(TextInput)[0].props.onChangeText("Paso bloqueado"));
  await press(tree, "Enviar reporte");
  expect(queue.enqueue).toHaveBeenCalledWith("trail_report", expect.objectContaining({
    trailId: 7, client_event_id: expect.stringMatching(/^[a-f0-9-]{36}$/), latitude: -41,
    longitude: -71, accuracy_meters: 5, severity: "Alta", details: "Paso bloqueado",
    observed_at: new Date(startedAt).toISOString(),
  }));
  expect(createTrailReport).not.toHaveBeenCalled();
  expect((queue.enqueue as jest.Mock).mock.invocationCallOrder[0]).toBeLessThan((queue.runSync as jest.Mock).mock.invocationCallOrder[0]);
  expect(router.replace).toHaveBeenCalledWith(expect.objectContaining({ params: expect.objectContaining({ pending: "1" }) }));
});

test.each(["offline", "server-error"])("terrain report is queued on %s and acknowledged only as pending", async (mode) => {
  if (mode === "offline") (queue.isOnline as jest.Mock).mockResolvedValue(false); else (createTrailReport as jest.Mock).mockRejectedValue(new Error("server"));
  const tree = await mount(Report); await press(tree, "Enviar reporte"); expect(queue.enqueue).toHaveBeenCalledWith("trail_report", expect.objectContaining({ trailId: 7, latitude: -41 })); expect(router.replace).toHaveBeenCalledWith(expect.objectContaining({ params: expect.objectContaining({ pending: "1" }) }));
});
test("a distant GPS fix cannot submit; a validated map choice can and local persistence failure remains visible", async () => {
  (useDeviceLocation as jest.Mock).mockReturnValue({ location: { ...gps, coordinate: [-42, -72], accuracy: 999 }, isLoading: false }); const tree = await mount(Report);
  await expect(press(tree, "Enviar reporte")).rejects.toThrow("disabled"); await press(tree, "Elegir en mapa");
  await act(async () => tree.root.findByType("TrailMap").props.onSelectionRejected(900)); expect(text(tree)).toContain("Elegi un punto");
  await act(async () => tree.root.findByType("TrailMap").props.onSelectCoordinate({ coordinate: [-41.001, -71], routeProgressMeters: 110 }));
  (queue.isOnline as jest.Mock).mockResolvedValue(false); (queue.enqueue as jest.Mock).mockRejectedValueOnce(new Error("Almacenamiento lleno")); await press(tree, "Enviar reporte"); expect(text(tree)).toContain("Almacenamiento lleno"); expect(router.replace).not.toHaveBeenCalled();
  await press(tree, "Enviar reporte"); expect(queue.enqueue).toHaveBeenLastCalledWith("trail_report", expect.objectContaining({ latitude: -41.001, accuracy_meters: null, route_progress_meters: 110 }));
});
