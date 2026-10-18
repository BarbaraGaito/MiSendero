import { Coordinate, getDistanceMeters } from "./geoUtils";

export const OPEN_METEO_ELEVATION_URL =
  "https://api.open-meteo.com/v1/elevation";
export const OPEN_METEO_ELEVATION_ATTRIBUTION =
  "Elevación: Open-Meteo · Copernicus DEM GLO-90 · © DLR e.V. (2010–2014), Airbus Defence and Space GmbH (2014–2018); COPERNICUS, Unión Europea y ESA. Derechos reservados.";
export const TERRAIN_DEM_RESOLUTION_METERS = 90;
export const TERRAIN_GRID_SIZE = 17;
export const TERRAIN_PROFILE_MIN_POINTS = 32;
export const TERRAIN_PROFILE_MAX_POINTS = 96;
export const TERRAIN_ELEVATION_BATCH_SIZE = 100;

const EARTH_RADIUS_METERS = 6_371_000;
const PROFILE_TARGET_SPACING_METERS = TERRAIN_DEM_RESOLUTION_METERS;
const MIN_GRID_SIDE_METERS =
  (TERRAIN_GRID_SIZE - 1) * TERRAIN_DEM_RESOLUTION_METERS;
const GRID_PADDING_METERS = TERRAIN_DEM_RESOLUTION_METERS * 2;
const MIN_GRADE_BASELINE_METERS = TERRAIN_DEM_RESOLUTION_METERS;

export type TerrainDifficultyLevel =
  | "suave"
  | "moderado"
  | "exigente"
  | "extremo";

export type TerrainDirection = "ascenso" | "descenso" | "llano";

export const TERRAIN_DIFFICULTY_COLORS: Record<
  TerrainDifficultyLevel,
  string
> = {
  suave: "#2E9D63",
  moderado: "#D9A72E",
  exigente: "#E36B2C",
  extremo: "#C83A3A",
};

export type SampledRoutePoint = {
  coordinate: Coordinate;
  distanceMeters: number;
};

export type ElevationProfilePoint = SampledRoutePoint & {
  rawElevationMeters: number;
  elevationMeters: number;
};

export type TerrainSegment = {
  startIndex: number;
  endIndex: number;
  startCoordinate: Coordinate;
  endCoordinate: Coordinate;
  startDistanceMeters: number;
  endDistanceMeters: number;
  distanceMeters: number;
  startElevationMeters: number;
  endElevationMeters: number;
  elevationChangeMeters: number;
  gradePercent: number;
  level: TerrainDifficultyLevel;
  direction: TerrainDirection;
  color: string;
};

export type TerrainSector = {
  startSegmentIndex: number;
  endSegmentIndex: number;
  startCoordinate: Coordinate;
  endCoordinate: Coordinate;
  startDistanceMeters: number;
  endDistanceMeters: number;
  distanceMeters: number;
  elevationChangeMeters: number;
  averageGradePercent: number;
  maxGradePercent: number;
  level: TerrainDifficultyLevel;
  direction: TerrainDirection;
  color: string;
};

export type ElevationStatistics = {
  totalDistanceMeters: number;
  elevationGainMeters: number;
  elevationLossMeters: number;
  minElevationMeters: number;
  maxElevationMeters: number;
  maxGradePercent: number;
};

export type TerrainGridBounds = {
  north: number;
  south: number;
  east: number;
  west: number;
};

export type TerrainGridGeometry = {
  size: number;
  center: Coordinate;
  bounds: TerrainGridBounds;
  sideLengthMeters: number;
  cellSizeMeters: number;
  coordinates: Coordinate[];
};

export type TerrainElevationGrid = Omit<TerrainGridGeometry, "coordinates"> & {
  elevationsMeters: number[];
  minElevationMeters: number;
  maxElevationMeters: number;
};

export type TerrainElevationSource = {
  provider: "Open-Meteo";
  dataset: "Copernicus DEM GLO-90";
  resolutionMeters: 90;
  endpoint: string;
  attribution: string;
  fetchedAt: string;
};

export type TerrainElevationData = {
  profile: ElevationProfilePoint[];
  statistics: ElevationStatistics;
  segments: TerrainSegment[];
  sectors: TerrainSector[];
  grid: TerrainElevationGrid;
  source: TerrainElevationSource;
};

