import { useEffect, useState } from "react";
import { Coordinate } from "../../services/geoUtils";
import { getOfflineTerrainGrid } from "../../services/offlineMaps";
import {
  TerrainGridData,
  createTerrainGridCoordinates,
  peekTerrainElevation,
} from "../../services/terrainElevation";
import { getTerrainTileGrid, peekTerrainTileGrid, type TerrainTileFetch } from "../../services/terrainTiles";

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
  fetchFn?: TerrainTileFetch
): Promise<TerrainElevationState> => {
  if (!createTerrainGridCoordinates(route)) {
    return { status: "unavailable", reason: "no-route" };
  }

  const cachedData = await (peekTerrainTileGrid(trailKey, route) ?? peekTerrainElevation(trailKey, route));
  if (cachedData) return { status: "ready", data: cachedData };

  const trailId = typeof trailKey === "number" ? trailKey : null;
  const saved = trailId === null
    ? null
    : await getOfflineTerrainGrid(trailId, route).catch(() => null);
  if (saved) {
    const target = createTerrainGridCoordinates(route)!;
    if (offline || saved.grid.size >= target.size) return { status: "ready", data: saved };
    // Keep older downloads usable if the higher-detail online request fails.
    const upgraded = await getTerrainTileGrid(trailKey, route, fetchFn);
    return { status: "ready", data: upgraded ?? saved };
  }
  if (offline) return { status: "unavailable", reason: "offline" };

  const data = await getTerrainTileGrid(trailKey, route, fetchFn);
  if (!data) return { status: "unavailable", reason: "provider-error" };

  // Online 3D uses the session cache; it does not enlarge downloaded 2D maps.
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
    }).catch(() => {
      if (active) setState({ status: "unavailable", reason: "provider-error" });
    });

    return () => {
      active = false;
    };
  }, [enabled, offline, trailKey, route]);

  return state;
}
