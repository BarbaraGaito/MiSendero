jest.mock("expo-crypto", () => ({ randomUUID: () => "c4caa5b2-5ebc-40ec-af77-01e1cbd1b4d0" }));
jest.mock("../deviceLocation", () => ({ getCurrentDeviceLocation: jest.fn().mockResolvedValue(null) }));
jest.mock("../routeTracking", () => ({ getLastRouteTrackingPoint: jest.fn().mockResolvedValue(null) }));
jest.mock("expo-network", () => ({ getNetworkStateAsync: jest.fn().mockResolvedValue({ isConnected: false }) }));
jest.mock("../trailRepository", () => ({ getTrailById: jest.fn().mockResolvedValue(null) }));
import { db, initDB } from "../../database/database";
import { clearAuthSession } from "../authSession";
import { buildEmergencyMessage, sendEmergencyAlert } from "../emergencyAlerts";
import { getEmergencyOperation } from "../syncQueue";
import { getLastRouteTrackingPoint } from "../routeTracking";
import { getTrailById } from "../trailRepository";
beforeEach(async () => { await initDB(); await clearAuthSession(); await db.runAsync("DELETE FROM pending_operations"); });

test("persists SOS without authentication or GPS and retries the same event without duplication", async () => {
  const first = await sendEmergencyAlert({ trailId: 2, startedAt: 1000 });
  const second = await sendEmergencyAlert({ trailId: 2, startedAt: 1000, eventId: first.eventId });
  expect(second.operationId).toBe(first.operationId);
  const row = await getEmergencyOperation(first.operationId);
  expect(row?.status).toBe("pending");
  expect(row?.userId).toBeNull();
  expect(row?.payload.latitude).toBeNull();
  expect(row?.payload.last_known_at).toBeNull();
  expect(first.message).toContain("Ubicación no disponible");
});
test("message marks coordinates as last known and includes their timestamp", () => {
  const message = buildEmergencyMessage({ latitude: -41, longitude: -71, timestamp: 1700000000000 });
  expect(message).toContain("Última ubicación");
  expect(message).toContain("Registrada:");
  expect(message).toContain("-41.00000, -71.00000");
});
test("never includes simulated coordinates in a real emergency message", async () => {
  (getLastRouteTrackingPoint as jest.Mock).mockResolvedValueOnce({ latitude: -41, longitude: -71, recordedAt: Date.now(), simulated: true });
  const result = await sendEmergencyAlert({ trailId: 1, startedAt: 1000 });
  expect((await getEmergencyOperation(result.operationId))?.payload.latitude).toBeNull();
});

test("persists the real trail name and start separately from the last known user location", async () => {
  (getTrailById as jest.Mock).mockResolvedValueOnce({
    id: 10, name: "Laguna del Tesoro - Aconquija", location: "Parque Nacional Aconquija, Tucuman",
    route_coordinates: "[[-27.3,-65.8],[-27.31,-65.81]]",
  });
  (getLastRouteTrackingPoint as jest.Mock).mockResolvedValueOnce({
    latitude: -27.305, longitude: -65.805, recordedAt: Date.now(), simulated: false,
  });
  const result = await sendEmergencyAlert({ trailId: 10, startedAt: 1000 });
  const saved = await getEmergencyOperation(result.operationId);
  expect(result.message).toContain("Sendero: Laguna del Tesoro - Aconquija");
  expect(result.message).toContain("Inicio del recorrido: -27.30000, -65.80000");
  expect(result.message).toContain("-27.30500, -65.80500");
  expect(result.message).not.toContain("Sendero ID");
  expect(saved?.payload.message_body).toBe(result.message);
  expect(saved?.payload.latitude).toBe(-27.305);
});