// Lo que usa la vista 3D: la grilla real del DEM y su fuente.
export type TerrainGridData = Pick<TerrainElevationData, "grid" | "source">;

export type ElevationFetch = (
  input: string,
  init?: { signal?: AbortSignal }
) => Promise<{
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}>;

export type TerrainElevationOptions = {
  fetchFn?: ElevationFetch;
  signal?: AbortSignal;
  forceRefresh?: boolean;
  now?: () => Date;
};

export class TerrainElevationError extends Error {
  constructor(
    public readonly code:
      | "invalid-route"
      | "request-failed"
      | "invalid-response",
    message: string,
    public readonly status?: number
  ) {
    super(message);
    this.name = "TerrainElevationError";
  }
}

const elevationCache = new Map<string, Promise<TerrainElevationData | null>>();

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));

const round = (value: number, digits = 1) => {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
};

const isValidCoordinate = (coordinate: Coordinate) =>
  Array.isArray(coordinate) &&
  coordinate.length >= 2 &&
  Number.isFinite(coordinate[0]) &&
  Number.isFinite(coordinate[1]) &&
  coordinate[0] >= -90 &&
  coordinate[0] <= 90 &&
  coordinate[1] >= -180 &&
  coordinate[1] <= 180;

const normalizeLongitude = (longitude: number) => {
  if (longitude > 180) return longitude - 360;
  if (longitude < -180) return longitude + 360;
  return longitude;
};

const interpolateCoordinate = (
  from: Coordinate,
  to: Coordinate,
  ratio: number
): Coordinate => {
  let longitudeDelta = to[1] - from[1];
  if (longitudeDelta > 180) longitudeDelta -= 360;
  if (longitudeDelta < -180) longitudeDelta += 360;

  return [
    from[0] + (to[0] - from[0]) * ratio,
    normalizeLongitude(from[1] + longitudeDelta * ratio),
  ];
};

const getUsableRoute = (route: readonly Coordinate[]) => {
  if (route.length < 2 || route.some((point) => !isValidCoordinate(point))) {
    return [];
  }

  return route.reduce<Coordinate[]>((points, point) => {
    const previous = points.at(-1);
    if (!previous || getDistanceMeters(previous, point) >= 0.01) {
      points.push([point[0], point[1]]);
    }
    return points;
  }, []);
};

export const sampleRouteByDistance = (
  route: readonly Coordinate[],
  options: {
    minPoints?: number;
    maxPoints?: number;
    targetSpacingMeters?: number;
  } = {}
): SampledRoutePoint[] => {
  const usableRoute = getUsableRoute(route);
  if (usableRoute.length < 2) return [];

  const minPoints = clamp(
    Math.round(options.minPoints ?? TERRAIN_PROFILE_MIN_POINTS),
    2,
    TERRAIN_PROFILE_MAX_POINTS
  );
  const maxPoints = clamp(
    Math.round(options.maxPoints ?? TERRAIN_PROFILE_MAX_POINTS),
    minPoints,
    TERRAIN_PROFILE_MAX_POINTS
  );
  const targetSpacingMeters = Math.max(
    1,
    options.targetSpacingMeters ?? PROFILE_TARGET_SPACING_METERS
  );
  const cumulativeDistances = [0];

  for (let index = 1; index < usableRoute.length; index += 1) {
    cumulativeDistances.push(
      cumulativeDistances[index - 1] +
        getDistanceMeters(usableRoute[index - 1], usableRoute[index])
    );
  }

  const totalDistanceMeters = cumulativeDistances.at(-1) ?? 0;
  if (totalDistanceMeters <= 0) return [];

  const sampleCount = clamp(
    Math.ceil(totalDistanceMeters / targetSpacingMeters) + 1,
    minPoints,
    maxPoints
  );
  const samples: SampledRoutePoint[] = [];
  let segmentIndex = 0;

  for (let sampleIndex = 0; sampleIndex < sampleCount; sampleIndex += 1) {
    const targetDistance =
      sampleIndex === sampleCount - 1
        ? totalDistanceMeters
        : (sampleIndex / (sampleCount - 1)) * totalDistanceMeters;

    while (
      segmentIndex < cumulativeDistances.length - 2 &&
      cumulativeDistances[segmentIndex + 1] < targetDistance
    ) {
      segmentIndex += 1;
    }

    const segmentStartDistance = cumulativeDistances[segmentIndex];
    const segmentEndDistance = cumulativeDistances[segmentIndex + 1];
    const segmentDistance = segmentEndDistance - segmentStartDistance;
    const ratio =
      segmentDistance > 0
        ? (targetDistance - segmentStartDistance) / segmentDistance
        : 0;

    samples.push({
      coordinate: interpolateCoordinate(
        usableRoute[segmentIndex],
        usableRoute[segmentIndex + 1],
        clamp(ratio, 0, 1)
      ),
      distanceMeters: targetDistance,
    });
  }

  return samples;
};

