export type FatigueLevel = 'bajo' | 'medio' | 'alto';

export type WatchAlert = 'Fatiga alta' | 'Detenido mucho tiempo';

export type WatchCommand = 'start' | 'stop' | 'sos';

export type SessionPhase = 'idle' | 'starting' | 'active' | 'stopping';

export type StatusTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

export type GpsMode = 'checking' | 'real' | 'simulated';

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
  errorMessage: string | null;
  fatigue: FatigueLevel;
  gpsMode: GpsMode;
  heartRate: number;
  lastSyncMessage: string;
  lastUpdatedAt: number | null;
  pendingCommand: WatchCommand | null;
  phase: SessionPhase;
  speedMps: number;
  startedAt: number | null;
  statusMessage: string;
  statusTone: StatusTone;
  storageLabel: string;
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
  errorMessage: string | null;
  fatigue: FatigueLevel;
  gpsMode: GpsMode;
  heartRate: number;
  lastSyncMessage: string;
  lastUpdatedAt: number | null;
  pendingCommand: WatchCommand | null;
  phase: SessionPhase;
  samplesStored: number;
  sessionId: number | null;
  sosRaised: boolean;
  speedMps: number;
  startedAt: number | null;
  statusMessage: string;
  statusTone: StatusTone;
  storageLabel: string;
}

export interface SyncLogEntry {
  id: number;
  message: string;
  timestamp: number;
}
