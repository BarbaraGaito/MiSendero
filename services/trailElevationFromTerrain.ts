import type { Coordinate } from "./geoUtils";
import type { TrailElevation } from "../types";
import {
  buildElevationProfile,
  buildTerrainElevationCacheKey,
  calculateElevationStatistics,
  sampleRouteByDistance,
  sampleTerrainGridElevation,
  type TerrainGridData,
} from "./terrainElevation";

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
  const profile = buildElevationProfile(samples, heights as number[]);
  const statistics = calculateElevationStatistics(profile);
  if (!statistics || statistics.totalDistanceMeters <= 0) return null;

  return {
    version: 1,
    geometry_hash: `client-grid:${buildTerrainElevationCacheKey(trailId, route)}`,
    source: data.source.dataset,
    source_url: data.source.endpoint,
    resolution_m: data.source.resolutionMeters,
    sample_spacing_m: Math.round(statistics.totalDistanceMeters / (profile.length - 1) * 10) / 10,
    noise_threshold_m: 0,
    fetched_at: data.source.fetchedAt,
    ascent_m: Math.round(statistics.elevationGainMeters),
    descent_m: Math.round(statistics.elevationLossMeters),
    min_m: Math.round(statistics.minElevationMeters),
    max_m: Math.round(statistics.maxElevationMeters),
    distance_m: Math.round(statistics.totalDistanceMeters),
    points: profile.map(point => ({
      latitude: point.coordinate[0],
      longitude: point.coordinate[1],
      distance_m: Math.round(point.distanceMeters * 10) / 10,
      elevation_m: Math.round(point.elevationMeters * 10) / 10,
    })),
  };
}
