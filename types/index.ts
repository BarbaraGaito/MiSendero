export type FatigueLevel = 'bajo' | 'medio' | 'alto';

export type WatchAlert = 'Fatiga alta' | 'Detenido mucho tiempo';

export type WatchCommand = 'start' | 'stop' | 'sos';

export interface FatigueInput {
  durationSec: number;
  heartRate: number;
  speedMps: number;
}

export interface FatigueAssessment {
  level: FatigueLevel;
  reason: string;
  score: number;
}

export interface SensorSample {
  heartRate: number;
  timestamp: number;
}

export interface PhoneToWatchPayload {
  active: boolean;
  alerts: WatchAlert[];
  distanceMeters: number;
  durationSec: number;
  fatigue: FatigueLevel;
  heartRate: number;
  lastSyncMessage: string;
  speedMps: number;
  startedAt: number | null;
}

export interface LocationSnapshot {
  distanceMeters: number;
  durationSec: number;
  latitude: number | null;
  longitude: number | null;
  source: 'real' | 'simulated';
  speedMps: number;
  stoppedSeconds: number;
}

export interface SampleRecord {
  alertLabel: string | null;
  durationSec: number;
  fatigue: FatigueLevel;
  heartRate: number;
  latitude: number | null;
  longitude: number | null;
  sessionId: number;
  speedMps: number;
  timestamp: number;
}

export interface SessionHistoryItem {
  averageFatigue: FatigueLevel;
  distanceMeters: number;
  durationSec: number;
  endedAt: number | null;
  id: number;
  sampleCount: number;
  startedAt: number;
  syncStatus: string;
}

export interface LiveSessionMetrics {
  active: boolean;
  alerts: WatchAlert[];
  distanceMeters: number;
  durationSec: number;
  fatigue: FatigueLevel;
  gpsMode: 'real' | 'simulated';
  heartRate: number;
  lastSyncMessage: string;
  samplesStored: number;
  sessionId: number | null;
  sosRaised: boolean;
  speedMps: number;
  startedAt: number | null;
}

export interface SyncLogEntry {
  id: number;
  message: string;
  timestamp: number;
}