const getRouteOrigin = (route: readonly Coordinate[]): Coordinate => {
  const totals = route.reduce(
    (result, coordinate) => ({
      latitude: result.latitude + coordinate[0],
      longitude: result.longitude + coordinate[1],
    }),
    { latitude: 0, longitude: 0 }
  );

  return [totals.latitude / route.length, totals.longitude / route.length];
};

const toLocalMeters = (coordinate: Coordinate, origin: Coordinate) => {
  const latitudeRadians = (origin[0] * Math.PI) / 180;

  return {
    x:
      ((coordinate[1] - origin[1]) *
        Math.PI *
        EARTH_RADIUS_METERS *
        Math.cos(latitudeRadians)) /
      180,
    y:
      ((coordinate[0] - origin[0]) * Math.PI * EARTH_RADIUS_METERS) /
      180,
  };
};

const fromLocalMeters = (
  point: { x: number; y: number },
  origin: Coordinate
): Coordinate => {
  const metersPerLatitudeDegree = (Math.PI * EARTH_RADIUS_METERS) / 180;
  const metersPerLongitudeDegree =
    metersPerLatitudeDegree * Math.cos((origin[0] * Math.PI) / 180);

  return [
    origin[0] + point.y / metersPerLatitudeDegree,
    normalizeLongitude(origin[1] + point.x / metersPerLongitudeDegree),
  ];
};

export const createTerrainGridCoordinates = (
  route: readonly Coordinate[],
  size = TERRAIN_GRID_SIZE
): TerrainGridGeometry | null => {
  const usableRoute = getUsableRoute(route);
  if (usableRoute.length < 2 || size < 2 || !Number.isInteger(size)) return null;

  const origin = getRouteOrigin(usableRoute);
  if (Math.abs(origin[0]) > 89) return null;

  const localRoute = usableRoute.map((coordinate) =>
    toLocalMeters(coordinate, origin)
  );
  const minX = Math.min(...localRoute.map((point) => point.x));
  const maxX = Math.max(...localRoute.map((point) => point.x));
  const minY = Math.min(...localRoute.map((point) => point.y));
  const maxY = Math.max(...localRoute.map((point) => point.y));
  const routeSpanMeters = Math.max(maxX - minX, maxY - minY);
  const sideLengthMeters = Math.max(
    MIN_GRID_SIDE_METERS,
    routeSpanMeters + Math.max(GRID_PADDING_METERS * 2, routeSpanMeters * 0.2)
  );
  const centerLocal = {
    x: (minX + maxX) / 2,
    y: (minY + maxY) / 2,
  };
  const halfSide = sideLengthMeters / 2;
  const cellSizeMeters = sideLengthMeters / (size - 1);
  const coordinates: Coordinate[] = [];

  for (let row = 0; row < size; row += 1) {
    const y = centerLocal.y + halfSide - row * cellSizeMeters;

    for (let column = 0; column < size; column += 1) {
      const x = centerLocal.x - halfSide + column * cellSizeMeters;
      coordinates.push(fromLocalMeters({ x, y }, origin));
    }
  }

  const northWest = coordinates[0];
  const southEast = coordinates.at(-1)!;

  return {
    size,
    center: fromLocalMeters(centerLocal, origin),
    bounds: {
      north: northWest[0],
      south: southEast[0],
      west: northWest[1],
      east: southEast[1],
    },
    sideLengthMeters,
    cellSizeMeters,
    coordinates,
  };
};

