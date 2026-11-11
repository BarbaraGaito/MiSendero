import type { Coordinate } from "./geoUtils";
import type { TrailElevation } from "../types";
import {
  buildTerrainElevationCacheKey,
  sampleRouteByDistance,
  sampleTerrainGridElevation,
  type TerrainGridData,
} from "./terrainElevation";

const NOISE_THRESHOLD_METERS = 5;

// The route profile can use the same measured DEM grid as the 3D map when
// the server did not include its Open-Meteo profile.
export function trailElevationFromTerrain(
  trailId: number,
  route: readonly Coordinate[],
  data: TerrainGridData
): TrailElevation | null {
  const samples = sampleRouteByDistance(route);
  if (samples.length < 2) return null;
  const heights = samples.map(sample => sampleTerrainGridElevation(data.grid, sample.coordinate));
  if (heights.some(height => height === null)) return null;
  const elevations = heights as number[];
  const distanceMeters = samples.at(-1)!.distanceMeters - samples[0].distanceMeters;
  if (distanceMeters <= 0) return null;
  let anchor = elevations[0];
  let ascent = 0;
  let descent = 0;
  elevations.slice(1).forEach((height, index) => {
    const change = height - anchor;
    if (Math.abs(change) >= NOISE_THRESHOLD_METERS || index === elevations.length - 2) {
      ascent += Math.max(0, change);
      descent += Math.max(0, -change);
      anchor = height;
    }
  });

  return {
    version: 1,
    geometry_hash: `client-grid:${buildTerrainElevationCacheKey(trailId, route)}`,
    source: data.source.dataset,
    source_url: data.source.dataset === "Mapzen Terrain Tiles"
      ? "https://registry.opendata.aws/terrain-tiles/"
      : data.source.endpoint,
    resolution_m: data.source.resolutionMeters,
    sample_spacing_m: Math.round(distanceMeters / (samples.length - 1) * 10) / 10,
    noise_threshold_m: NOISE_THRESHOLD_METERS,
    fetched_at: data.source.fetchedAt,
    ascent_m: Math.round(ascent),
    descent_m: Math.round(descent),
    min_m: Math.min(...elevations),
    max_m: Math.max(...elevations),
    distance_m: Math.round(distanceMeters),
    points: samples.map((point, index) => ({
      latitude: point.coordinate[0],
      longitude: point.coordinate[1],
      distance_m: Math.round(point.distanceMeters * 10) / 10,
      elevation_m: Math.round(elevations[index] * 10) / 10,
    })),
  };
}
