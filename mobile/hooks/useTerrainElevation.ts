import { useEffect, useState } from "react";
import { Coordinate } from "../../services/geoUtils";
import {
  backfillOfflineTerrainGrid,
  getOfflineTerrainGrid,
} from "../../services/offlineMaps";
import {
  ElevationFetch,
  TerrainGridData,
  createTerrainGridCoordinates,
  getTerrainElevation,
  peekTerrainElevation,
} from "../../services/terrainElevation";

export type TerrainUnavailableReason = "no-route" | "offline" | "provider-error";

export type TerrainElevationState =
  | { status: "loading" }
  | { status: "ready"; data: TerrainGridData }
  | { status: "unavailable"; reason: TerrainUnavailableReason };

// Nunca devuelve alturas de ejemplo: o hay datos reales del DEM o el relieve
// queda no disponible. Orden: cache de la sesion, grilla guardada con el mapa
// descargado y, solo con conexion, el proveedor.
export const loadTerrainElevationState = async (
  trailKey: string | number,
  route: readonly Coordinate[],
  offline: boolean,
  fetchFn?: ElevationFetch
): Promise<TerrainElevationState> => {
  if (!createTerrainGridCoordinates(route)) {
    return { status: "unavailable", reason: "no-route" };
  }

  const cachedData = await peekTerrainElevation(trailKey, route);
  if (cachedData) return { status: "ready", data: cachedData };

  const trailId = typeof trailKey === "number" ? trailKey : null;
  const saved = trailId === null
    ? null
    : await getOfflineTerrainGrid(trailId, route).catch(() => null);
  if (saved) return { status: "ready", data: saved };
  if (offline) return { status: "unavailable", reason: "offline" };

  const data = await getTerrainElevation(trailKey, route, { fetchFn });
  if (!data) return { status: "unavailable", reason: "provider-error" };

  if (trailId !== null) {
    await backfillOfflineTerrainGrid(trailId, route, data).catch(() => undefined);
  }
  return { status: "ready", data };
};

export function useTerrainElevation(
  trailKey: string | number,
  route: readonly Coordinate[],
  { enabled, offline }: { enabled: boolean; offline: boolean }
) {
  const [state, setState] = useState<TerrainElevationState>({ status: "loading" });

  useEffect(() => {
    if (!enabled) return;

    let active = true;
    setState({ status: "loading" });
    loadTerrainElevationState(trailKey, route, offline).then((next) => {
      if (active) setState(next);
    });

    return () => {
      active = false;
    };
  }, [enabled, offline, trailKey, route]);

  return state;
}