export const smoothElevationSeries = (
  elevationsMeters: readonly number[],
  radius = 2
) => {
  if (
    elevationsMeters.some((elevation) => !Number.isFinite(elevation)) ||
    radius <= 0 ||
    elevationsMeters.length < 3
  ) {
    return [...elevationsMeters];
  }

  const safeRadius = Math.max(1, Math.floor(radius));

  return elevationsMeters.map((_, index) => {
    let weightedTotal = 0;
    let totalWeight = 0;

    for (
      let sampleIndex = Math.max(0, index - safeRadius);
      sampleIndex <= Math.min(elevationsMeters.length - 1, index + safeRadius);
      sampleIndex += 1
    ) {
      const weight = safeRadius + 1 - Math.abs(sampleIndex - index);
      weightedTotal += elevationsMeters[sampleIndex] * weight;
      totalWeight += weight;
    }

    return weightedTotal / totalWeight;
  });
};

export const buildElevationProfile = (
  sampledRoute: readonly SampledRoutePoint[],
  rawElevationsMeters: readonly number[]
): ElevationProfilePoint[] => {
  if (
    sampledRoute.length < 2 ||
    sampledRoute.length !== rawElevationsMeters.length ||
    rawElevationsMeters.some((elevation) => !Number.isFinite(elevation))
  ) {
    return [];
  }

  const smoothedElevations = smoothElevationSeries(rawElevationsMeters);

  return sampledRoute.map((sample, index) => ({
    coordinate: sample.coordinate,
    distanceMeters: sample.distanceMeters,
    rawElevationMeters: rawElevationsMeters[index],
    elevationMeters: smoothedElevations[index],
  }));
};

export const classifyTerrainDifficulty = (
  gradePercent: number
): TerrainDifficultyLevel => {
  const absoluteGrade = Math.abs(gradePercent);
  if (absoluteGrade < 8) return "suave";
  if (absoluteGrade < 15) return "moderado";
  if (absoluteGrade < 25) return "exigente";
  return "extremo";
};

const getTerrainDirection = (gradePercent: number): TerrainDirection => {
  if (gradePercent > 1) return "ascenso";
  if (gradePercent < -1) return "descenso";
  return "llano";
};

const interpolateProfileElevation = (
  profile: readonly ElevationProfilePoint[],
  targetDistanceMeters: number
) => {
  const first = profile[0];
  const last = profile.at(-1)!;
  if (targetDistanceMeters <= first.distanceMeters) return first.elevationMeters;
  if (targetDistanceMeters >= last.distanceMeters) return last.elevationMeters;

  let upperIndex = 1;
  while (
    upperIndex < profile.length - 1 &&
    profile[upperIndex].distanceMeters < targetDistanceMeters
  ) {
    upperIndex += 1;
  }

  const lower = profile[upperIndex - 1];
  const upper = profile[upperIndex];
  const span = upper.distanceMeters - lower.distanceMeters;
  const ratio = span > 0 ? (targetDistanceMeters - lower.distanceMeters) / span : 0;

  return lower.elevationMeters +
    (upper.elevationMeters - lower.elevationMeters) * ratio;
};

const getStableGradePercent = (
  profile: readonly ElevationProfilePoint[],
  segmentIndex: number
) => {
  const first = profile[0];
  const last = profile.at(-1)!;
  const segmentStart = profile[segmentIndex];
  const segmentEnd = profile[segmentIndex + 1];
  const centerDistance =
    (segmentStart.distanceMeters + segmentEnd.distanceMeters) / 2;
  const halfBaseline = MIN_GRADE_BASELINE_METERS / 2;
  const startDistance = Math.max(
    first.distanceMeters,
    centerDistance - halfBaseline
  );
  const endDistance = Math.min(last.distanceMeters, centerDistance + halfBaseline);
  const horizontalDistance = endDistance - startDistance;

  if (horizontalDistance <= 0) return 0;

  const startElevation = interpolateProfileElevation(profile, startDistance);
  const endElevation = interpolateProfileElevation(profile, endDistance);
  return ((endElevation - startElevation) / horizontalDistance) * 100;
};

