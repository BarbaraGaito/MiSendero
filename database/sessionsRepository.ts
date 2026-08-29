import { db } from "./database";
import { FatigueLevel, SessionRow } from "../types";
import { getAuthSession } from "../services/authSession";

type SessionCompletionStatus = SessionRow["completion_status"];
type EndedSessionCompletionStatus = Exclude<SessionCompletionStatus, "paused">;

export interface SessionsSummary {
  totalDistance: number;
  completedCount: number;
  currentMonthCount: number;
}

export interface TrailRatingSummary {
  averageRating: number;
  reviewCount: number;
}

export interface TrailReview {
  id: number;
  rating: number;
  reviewText: string | null;
  reviewedAt: number;
  startedAt: number;
}

export interface CompletedSessionResult {
  session: SessionRow;
  didFinalizeNow: boolean;
}

const getCurrentUserId = async () => {
  const session = await getAuthSession().catch(() => null);
  return session?.user.id ?? null;
};

export const createSession = async (startedAt: number, trailId?: number | null) => {
  const userId = await getCurrentUserId();
  const result = await db.runAsync(
    `INSERT INTO sessions (user_id, started_at, duration, distance, avg_fatigue, trail_id, completion_status)
     VALUES (?, ?, 0, 0, ?, ?, ?)`,
    [userId, startedAt, "bajo", trailId ?? null, "paused"]
  );

  return result.lastInsertRowId;
};

export const saveHeartRateLog = async (
  hr: number,
  timestamp: number,
  sessionId: number
) => {
  await db.runAsync(
    `INSERT INTO heart_rate_logs (hr, timestamp, session_id)
     VALUES (?, ?, ?)`,
    [hr, timestamp, sessionId]
  );
};

export const finishSession = async (
  sessionId: number,
  endedAt: number,
  duration: number,
  distance: number,
  avgFatigue: FatigueLevel,
  trailId?: number | null
) => {
  const userId = await getCurrentUserId();
  await db.runAsync(
    `UPDATE sessions
     SET ended_at = ?,
         duration = ?,
         distance = ?,
         avg_fatigue = ?,
         completion_status = ?,
         trail_id = COALESCE(?, trail_id)
     WHERE id = ? AND user_id IS ?`,
    [endedAt, duration, distance, avgFatigue, "completed", trailId ?? null, sessionId, userId]
  );
};

