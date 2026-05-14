import * as SQLite from 'expo-sqlite';

import { FatigueLevel, SampleRecord, SessionHistoryItem } from '../types';

interface SessionRow {
  averageFatigue: FatigueLevel;
  distanceMeters: number;
  durationSec: number;
  endedAt: number | null;
  id: number;
  sampleCount: number;
  startedAt: number;
  syncStatus: string;
}

interface FinishSessionParams {
  averageFatigue: FatigueLevel;
  distanceMeters: number;
  durationSec: number;
  endedAt: number;
  sampleCount: number;
  sessionId: number;
  syncStatus: string;
}

let databasePromise: Promise<SQLite.SQLiteDatabase> | null = null;

async function getDatabase() {
  if (!databasePromise) {
    databasePromise = SQLite.openDatabaseAsync('misendero.db');
  }

  return databasePromise;
}

export async function initDatabase() {
  const db = await getDatabase();

  await db.execAsync(`
    PRAGMA journal_mode = WAL;

    CREATE TABLE IF NOT EXISTS sessions (
      id INTEGER PRIMARY KEY NOT NULL,
      startedAt INTEGER NOT NULL,
      endedAt INTEGER,
      durationSec REAL DEFAULT 0,
      distanceMeters REAL DEFAULT 0,
      averageFatigue TEXT DEFAULT 'bajo',
      sampleCount INTEGER DEFAULT 0,
      syncStatus TEXT DEFAULT 'offline-only'
    );

    CREATE TABLE IF NOT EXISTS samples (
      id INTEGER PRIMARY KEY NOT NULL,
      sessionId INTEGER NOT NULL,
      timestamp INTEGER NOT NULL,
      heartRate INTEGER NOT NULL,
      speedMps REAL NOT NULL,
      durationSec REAL NOT NULL,
      fatigue TEXT NOT NULL,
      latitude REAL,
      longitude REAL,
      alertLabel TEXT,
      FOREIGN KEY (sessionId) REFERENCES sessions (id) ON DELETE CASCADE
    );
  `);
}

export async function createSession(startedAt: number) {
  const db = await getDatabase();
  const result = await db.runAsync(
    'INSERT INTO sessions (startedAt, syncStatus) VALUES (?, ?)',
    startedAt,
    'offline-only'
  );

  return Number(result.lastInsertRowId);
}

export async function saveSample(sample: SampleRecord) {
  const db = await getDatabase();

  await db.runAsync(
    `INSERT INTO samples (
      sessionId,
      timestamp,
      heartRate,
      speedMps,
      durationSec,
      fatigue,
      latitude,
      longitude,
      alertLabel
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    sample.sessionId,
    sample.timestamp,
    sample.heartRate,
    sample.speedMps,
    sample.durationSec,
    sample.fatigue,
    sample.latitude,
    sample.longitude,
    sample.alertLabel
  );
}

export async function finishSession({
  averageFatigue,
  distanceMeters,
  durationSec,
  endedAt,
  sampleCount,
  sessionId,
  syncStatus,
}: FinishSessionParams) {
  const db = await getDatabase();

  await db.runAsync(
    `UPDATE sessions
     SET endedAt = ?, durationSec = ?, distanceMeters = ?, averageFatigue = ?, sampleCount = ?, syncStatus = ?
     WHERE id = ?`,
    endedAt,
    durationSec,
    distanceMeters,
    averageFatigue,
    sampleCount,
    syncStatus,
    sessionId
  );
}

export async function getSessionHistory(): Promise<SessionHistoryItem[]> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<SessionRow>(
    `SELECT
      id,
      startedAt,
      endedAt,
      durationSec,
      distanceMeters,
      averageFatigue,
      sampleCount,
      syncStatus
    FROM sessions
    ORDER BY startedAt DESC`
  );

  return rows.map((row) => ({
    averageFatigue: row.averageFatigue,
    distanceMeters: row.distanceMeters,
    durationSec: row.durationSec,
    endedAt: row.endedAt,
    id: row.id,
    sampleCount: row.sampleCount,
    startedAt: row.startedAt,
    syncStatus: row.syncStatus,
  }));
}