export const buildTerrainSegments = (
  profile: readonly ElevationProfilePoint[]
): TerrainSegment[] => {
  if (profile.length < 2) return [];

  return profile.slice(0, -1).map((start, index) => {
    const end = profile[index + 1];
    const distanceMeters = end.distanceMeters - start.distanceMeters;
    const elevationChangeMeters = end.elevationMeters - start.elevationMeters;
    const gradePercent = round(getStableGradePercent(profile, index), 1);
    const level = classifyTerrainDifficulty(gradePercent);

    return {
      startIndex: index,
      endIndex: index + 1,
      startCoordinate: start.coordinate,
      endCoordinate: end.coordinate,
      startDistanceMeters: start.distanceMeters,
      endDistanceMeters: end.distanceMeters,
      distanceMeters,
      startElevationMeters: start.elevationMeters,
      endElevationMeters: end.elevationMeters,
      elevationChangeMeters,
      gradePercent,
      level,
      direction: getTerrainDirection(gradePercent),
      color: TERRAIN_DIFFICULTY_COLORS[level],
    };
  });
};

const createSector = (segment: TerrainSegment): TerrainSector => ({
  startSegmentIndex: segment.startIndex,
  endSegmentIndex: segment.startIndex,
  startCoordinate: segment.startCoordinate,
  endCoordinate: segment.endCoordinate,
  startDistanceMeters: segment.startDistanceMeters,
  endDistanceMeters: segment.endDistanceMeters,
  distanceMeters: segment.distanceMeters,
  elevationChangeMeters: segment.elevationChangeMeters,
  averageGradePercent: segment.gradePercent,
  maxGradePercent: Math.abs(segment.gradePercent),
  level: segment.level,
  direction: segment.direction,
  color: segment.color,
});

export const buildTerrainSectors = (
  segments: readonly TerrainSegment[]
): TerrainSector[] => {
  const sectors: TerrainSector[] = [];

  segments.forEach((segment) => {
    const current = sectors.at(-1);
    if (
      !current ||
      current.level !== segment.level ||
      current.direction !== segment.direction
    ) {
      sectors.push(createSector(segment));
      return;
    }

    const previousDistance = current.distanceMeters;
    const nextDistance = previousDistance + segment.distanceMeters;
    current.averageGradePercent =
      nextDistance > 0
        ? (current.averageGradePercent * previousDistance +
            segment.gradePercent * segment.distanceMeters) /
          nextDistance
        : 0;
    current.endSegmentIndex = segment.startIndex;
    current.endCoordinate = segment.endCoordinate;
    current.endDistanceMeters = segment.endDistanceMeters;
    current.distanceMeters = nextDistance;
    current.elevationChangeMeters += segment.elevationChangeMeters;
    current.maxGradePercent = Math.max(
      current.maxGradePercent,
      Math.abs(segment.gradePercent)
    );
  });

  return sectors.map((sector) => ({
    ...sector,
    distanceMeters: round(sector.distanceMeters),
    elevationChangeMeters: round(sector.elevationChangeMeters),
    averageGradePercent: round(sector.averageGradePercent, 1),
    maxGradePercent: round(sector.maxGradePercent, 1),
  }));
};

export const calculateElevationStatistics = (
  profile: readonly ElevationProfilePoint[],
  segments: readonly TerrainSegment[] = buildTerrainSegments(profile)
): ElevationStatistics | null => {
  if (profile.length < 2) return null;

  let elevationGainMeters = 0;
  let elevationLossMeters = 0;

  for (let index = 1; index < profile.length; index += 1) {
    const difference =
      profile[index].elevationMeters - profile[index - 1].elevationMeters;
    if (difference > 0) elevationGainMeters += difference;
    if (difference < 0) elevationLossMeters += Math.abs(difference);
  }

  const elevations = profile.map((point) => point.elevationMeters);

  return {
    totalDistanceMeters: round(
      profile.at(-1)!.distanceMeters - profile[0].distanceMeters
    ),
    elevationGainMeters: round(elevationGainMeters),
    elevationLossMeters: round(elevationLossMeters),
    minElevationMeters: round(Math.min(...elevations)),
    maxElevationMeters: round(Math.max(...elevations)),
    maxGradePercent: round(
      segments.reduce(
        (maximum, segment) => Math.max(maximum, Math.abs(segment.gradePercent)),
        0
      ),
      1
    ),
  };
};