export const getOrCreateCompletedSession = async ({
  trailId,
  startedAt,
  endedAt,
  duration,
  distance,
  completionStatus = "completed",
  routeProgressMeters = null,
  routeTotalMeters = null,
  endedLatitude = null,
  endedLongitude = null,
}: {
  trailId: number;
  startedAt: number;
  endedAt: number;
  duration: number;
  distance: number;
  completionStatus?: EndedSessionCompletionStatus;
  routeProgressMeters?: number | null;
  routeTotalMeters?: number | null;
  endedLatitude?: number | null;
  endedLongitude?: number | null;
}): Promise<CompletedSessionResult> => {
  const userId = await getCurrentUserId();
  const existing = await db.getFirstAsync<SessionRow>(
    `SELECT * FROM sessions
     WHERE user_id IS ? AND trail_id = ? AND started_at = ?
     LIMIT 1`,
    [userId, trailId, startedAt]
  );

  if (existing) {
    const alreadyFinalized =
      existing.ended_at !== null && existing.completion_status !== "paused";

    if (alreadyFinalized) {
      return { session: existing, didFinalizeNow: false };
    }

    await db.runAsync(
      `UPDATE sessions
       SET ended_at = ?,
           duration = ?,
           distance = ?,
           avg_fatigue = COALESCE(avg_fatigue, ?),
           trail_id = ?,
           completion_status = ?,
           route_progress_meters = ?,
           route_total_meters = ?,
           ended_latitude = ?,
           ended_longitude = ?
       WHERE id = ? AND user_id IS ?`,
      [
        endedAt,
        duration,
        distance,
        "bajo",
        trailId,
        completionStatus,
        routeProgressMeters,
        routeTotalMeters,
        endedLatitude,
        endedLongitude,
        existing.id,
        userId,
      ]
    );

    const updated = await db.getFirstAsync<SessionRow>(
      `SELECT * FROM sessions WHERE id = ? AND user_id IS ?`,
      [existing.id, userId]
    );

    if (!updated) {
      throw new Error("completed-session-not-found");
    }

    return { session: updated, didFinalizeNow: true };
  }

  const result = await db.runAsync(
    `INSERT INTO sessions (
       user_id,
       started_at,
       ended_at,
       duration,
       distance,
       avg_fatigue,
       trail_id,
       completion_status,
       route_progress_meters,
       route_total_meters,
       ended_latitude,
       ended_longitude
     )
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      userId,
      startedAt,
      endedAt,
      duration,
      distance,
      "bajo",
      trailId,
      completionStatus,
      routeProgressMeters,
      routeTotalMeters,
      endedLatitude,
      endedLongitude,
    ]
  );

  const row = await db.getFirstAsync<SessionRow>(
    `SELECT * FROM sessions WHERE id = ? AND user_id IS ?`,
    [result.lastInsertRowId, userId]
  );

  if (!row) {
    throw new Error("completed-session-not-found");
  }

  return { session: row, didFinalizeNow: true };
};

export const getOrCreatePausedSession = async ({
  trailId,
  startedAt,
  duration,
  distance,
}: {
  trailId: number;
  startedAt: number;
  duration: number;
  distance: number;
}): Promise<SessionRow> => {
  const userId = await getCurrentUserId();
  const existing = await db.getFirstAsync<SessionRow>(
    `SELECT * FROM sessions
     WHERE user_id IS ? AND trail_id = ? AND started_at = ?
     LIMIT 1`,
    [userId, trailId, startedAt]
  );

  if (existing) {
    await db.runAsync(
      `UPDATE sessions
       SET ended_at = NULL,
           duration = ?,
           distance = ?,
           completion_status = ?,
           trail_id = ?
       WHERE id = ? AND user_id IS ?`,
      [duration, distance, "paused", trailId, existing.id, userId]
    );

    return {
      ...existing,
      ended_at: null,
      duration,
      distance,
      completion_status: "paused",
      trail_id: trailId,
    };
  }

  const result = await db.runAsync(
    `INSERT INTO sessions (
       user_id,
       started_at,
       ended_at,
       duration,
       distance,
       avg_fatigue,
       trail_id,
       completion_status
     )
     VALUES (?, ?, NULL, ?, ?, ?, ?, ?)`,
    [userId, startedAt, duration, distance, "bajo", trailId, "paused"]
  );

  const row = await db.getFirstAsync<SessionRow>(
    `SELECT * FROM sessions WHERE id = ? AND user_id IS ?`,
    [result.lastInsertRowId, userId]
  );

  if (!row) {
    throw new Error("paused-session-not-found");
  }

  return row;
};

export const attachTrailToSession = async (
  sessionId: number,
  trailId: number
) => {
  const userId = await getCurrentUserId();
  await db.runAsync(
    `UPDATE sessions
     SET trail_id = COALESCE(trail_id, ?)
     WHERE id = ? AND user_id IS ?`,
    [trailId, sessionId, userId]
  );
};

export const saveSessionReview = async (
  sessionId: number,
  trailId: number,
  rating: number,
  reviewText: string
) => {
  const userId = await getCurrentUserId();
  await db.runAsync(
    `UPDATE sessions
     SET trail_id = ?,
         rating = ?,
         review_text = ?,
         reviewed_at = ?
     WHERE id = ? AND user_id IS ?`,
    [trailId, rating, reviewText.trim() || null, Date.now(), sessionId, userId]
  );
};

export const getTrailRatingSummary = async (
  trailId: number
): Promise<TrailRatingSummary | null> => {
  const userId = await getCurrentUserId();
  const row = await db.getFirstAsync<{
    average_rating: number | null;
    review_count: number;
  }>(
    `SELECT AVG(rating) AS average_rating,
            COUNT(rating) AS review_count
     FROM sessions
     WHERE user_id IS ? AND trail_id = ? AND rating IS NOT NULL`,
    [userId, trailId]
  );

  if (!row || row.review_count === 0 || row.average_rating === null) return null;

  return {
    averageRating: row.average_rating,
    reviewCount: row.review_count,
  };
};

export const getTrailReviews = async (trailId: number): Promise<TrailReview[]> => {
  const userId = await getCurrentUserId();
  const rows = await db.getAllAsync<{
    id: number;
    rating: number;
    review_text: string | null;
    reviewed_at: number | null;
    started_at: number;
  }>(
    `SELECT id,
            rating,
            review_text,
            reviewed_at,
            started_at
     FROM sessions
     WHERE user_id IS ? AND trail_id = ? AND rating IS NOT NULL
     ORDER BY reviewed_at DESC, ended_at DESC`,
    [userId, trailId]
  );

  return rows.map((row) => ({
    id: row.id,
    rating: row.rating,
    reviewText: row.review_text,
    reviewedAt: row.reviewed_at ?? row.started_at,
    startedAt: row.started_at,
  }));
};

export const getSessions = async (): Promise<SessionRow[]> => {
  const userId = await getCurrentUserId();
  return await db.getAllAsync<SessionRow>(
    `SELECT * FROM sessions
     WHERE user_id IS ? AND ended_at IS NOT NULL
     ORDER BY started_at DESC`,
    [userId]
  );
};

export const getLatestCompletedSession = async (): Promise<SessionRow | null> => {
  const userId = await getCurrentUserId();
  const row = await db.getFirstAsync<SessionRow>(
    `SELECT * FROM sessions
     WHERE user_id IS ? AND ended_at IS NOT NULL
     ORDER BY ended_at DESC
     LIMIT 1`,
    [userId]
  );

  return row ?? null;
};

export const getRecentSessions = async (
  limit = 10
): Promise<SessionRow[]> => {
  const userId = await getCurrentUserId();
  return await db.getAllAsync<SessionRow>(
    `SELECT * FROM sessions
     WHERE user_id IS ?
     ORDER BY started_at DESC
     LIMIT ?`,
    [userId, limit]
  );
};

export const getSessionsSummary = async (): Promise<SessionsSummary> => {
  const userId = await getCurrentUserId();
  const monthStart = new Date();
  monthStart.setDate(1);
  monthStart.setHours(0, 0, 0, 0);

  const row = await db.getFirstAsync<{
    total_distance: number | null;
    completed_count: number;
    current_month_count: number;
  }>(
    `SELECT
       COALESCE(SUM(CASE WHEN ended_at IS NOT NULL THEN distance ELSE 0 END), 0) AS total_distance,
       SUM(CASE WHEN ended_at IS NOT NULL AND completion_status = 'completed' THEN 1 ELSE 0 END) AS completed_count,
       SUM(CASE WHEN ended_at IS NOT NULL AND started_at >= ? THEN 1 ELSE 0 END) AS current_month_count
     FROM sessions
     WHERE user_id IS ?`,
    [monthStart.getTime(), userId]
  );

  return {
    totalDistance: row?.total_distance ?? 0,
    completedCount: row?.completed_count ?? 0,
    currentMonthCount: row?.current_month_count ?? 0,
  };
};
