import * as Network from "expo-network";
import { getTrailEnvironmental as fetchEnvironmental } from "./api";
import { getOfflineMapByTrailId, refreshOfflineTrailEnvironmental } from "./offlineMaps";
import { verifiedEnvironmentalBatch } from "./environmentalGeometry";
import type { EnvironmentalBatch } from "../backend/src/contracts/environmental";
import type { Trail } from "../types";

export interface EnvironmentalContext {
  batch: EnvironmentalBatch | null;
  mode: "online" | "offline" | "cached";
  error: boolean;
}

export const getTrailEnvironmental = async (trail: Trail, offlineOnly = false): Promise<EnvironmentalContext> => {
  const local = await getOfflineMapByTrailId(trail.id).catch(() => null);
  const cached = local?.environmental
    ? await verifiedEnvironmentalBatch(local.environmental, trail).catch(() => null) : null;
  const network = offlineOnly ? { isConnected: false, isInternetReachable: false } : await Network.getNetworkStateAsync().catch(() => null);
  if (network?.isConnected === false || network?.isInternetReachable === false) {
    return { batch: cached, mode: "offline", error: !cached };
  }
  try {
    const fresh = await verifiedEnvironmentalBatch(await fetchEnvironmental(trail.id), trail);
    if (fresh.snapshots.every((s) => s.status === "error")) throw new Error("Environmental storage unavailable");
    if (local?.trail) await refreshOfflineTrailEnvironmental(trail, fresh).catch(() => undefined);
    return { batch: fresh, mode: "online", error: false };
  } catch {
    return { batch: cached, mode: "cached", error: true };
  }
};