const parseElevationResponse = (
  value: unknown,
  expectedCount: number
): number[] => {
  if (!value || typeof value !== "object" || !("elevation" in value)) {
    throw new TerrainElevationError(
      "invalid-response",
      "La respuesta de elevacion no contiene datos utilizables."
    );
  }

  const elevation = (value as { elevation?: unknown }).elevation;
  if (
    !Array.isArray(elevation) ||
    elevation.length !== expectedCount ||
    elevation.some((item) => typeof item !== "number" || !Number.isFinite(item))
  ) {
    throw new TerrainElevationError(
      "invalid-response",
      "La respuesta de elevacion esta incompleta o contiene valores invalidos."
    );
  }

  return elevation as number[];
};

export const fetchElevationsForCoordinates = async (
  coordinates: readonly Coordinate[],
  options: Pick<TerrainElevationOptions, "fetchFn" | "signal"> = {}
) => {
  if (coordinates.some((coordinate) => !isValidCoordinate(coordinate))) {
    throw new TerrainElevationError(
      "invalid-route",
      "No se pueden consultar coordenadas invalidas."
    );
  }

  if (coordinates.length === 0) return [];

  const fetchFn: ElevationFetch =
    options.fetchFn ??
    ((input, init) => fetch(input, { signal: init?.signal }));
  const elevations: number[] = [];

  for (
    let start = 0;
    start < coordinates.length;
    start += TERRAIN_ELEVATION_BATCH_SIZE
  ) {
    const batch = coordinates.slice(
      start,
      start + TERRAIN_ELEVATION_BATCH_SIZE
    );
    const latitude = batch.map((coordinate) => coordinate[0].toFixed(6)).join(",");
    const longitude = batch.map((coordinate) => coordinate[1].toFixed(6)).join(",");
    const url = `${OPEN_METEO_ELEVATION_URL}?latitude=${encodeURIComponent(
      latitude
    )}&longitude=${encodeURIComponent(longitude)}`;

    let response: Awaited<ReturnType<ElevationFetch>>;
    try {
      response = await fetchFn(url, { signal: options.signal });
    } catch {
      throw new TerrainElevationError(
        "request-failed",
        "No pudimos cargar las alturas del recorrido. Intentá nuevamente."
      );
    }

    if (!response.ok) {
      throw new TerrainElevationError(
        "request-failed",
        "No pudimos cargar las alturas del recorrido. Intentá nuevamente más tarde.",
        response.status
      );
    }

    const body = await response.json().catch(() => null);
    elevations.push(...parseElevationResponse(body, batch.length));
  }

  return elevations;
};

const buildElevationGrid = (
  geometry: TerrainGridGeometry,
  elevationsMeters: readonly number[]
): TerrainElevationGrid | null => {
  if (
    geometry.coordinates.length !== elevationsMeters.length ||
    elevationsMeters.some((elevation) => !Number.isFinite(elevation))
  ) {
    return null;
  }

  return {
    size: geometry.size,
    center: geometry.center,
    bounds: geometry.bounds,
    sideLengthMeters: geometry.sideLengthMeters,
    cellSizeMeters: geometry.cellSizeMeters,
    elevationsMeters: [...elevationsMeters],
    minElevationMeters: Math.min(...elevationsMeters),
    maxElevationMeters: Math.max(...elevationsMeters),
  };
};

export const sampleTerrainGridElevation = (
  grid: TerrainElevationGrid,
  coordinate: Coordinate
): number | null => {
  if (
    !isValidCoordinate(coordinate) ||
    grid.size < 2 ||
    grid.elevationsMeters.length !== grid.size * grid.size ||
    grid.elevationsMeters.some((elevation) => !Number.isFinite(elevation))
  ) {
    return null;
  }

  const { north, south, east, west } = grid.bounds;
  const latitudeSpan = north - south;
  const longitudeSpan = east - west;
  if (latitudeSpan <= 0 || longitudeSpan <= 0) return null;

  const epsilon = 1e-9;
  if (
    coordinate[0] > north + epsilon ||
    coordinate[0] < south - epsilon ||
    coordinate[1] < west - epsilon ||
    coordinate[1] > east + epsilon
  ) {
    return null;
  }

  const columnPosition =
    ((coordinate[1] - west) / longitudeSpan) * (grid.size - 1);
  const rowPosition =
    ((north - coordinate[0]) / latitudeSpan) * (grid.size - 1);
  const column0 = clamp(Math.floor(columnPosition), 0, grid.size - 1);
  const row0 = clamp(Math.floor(rowPosition), 0, grid.size - 1);
  const column1 = Math.min(grid.size - 1, column0 + 1);
  const row1 = Math.min(grid.size - 1, row0 + 1);
  const columnRatio = clamp(columnPosition - column0, 0, 1);
  const rowRatio = clamp(rowPosition - row0, 0, 1);
  const value00 = grid.elevationsMeters[row0 * grid.size + column0];
  const value10 = grid.elevationsMeters[row0 * grid.size + column1];
  const value01 = grid.elevationsMeters[row1 * grid.size + column0];
  const value11 = grid.elevationsMeters[row1 * grid.size + column1];
  const top = value00 + (value10 - value00) * columnRatio;
  const bottom = value01 + (value11 - value01) * columnRatio;

  return top + (bottom - top) * rowRatio;
};

