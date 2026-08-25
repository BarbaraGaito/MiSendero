import { db } from "./database";
import { FatigueLevel, SessionRow } from "../types";

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

export const createSession = async (startedAt: number, trailId?: number | null) => {
  const result = await db.runAsync(
    `INSERT INTO sessions (started_at, duration, distance, avg_fatigue, trail_id)
     VALUES (?, 0, 0, ?, ?)`,
    [startedAt, "bajo", trailId ?? null]
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
  await db.runAsync(
    `UPDATE sessions
     SET ended_at = ?,
         duration = ?,
         distance = ?,
         avg_fatigue = ?,
         trail_id = COALESCE(?, trail_id)
     WHERE id = ?`,
    [endedAt, duration, distance, avgFatigue, trailId ?? null, sessionId]
  );
};

export const getOrCreateCompletedSession = async ({
  trailId,
  startedAt,
  endedAt,
  duration,
  distance,
}: {
  trailId: number;
  startedAt: number;
  endedAt: number;
  duration: number;
  distance: number;
}): Promise<SessionRow> => {
  const existing = await db.getFirstAsync<SessionRow>(
    `SELECT * FROM sessions
     WHERE trail_id = ? AND started_at = ?
     LIMIT 1`,
    [trailId, startedAt]
  );

  if (existing) return existing;

  const result = await db.runAsync(
    `INSERT INTO sessions (
       started_at,
       ended_at,
       duration,
       distance,
       avg_fatigue,
       trail_id
     )
     VALUES (?, ?, ?, ?, ?, ?)`,
    [startedAt, endedAt, duration, distance, "bajo", trailId]
  );

  const row = await db.getFirstAsync<SessionRow>(
    `SELECT * FROM sessions WHERE id = ?`,
    [result.lastInsertRowId]
  );

  if (!row) {
    throw new Error("completed-session-not-found");
  }

  return row;
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
  const existing = await db.getFirstAsync<SessionRow>(
    `SELECT * FROM sessions
     WHERE trail_id = ? AND started_at = ?
     LIMIT 1`,
    [trailId, startedAt]
  );

  if (existing) {
    await db.runAsync(
      `UPDATE sessions
       SET ended_at = NULL,
           duration = ?,
           distance = ?,
           trail_id = ?
       WHERE id = ?`,
      [duration, distance, trailId, existing.id]
    );

    return {
      ...existing,
      ended_at: null,
      duration,
      distance,
      trail_id: trailId,
    };
  }

  const result = await db.runAsync(
    `INSERT INTO sessions (
       started_at,
       ended_at,
       duration,
       distance,
       avg_fatigue,
       trail_id
     )
     VALUES (?, NULL, ?, ?, ?, ?)`,
    [startedAt, duration, distance, "bajo", trailId]
  );

  const row = await db.getFirstAsync<SessionRow>(
    `SELECT * FROM sessions WHERE id = ?`,
    [result.lastInsertRowId]
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
  await db.runAsync(
    `UPDATE sessions
     SET trail_id = COALESCE(trail_id, ?)
     WHERE id = ?`,
    [trailId, sessionId]
  );
};

export const saveSessionReview = async (
  sessionId: number,
  trailId: number,
  rating: number,
  reviewText: string
) => {
  await db.runAsync(
    `UPDATE sessions
     SET trail_id = ?,
         rating = ?,
         review_text = ?,
         reviewed_at = ?
     WHERE id = ?`,
    [trailId, rating, reviewText.trim() || null, Date.now(), sessionId]
  );
};

export const getTrailRatingSummary = async (
  trailId: number
): Promise<TrailRatingSummary | null> => {
  const row = await db.getFirstAsync<{
    average_rating: number | null;
    review_count: number;
  }>(
    `SELECT AVG(rating) AS average_rating,
            COUNT(rating) AS review_count
     FROM sessions
     WHERE trail_id = ? AND rating IS NOT NULL`,
    [trailId]
  );

  if (!row || row.review_count === 0 || row.average_rating === null) return null;

  return {
    averageRating: row.average_rating,
    reviewCount: row.review_count,
  };
};

export const getTrailReviews = async (trailId: number): Promise<TrailReview[]> => {
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
     WHERE trail_id = ? AND rating IS NOT NULL
     ORDER BY reviewed_at DESC, ended_at DESC`,
    [trailId]
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
  return await db.getAllAsync<SessionRow>(
    `SELECT * FROM sessions
     WHERE ended_at IS NOT NULL
     ORDER BY started_at DESC`
  );
};

export const getLatestCompletedSession = async (): Promise<SessionRow | null> => {
  const row = await db.getFirstAsync<SessionRow>(
    `SELECT * FROM sessions
     WHERE ended_at IS NOT NULL
     ORDER BY ended_at DESC
     LIMIT 1`
  );

  return row ?? null;
};

export const getRecentSessions = async (
  limit = 10
): Promise<SessionRow[]> => {
  return await db.getAllAsync<SessionRow>(
    `SELECT * FROM sessions
     ORDER BY started_at DESC
     LIMIT ?`,
    [limit]
  );
};

export const getSessionsSummary = async (): Promise<SessionsSummary> => {
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
       SUM(CASE WHEN ended_at IS NOT NULL THEN 1 ELSE 0 END) AS completed_count,
       SUM(CASE WHEN ended_at IS NOT NULL AND started_at >= ? THEN 1 ELSE 0 END) AS current_month_count
     FROM sessions`,
    [monthStart.getTime()]
  );

  return {
    totalDistance: row?.total_distance ?? 0,
    completedCount: row?.completed_count ?? 0,
    currentMonthCount: row?.current_month_count ?? 0,
  };
};
