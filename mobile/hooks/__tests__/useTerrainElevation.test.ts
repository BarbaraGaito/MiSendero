// Sin mapas descargados: la grilla persistida se prueba en
// services/__tests__/offlineTerrainGrid.test.ts con SQLite real.
jest.mock("../../../services/offlineMaps", () => ({
  getOfflineTerrainGrid: jest.fn().mockResolvedValue(null),
  backfillOfflineTerrainGrid: jest.fn().mockResolvedValue(undefined),
}));

import type { Coordinate } from "../../../services/geoUtils";
import {
  ElevationFetch,
  TERRAIN_GRID_SIZE,
  clearTerrainElevationCache,
} from "../../../services/terrainElevation";
import * as terrainElevation from "../../../services/terrainElevation";
import { mount } from "../../../testing/mobileHarness";
import { loadTerrainElevationState, TerrainElevationState, useTerrainElevation } from "../useTerrainElevation";

const route: Coordinate[] = [
  [-41.01, -71.01],
  [-41, -71],
];

const okFetch = () =>
  jest.fn(async (input: string) => {
    const count = new URL(input).searchParams.get("latitude")!.split(",").length;
    return {
      ok: true,
      status: 200,
      json: async () => ({ elevation: Array.from({ length: count }, (_, index) => 800 + index) }),
    };
  }) as ElevationFetch;

test("the terrain hook handles an unexpected rejected load as unavailable", async () => {
  jest.spyOn(terrainElevation, "peekTerrainElevation").mockRejectedValueOnce(new Error("Cache unavailable"));
  let state: TerrainElevationState | undefined;
  const Probe = () => {
    state = useTerrainElevation(1, route, { enabled: true, offline: false });
    return null;
  };
  await mount(Probe);
  expect(state).toEqual({ status: "unavailable", reason: "provider-error" });
});

describe("loadTerrainElevationState", () => {
  beforeEach(() => {
    clearTerrainElevationCache();
  });

  test("sin trazado no consulta y queda no disponible", async () => {
    const fetchFn = okFetch();

    await expect(loadTerrainElevationState(1, [], false, fetchFn)).resolves.toEqual({
      status: "unavailable",
      reason: "no-route",
    });
    await expect(loadTerrainElevationState(1, [route[0]], false, fetchFn)).resolves.toEqual({
      status: "unavailable",
      reason: "no-route",
    });
    expect(fetchFn).not.toHaveBeenCalled();
  });

  test("con conexion devuelve la grilla real del proveedor", async () => {
    const state = await loadTerrainElevationState(1, route, false, okFetch());

    expect(state.status).toBe("ready");
    if (state.status !== "ready") return;
    expect(state.data.grid.elevationsMeters).toHaveLength(TERRAIN_GRID_SIZE ** 2);
    expect(state.data.source.dataset).toBe("Copernicus DEM GLO-90");
  });

  test("un error del proveedor no se reemplaza por alturas de ejemplo", async () => {
    const fetchFn = jest.fn(async () => ({
      ok: false,
      status: 503,
      json: async () => ({}),
    })) as ElevationFetch;

    await expect(loadTerrainElevationState(1, route, false, fetchFn)).resolves.toEqual({
      status: "unavailable",
      reason: "provider-error",
    });
  });

  test("sin conexion solo usa el relieve ya consultado y no llama al proveedor", async () => {
    const offlineFetch = okFetch();

    await expect(loadTerrainElevationState(1, route, true, offlineFetch)).resolves.toEqual({
      status: "unavailable",
      reason: "offline",
    });

    const online = await loadTerrainElevationState(1, route, false, okFetch());
    const offline = await loadTerrainElevationState(1, route, true, offlineFetch);

    expect(offline).toEqual(online);
    expect(offline.status).toBe("ready");
    expect(offlineFetch).not.toHaveBeenCalled();
  });
});
