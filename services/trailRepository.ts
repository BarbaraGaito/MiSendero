import * as api from "./api";
import { getOfflineMapByTrailId, getOfflineMaps } from "./offlineMaps";
import { Trail, TrailReport } from "../types";
import * as Network from "expo-network";

// Downloaded geometry is usable even if imagery is incomplete. Tile verification
// belongs to the map availability indicator, not the route/reporting workflow.
export const getTrailById = async (id: number): Promise<Trail> => {
  const local = await getOfflineMapByTrailId(id);
  if (local?.trail) return local.trail;
  return api.getTrailById(id);
};

export const getTrailReports = async (id: number): Promise<TrailReport[]> => {
  const local = await getOfflineMapByTrailId(id);
  if (local?.trail) return local.reports ?? [];
  return api.getTrailReports(id);
};

export const getTrails = async (): Promise<Trail[]> => {
  try {
    const network = await Network.getNetworkStateAsync().catch(() => null);
    if (network?.isConnected === false || network?.isInternetReachable === false) throw new Error("Sin conexión");
    return await api.getTrails();
  } catch (error) {
    const saved = (await getOfflineMaps()).flatMap((map) => map.trail ? [map.trail] : []);
    if (saved.length) return saved;
    throw error;
  }
};

export const getTrailWeather = async (id: number) => {
  const network = await Network.getNetworkStateAsync().catch(() => null);
  if (network?.isConnected === false || network?.isInternetReachable === false) return null;
  return api.getTrailWeather(id).catch(() => null);
};
