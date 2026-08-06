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

export interface Trail {
  id: number;
  name: string;
  location: string;
  difficulty: string;
  duration: string | null;
  distance_km: number | null;
  description: string | null;
  image_url: string | null;
  created_at: string;
}

export interface Profile {
  user: {
    id: number;
    name: string;
    email: string;
    created_at?: string;
  } | null;
  stats: {
    completed_routes: number;
    total_distance_km: number;
  };
}

export interface AuthUser {
  id: number;
  name: string;
  email: string;
  created_at?: string;
}

export interface AuthResponse {
  token: string;
  user: AuthUser;
}

export interface AuthSession {
  token: string;
  user: AuthUser;
}
