jest.mock("../api", () => ({ getTrailById: jest.fn(), getTrailReports: jest.fn(), getTrails: jest.fn() }));
jest.mock("../offlineMaps", () => ({ getOfflineMapByTrailId: jest.fn(), getOfflineMaps: jest.fn() }));
jest.mock("expo-network", () => ({ getNetworkStateAsync: jest.fn().mockResolvedValue({ isConnected: false }) }));
import * as api from "../api";
import * as local from "../offlineMaps";
import { getTrailById, getTrailReports, getTrails } from "../trailRepository";

test("detail and reports can use geometry even when imagery is incomplete", async () => {
  const trail = { id: 8, name: "Ruta descargada", route_coordinates: "[]" };
  (local.getOfflineMapByTrailId as jest.Mock).mockResolvedValue({ trail, reports: [{ id: 2 }], status: "incompleto" });
  (local.getOfflineMaps as jest.Mock).mockResolvedValue([{ trail }]);
  expect(await getTrailById(8)).toEqual(trail);
  expect(await getTrailReports(8)).toEqual([{ id: 2 }]);
  expect(await getTrails()).toEqual([trail]);
  expect(api.getTrailById).not.toHaveBeenCalled();
  expect(api.getTrails).not.toHaveBeenCalled();
});
