export type FatigueLevel = "bajo" | "medio" | "alto";

export interface WatchData {
  hr: number;
  timestamp: number;
}

export interface Session {
  id?: number;
  startedAt: number;
  endedAt?: number | null;
  duration: number;
  distance: number;
  avgFatigue: FatigueLevel;
}

export interface SessionRow {
  id: number;
  started_at: number;
  ended_at: number | null;
  duration: number;
  distance: number;
  avg_fatigue: FatigueLevel;
}