export const loadTerrainElevation = async (
  route: readonly Coordinate[],
  options: Omit<TerrainElevationOptions, "forceRefresh"> = {}
): Promise<TerrainElevationData | null> => {
  const sampledRoute = sampleRouteByDistance(route);
  const gridGeometry = createTerrainGridCoordinates(route);
  if (sampledRoute.length < 2 || !gridGeometry) return null;

  try {
    const allCoordinates = [
      ...sampledRoute.map((sample) => sample.coordinate),
      ...gridGeometry.coordinates,
    ];
    const allElevations = await fetchElevationsForCoordinates(allCoordinates, options);
    const profileElevations = allElevations.slice(0, sampledRoute.length);
    const gridElevations = allElevations.slice(sampledRoute.length);
    const profile = buildElevationProfile(sampledRoute, profileElevations);
    const grid = buildElevationGrid(gridGeometry, gridElevations);
    if (profile.length < 2 || !grid) return null;

    const segments = buildTerrainSegments(profile);
    const statistics = calculateElevationStatistics(profile, segments);
    if (!statistics) return null;

    return {
      profile,
      statistics,
      segments,
      sectors: buildTerrainSectors(segments),
      grid,
      source: {
        provider: "Open-Meteo",
        dataset: "Copernicus DEM GLO-90",
        resolutionMeters: TERRAIN_DEM_RESOLUTION_METERS,
        endpoint: OPEN_METEO_ELEVATION_URL,
        attribution: OPEN_METEO_ELEVATION_ATTRIBUTION,
        fetchedAt: (options.now?.() ?? new Date()).toISOString(),
      },
    };
  } catch {
    return null;
  }
};

export const buildTerrainElevationCacheKey = (
  trailKey: string | number,
  route: readonly Coordinate[]
) => {
  let hash = 2_166_136_261;
  const serializedRoute = route
    .map((coordinate) => `${coordinate[0].toFixed(6)},${coordinate[1].toFixed(6)}`)
    .join(";");

  for (let index = 0; index < serializedRoute.length; index += 1) {
    hash ^= serializedRoute.charCodeAt(index);
    hash = Math.imul(hash, 16_777_619);
  }

  return `${String(trailKey)}:${route.length}:${(hash >>> 0).toString(16)}`;
};

export const clearTerrainElevationCache = (trailKey?: string | number) => {
  if (trailKey === undefined) {
    elevationCache.clear();
    return;
  }

  const prefix = `${String(trailKey)}:`;
  Array.from(elevationCache.keys()).forEach((key) => {
    if (key.startsWith(prefix)) elevationCache.delete(key);
  });
};

// Solo lee el cache en memoria: sin conexion no se consulta al proveedor.
export const peekTerrainElevation = (
  trailKey: string | number,
  route: readonly Coordinate[]
): Promise<TerrainElevationData | null> | null =>
  elevationCache.get(buildTerrainElevationCacheKey(trailKey, route)) ?? null;

export const getTerrainElevation = (
  trailKey: string | number,
  route: readonly Coordinate[],
  options: TerrainElevationOptions = {}
): Promise<TerrainElevationData | null> => {
  if (getUsableRoute(route).length < 2) return Promise.resolve(null);

  const cacheKey = buildTerrainElevationCacheKey(trailKey, route);
  if (options.forceRefresh) elevationCache.delete(cacheKey);

  const cached = elevationCache.get(cacheKey);
  if (cached) return cached;

  const request = loadTerrainElevation(route, options).then((result) => {
    if (!result) elevationCache.delete(cacheKey);
    return result;
  });
  elevationCache.set(cacheKey, request);
  return request;
};
