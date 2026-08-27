import { db, initDB } from "../database/database";
import { RouteTrackingPoint } from "../types";

interface RouteTrackingPointRow {
  id: number;
  trail_id: number;
  started_at: number;
  latitude: number;
  longitude: number;
  accuracy_meters: number | null;
  speed_kmh: number | null;
  distance_delta_meters: number;
  recorded_at: number;
  simulated: number;
  created_at: number;
}

export interface RouteTrackingSummary {
  points: number;
  distanceMeters: number;
  startedAt: number;
  lastRecordedAt: number | null;
  lastPoint: RouteTrackingPoint | null;
}

const toRouteTrackingPoint = (row: RouteTrackingPointRow): RouteTrackingPoint => ({
  id: row.id,
  trailId: row.trail_id,
  startedAt: row.started_at,
  latitude: row.latitude,
  longitude: row.longitude,
  accuracyMeters: row.accuracy_meters,
  speedKmh: row.speed_kmh,
  distanceDeltaMeters: row.distance_delta_meters,
  recordedAt: row.recorded_at,
  simulated: row.simulated === 1,
});

export const saveRouteTrackingPoint = async (
  point: RouteTrackingPoint
): Promise<void> => {
  await initDB();

  await db.runAsync(
    `INSERT INTO route_tracking_points (
       trail_id,
       started_at,
       latitude,
       longitude,
       accuracy_meters,
       speed_kmh,
       distance_delta_meters,
       recorded_at,
       simulated,
       created_at
     )
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      point.trailId,
      point.startedAt,
      point.latitude,
      point.longitude,
      point.accuracyMeters,
      point.speedKmh,
      point.distanceDeltaMeters,
      point.recordedAt,
      point.simulated ? 1 : 0,
      Date.now(),
    ]
  );
};

export const getRouteTrackingSummary = async (
  trailId: number,
  startedAt: number
): Promise<RouteTrackingSummary> => {
  await initDB();

  const [summary, lastPointRow] = await Promise.all([
    db.getFirstAsync<{
      points: number;
      distance_meters: number | null;
      last_recorded_at: number | null;
    }>(
      `SELECT
         COUNT(*) AS points,
         COALESCE(SUM(distance_delta_meters), 0) AS distance_meters,
         MAX(recorded_at) AS last_recorded_at
       FROM route_tracking_points
       WHERE trail_id = ? AND started_at = ?`,
      [trailId, startedAt]
    ),
    db.getFirstAsync<RouteTrackingPointRow>(
      `SELECT *
       FROM route_tracking_points
       WHERE trail_id = ? AND started_at = ?
       ORDER BY recorded_at DESC
       LIMIT 1`,
      [trailId, startedAt]
    ),
  ]);

  return {
    points: summary?.points ?? 0,
    distanceMeters: summary?.distance_meters ?? 0,
    startedAt,
    lastRecordedAt: summary?.last_recorded_at ?? null,
    lastPoint: lastPointRow ? toRouteTrackingPoint(lastPointRow) : null,
  };
};

export const getLastRouteTrackingPoint = async (
  trailId: number,
  startedAt: number
) => {
  await initDB();

  const row = await db.getFirstAsync<RouteTrackingPointRow>(
    `SELECT *
     FROM route_tracking_points
     WHERE trail_id = ? AND started_at = ?
     ORDER BY recorded_at DESC
     LIMIT 1`,
    [trailId, startedAt]
  );

  return row ? toRouteTrackingPoint(row) : null;
};
