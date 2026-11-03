import { Coordinate, getDistanceMeters } from "../../services/geoUtils";
import type { TerrainElevationGrid } from "../../services/terrainElevation";

// La escena mide 14,4 unidades de lado. Una unidad equivale a la misma
// cantidad de metros en horizontal y en vertical: el relieve no se exagera.
export const TERRAIN_SCENE_HALF_SIZE = 7.2;
export const TERRAIN_MESH_SUBDIVISIONS = 4;
const ROUTE_MAX_SEGMENT_UNITS = 0.055;
const BOUNDS_EPSILON = 1e-9;

export type TerrainScenePoint = { x: number; y: number; z: number };

export type TerrainSceneWeather = {
  condition: string;
  rainProbability: number;
  temperatureC: number;
  windKmh?: number | null;
  windDirectionDegrees?: number | null;
  cloudCoverPercent?: number | null;
  isDay?: boolean | null;
  observedAt?: string | null;
  source?: string;
};

export type TerrainWeatherKind =
  | "clear"
  | "partly-cloudy"
  | "cloudy"
  | "rain"
  | "storm"
  | "fog"
  | "snow";

export type TerrainSceneModel = {
  grid: TerrainElevationGrid;
  metersPerUnit: number;
  minElevationMeters: number;
  maxElevationMeters: number;
  maxHeight: number;
  route: TerrainScenePoint[];
  routeDistancesMeters: number[];
};

export type TerrainMeshData = {
  verticesPerSide: number;
  positions: number[];
  relativeElevations: number[];
  uvs: number[];
  indices: number[];
};

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));

const isUsableGrid = (grid: TerrainElevationGrid) =>
  Number.isInteger(grid.size) &&
  grid.size >= 2 &&
  grid.elevationsMeters.length === grid.size * grid.size &&
  grid.elevationsMeters.every((elevation) => Number.isFinite(elevation)) &&
  grid.sideLengthMeters > 0 &&
  grid.bounds.north > grid.bounds.south &&
  grid.bounds.east > grid.bounds.west;

// Interpolacion bilineal entre las cuatro muestras reales del DEM que rodean
// la posicion (fila 0 = norte, columna 0 = oeste).
const interpolateGridElevation = (
  grid: TerrainElevationGrid,
  row: number,
  column: number
) => {
  const lastIndex = grid.size - 1;
  const row0 = clamp(Math.floor(row), 0, lastIndex);
  const column0 = clamp(Math.floor(column), 0, lastIndex);
  const row1 = Math.min(lastIndex, row0 + 1);
  const column1 = Math.min(lastIndex, column0 + 1);
  const rowRatio = clamp(row - row0, 0, 1);
  const columnRatio = clamp(column - column0, 0, 1);
  const at = (r: number, c: number) => grid.elevationsMeters[r * grid.size + c];
  const top = at(row0, column0) + (at(row0, column1) - at(row0, column0)) * columnRatio;
  const bottom = at(row1, column0) + (at(row1, column1) - at(row1, column0)) * columnRatio;

  return top + (bottom - top) * rowRatio;
};

export const getTerrainSceneHeight = (
  model: TerrainSceneModel,
  x: number,
  z: number
) => {
  const toGridIndex = (value: number) =>
    clamp((value + TERRAIN_SCENE_HALF_SIZE) / (TERRAIN_SCENE_HALF_SIZE * 2), 0, 1) *
    (model.grid.size - 1);
  const elevation = interpolateGridElevation(model.grid, toGridIndex(z), toGridIndex(x));

  return (elevation - model.minElevationMeters) / model.metersPerUnit;
};

export const coordinateToTerrainScenePoint = (
  model: TerrainSceneModel,
  coordinate: Coordinate
): TerrainScenePoint | null => {
  const { north, south, east, west } = model.grid.bounds;
  const columnRatio = (coordinate[1] - west) / (east - west);
  const rowRatio = (north - coordinate[0]) / (north - south);
  const isInside = (ratio: number) =>
    Number.isFinite(ratio) && ratio >= -BOUNDS_EPSILON && ratio <= 1 + BOUNDS_EPSILON;
  if (!isInside(columnRatio) || !isInside(rowRatio)) return null;

  const x = -TERRAIN_SCENE_HALF_SIZE + clamp(columnRatio, 0, 1) * TERRAIN_SCENE_HALF_SIZE * 2;
  const z = -TERRAIN_SCENE_HALF_SIZE + clamp(rowRatio, 0, 1) * TERRAIN_SCENE_HALF_SIZE * 2;

  return { x, y: getTerrainSceneHeight(model, x, z), z };
};

export const terrainScenePointToCoordinate = (
  model: TerrainSceneModel,
  point: Pick<TerrainScenePoint, "x" | "z">
): Coordinate | null => {
  const column = (point.x + TERRAIN_SCENE_HALF_SIZE) / (TERRAIN_SCENE_HALF_SIZE * 2);
  const row = (point.z + TERRAIN_SCENE_HALF_SIZE) / (TERRAIN_SCENE_HALF_SIZE * 2);
  if (![column, row].every(value => Number.isFinite(value) && value >= -BOUNDS_EPSILON && value <= 1 + BOUNDS_EPSILON)) return null;
  const { north, south, west, east } = model.grid.bounds;
  return [north - clamp(row, 0, 1) * (north - south), west + clamp(column, 0, 1) * (east - west)];
};

