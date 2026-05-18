import { db } from "./database";
import { FatigueLevel, SessionRow } from "../types";

export const createSession = async (startedAt: number) => {
  const result = await db.runAsync(
    `INSERT INTO sessions (started_at, duration, distance, avg_fatigue)
     VALUES (?, 0, 0, ?)`,
    [startedAt, "bajo"]
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
  avgFatigue: FatigueLevel
) => {
  await db.runAsync(
    `UPDATE sessions
     SET ended_at = ?, duration = ?, distance = ?, avg_fatigue = ?
     WHERE id = ?`,
    [endedAt, duration, distance, avgFatigue, sessionId]
  );
};

export const getSessions = async (): Promise<SessionRow[]> => {
  return await db.getAllAsync<SessionRow>(
    `SELECT * FROM sessions
     WHERE ended_at IS NOT NULL
     ORDER BY started_at DESC`
  );
};
