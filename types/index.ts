export type FatigueLevel = "bajo" | "medio" | "alto";
export type UserRole = "admin" | "user";

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
  trail_id: number | null;
  rating: number | null;
  review_text: string | null;
  reviewed_at: number | null;
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
  center_lat: number | null;
  center_lng: number | null;
  map_zoom: number | null;
  route_coordinates: string | null;
  created_at: string;
}

export interface TrailWeather {
  trail_id: number;
  date: string;
  temperature_c: number;
  min_temperature_c: number;
  max_temperature_c: number;
  condition: string;
  wind_kmh: number;
  rain_probability: number;
  risk_level: "bajo" | "medio" | "alto";
  recommendation: string;
  source: string;
}

export interface TrailReport {
  id: number;
  trail_id: number;
  issue_summary: string;
  severity: string;
  trail_state: string;
  cause: string | null;
  blocks_path: number;
  details: string | null;
  reporter_name: string;
  created_at: string;
}

export interface EmergencyContact {
  id?: number;
  name: string;
  phone: string;
  relationship: string;
  updated_at: number;
}

export interface Profile {
  user: {
    id: number;
    name: string;
    email: string;
    role?: UserRole;
    terms_version?: string | null;
    terms_accepted_at?: string | null;
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
  role?: UserRole;
  terms_version?: string | null;
  terms_accepted_at?: string | null;
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