// Devuelve null si la grilla no es una grilla real completa o si algun punto
// de la ruta queda fuera de ella: en ese caso no se dibuja relieve.
export const buildTerrainSceneModel = (
  grid: TerrainElevationGrid,
  routePoints: readonly Coordinate[]
): TerrainSceneModel | null => {
  if (!isUsableGrid(grid) || routePoints.length < 2) return null;

  const minElevationMeters = Math.min(...grid.elevationsMeters);
  const maxElevationMeters = Math.max(...grid.elevationsMeters);
  const metersPerUnit = grid.sideLengthMeters / (TERRAIN_SCENE_HALF_SIZE * 2);
  const model: TerrainSceneModel = {
    grid,
    metersPerUnit,
    minElevationMeters,
    maxElevationMeters,
    maxHeight: (maxElevationMeters - minElevationMeters) / metersPerUnit,
    route: [],
    routeDistancesMeters: [],
  };

  for (const [index, coordinate] of routePoints.entries()) {
    const point = coordinateToTerrainScenePoint(model, coordinate);
    if (!point) return null;
    model.route.push(point);
    model.routeDistancesMeters.push(index === 0 ? 0 : model.routeDistancesMeters[index - 1] + getDistanceMeters(routePoints[index - 1], coordinate));
  }

  return model;
};

export const buildTerrainMeshData = (
  model: TerrainSceneModel,
  subdivisions = Math.min(TERRAIN_MESH_SUBDIVISIONS, Math.max(1, Math.floor(64 / (model.grid.size - 1))))
): TerrainMeshData => {
  const { grid } = model;
  const verticesPerSide = (grid.size - 1) * subdivisions + 1;
  const lastVertex = verticesPerSide - 1;
  const elevationRange = model.maxElevationMeters - model.minElevationMeters;
  const positions: number[] = [];
  const relativeElevations: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];

  for (let row = 0; row < verticesPerSide; row += 1) {
    for (let column = 0; column < verticesPerSide; column += 1) {
      const elevation = interpolateGridElevation(
        grid,
        row / subdivisions,
        column / subdivisions
      );
      const x = -TERRAIN_SCENE_HALF_SIZE + (column / lastVertex) * TERRAIN_SCENE_HALF_SIZE * 2;
      const z = -TERRAIN_SCENE_HALF_SIZE + (row / lastVertex) * TERRAIN_SCENE_HALF_SIZE * 2;

      positions.push(x, (elevation - model.minElevationMeters) / model.metersPerUnit, z);
      relativeElevations.push(
        elevationRange > 0 ? (elevation - model.minElevationMeters) / elevationRange : 0
      );
      uvs.push(column / lastVertex, 1 - row / lastVertex);
    }
  }

  for (let row = 0; row < lastVertex; row += 1) {
    for (let column = 0; column < lastVertex; column += 1) {
      const a = row * verticesPerSide + column;
      const b = a + 1;
      const c = a + verticesPerSide;
      const d = c + 1;

      indices.push(a, c, b, b, c, d);
    }
  }

  return { verticesPerSide, positions, relativeElevations, uvs, indices };
};

// Densifica el trazado real y apoya cada punto sobre la superficie del DEM.
export const drapeRouteOnTerrain = (
  model: TerrainSceneModel,
  maxSegmentLength = ROUTE_MAX_SEGMENT_UNITS
): TerrainScenePoint[] => {
  const draped: TerrainScenePoint[] = [];
  const pushPoint = (x: number, z: number) =>
    draped.push({ x, y: getTerrainSceneHeight(model, x, z), z });

  for (let index = 1; index < model.route.length; index += 1) {
    const start = model.route[index - 1];
    const end = model.route[index];
    const segmentLength = Math.hypot(end.x - start.x, end.z - start.z);
    const steps = Math.max(1, Math.ceil(segmentLength / maxSegmentLength));

    for (let step = 0; step < steps; step += 1) {
      const progress = step / steps;
      pushPoint(
        start.x + (end.x - start.x) * progress,
        start.z + (end.z - start.z) * progress
      );
    }
  }

  const last = model.route.at(-1);
  if (last) pushPoint(last.x, last.z);

  return draped;
};

// Sin pronostico real no hay efectos de clima.
export const getTerrainWeatherKind = (
  weather: TerrainSceneWeather | null | undefined
): TerrainWeatherKind | null => {
  if (!weather) return null;

  const normalized = weather.condition
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
  if (normalized.includes("nieve") || normalized.includes("nevada")) return "snow";
  if (normalized.includes("torment")) return "storm";
  if (normalized.includes("lluv") || normalized.includes("lloviz") || normalized.includes("chaparr")) return "rain";
  if (normalized.includes("niebla") || normalized.includes("neblina")) return "fog";
  if (normalized.includes("parcial") || normalized.includes("nubes")) return "partly-cloudy";
  if (normalized.includes("nubl") || normalized.includes("cubierto")) return "cloudy";
  if (normalized.includes("despejado") || normalized.includes("soleado")) return "clear";
  return null;
};
