jest.mock("../api", () => ({ getTrailById: jest.fn(), getTrailReports: jest.fn(), getTrails: jest.fn() }));
jest.mock("../offlineMaps", () => ({ getOfflineMapByTrailId: jest.fn(), getOfflineMaps: jest.fn(), refreshOfflineTrailElevation: jest.fn(), refreshOfflineTrailReports: jest.fn() }));
jest.mock("expo-network", () => ({ getNetworkStateAsync: jest.fn().mockResolvedValue({ isConnected: false }) }));
import * as api from "../api";
import * as local from "../offlineMaps";
import { getTrailById, getTrailReports, getTrails } from "../trailRepository";
import * as Network from "expo-network";

beforeEach(() => {
  jest.clearAllMocks();
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: false });
});

test("detail and reports can use geometry even when imagery is incomplete", async () => {
  const trail = { id: 8, name: "Ruta descargada", route_coordinates: "[]" };
  (local.getOfflineMapByTrailId as jest.Mock).mockResolvedValue({ trail, reports: [{ id: 2, created_at: new Date().toISOString() }], status: "incompleto" });
  (local.getOfflineMaps as jest.Mock).mockResolvedValue([{ trail }]);
  expect(await getTrailById(8)).toEqual(trail);
  expect(await getTrailReports(8)).toEqual([expect.objectContaining({ id: 2 })]);
  expect(await getTrails()).toEqual([trail]);
  expect(api.getTrailById).not.toHaveBeenCalled();
  expect(api.getTrails).not.toHaveBeenCalled();
});

test("upgrades a legacy downloaded route with real elevation while connected", async () => {
  const trail = { id: 8, route_coordinates: "[[1,2],[1,3]]" };
  const upgraded = { ...trail, elevation: { source: "Copernicus", points: [{ elevation_m: 200 }] } };
  (local.getOfflineMapByTrailId as jest.Mock).mockResolvedValue({ trail });
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: true, isInternetReachable: true });
  (api.getTrailById as jest.Mock).mockResolvedValue(upgraded);
  (local.refreshOfflineTrailElevation as jest.Mock).mockResolvedValue(upgraded);
  expect(await getTrailById(8)).toEqual(upgraded);
  expect(local.refreshOfflineTrailElevation).toHaveBeenCalledWith(upgraded);
});

test("online report refresh replaces the offline copy, including withdrawals and corrections", async () => {
  const trail = { id: 8 };
  const old = { id: 2, created_at: new Date().toISOString(), issue_summary: "Anterior" };
  (local.getOfflineMapByTrailId as jest.Mock).mockResolvedValue({ trail, reports: [old] });
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: true });
  (api.getTrailReports as jest.Mock).mockResolvedValue([]);
  expect(await getTrailReports(8)).toEqual([]);
  expect(local.refreshOfflineTrailReports).toHaveBeenCalledWith(8, []);
  (api.getTrailReports as jest.Mock).mockResolvedValue([{ ...old, issue_summary: "Corregido" }]);
  expect((await getTrailReports(8))[0].issue_summary).toBe("Corregido");
});

test("an elevation refresh failure retains the downloaded route", async () => {
  const trail = { id: 8, route_coordinates: "[[1,2],[1,3]]" };
  (local.getOfflineMapByTrailId as jest.Mock).mockResolvedValue({ trail });
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: true });
  (api.getTrailById as jest.Mock).mockRejectedValue(new Error("timeout"));
  expect(await getTrailById(8)).toEqual(trail);
});

test("a downloaded elevation profile needs no network", async () => {
  const trail = { id: 8, elevation: { source: "Copernicus" }, national_park: null };
  (local.getOfflineMapByTrailId as jest.Mock).mockResolvedValue({ trail });
  expect(await getTrailById(8)).toEqual(trail);
  expect(api.getTrailById).not.toHaveBeenCalled();
  expect(Network.getNetworkStateAsync).not.toHaveBeenCalled();
});

test("upgrades legacy downloaded metadata even when elevation already exists", async () => {
  const trail = { id: 8, elevation: { source: "Copernicus" } };
  const upgraded = { ...trail, national_park: { slug: "nahuel-huapi" } };
  (local.getOfflineMapByTrailId as jest.Mock).mockResolvedValue({ trail });
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: true });
  (api.getTrailById as jest.Mock).mockResolvedValue(upgraded);
  (local.refreshOfflineTrailElevation as jest.Mock).mockResolvedValue(upgraded);
  expect(await getTrailById(8)).toEqual(upgraded);
});

test("a national-park download with a formerly null profile receives the new institutional data", async () => {
  const trail = { id: 71, location: "Parque Nacional Iguazu, Misiones", elevation: { source: "Copernicus" }, national_park: null };
  const upgraded = { ...trail, national_park: { slug: "iguazu" }, national_park_slug: "iguazu" };
  (local.getOfflineMapByTrailId as jest.Mock).mockResolvedValue({ trail });
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: true });
  (api.getTrailById as jest.Mock).mockResolvedValue(upgraded);
  (local.refreshOfflineTrailElevation as jest.Mock).mockResolvedValue(upgraded);
  expect(await getTrailById(71)).toEqual(upgraded);
  expect(local.refreshOfflineTrailElevation).toHaveBeenCalledWith(upgraded);
});
