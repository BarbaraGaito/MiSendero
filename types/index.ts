export type FatigueLevel = "bajo" | "medio" | "alto";
export type UserRole = "admin" | "user";

export interface WatchData {
  hr: number;
  timestamp: number;
}

export type WearableProvider =
  | "apple_healthkit"
  | "android_health_connect"
  | "wear_os_health_services"
  | "development_simulator";

export type WearableConnectionStatus =
  | "not_linked"
  | "linked"
  | "requires_consent"
  | "waiting_for_native_data"
  | "stale_data";

export type HealthPredictionLevel = "normal" | "caution" | "high";

export type WearableSimulationScenario =
  | "normal"
  | "esfuerzo_moderado"
  | "fatiga_alta"
  | "riesgo_fisiologico";

export interface WearableConnection {
  user_id?: number;
  provider: WearableProvider;
  linked: boolean;
  permissionsGranted: boolean;
  updatedAt: number | null;
  lastSyncAt: number | null;
}

export interface WearableMetricSample {
  id?: number;
  user_id?: number;
  provider: WearableProvider;
  heartRateBpm: number | null;
  steps: number | null;
  activeEnergyKcal: number | null;
  speedKmh: number | null;
  oxygenSaturation: number | null;
  recordedAt: number;
  createdAt?: number;
}

export interface WearableHealthPrediction {
  level: HealthPredictionLevel;
  title: string;
  message: string;
  fatigue: FatigueLevel | "sin_datos";
  fatigueConfidence: number;
  riskLabel: "bajo" | "medio" | "alto" | "sin_datos";
  riskConfidence: number;
  analysisSummary: string;
  factors: string[];
  recommendedAction: string;
}

export interface WearableRuntimeStatus {
  connection: WearableConnection;
  status: WearableConnectionStatus;
  latestSample: WearableMetricSample | null;
  prediction: WearableHealthPrediction | null;
  displayName: string;
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
  user_id: number | null;
  started_at: number;
  ended_at: number | null;
  duration: number;
  distance: number;
  avg_fatigue: FatigueLevel | null;
  trail_id: number | null;
  completion_status: "completed" | "ended_early" | "paused";
  route_progress_meters: number | null;
  route_total_meters: number | null;
  ended_latitude: number | null;
  ended_longitude: number | null;
  rating: number | null;
  review_text: string | null;
  reviewed_at: number | null;
}

export interface TrailElevation {
  version: number;
  geometry_hash: string;
  source: string;
  source_url: string;
  resolution_m: number;
  sample_spacing_m: number;
  noise_threshold_m: number;
  fetched_at: string;
  ascent_m: number;
  descent_m: number;
  min_m: number;
  max_m: number;
  distance_m: number;
  points: {
    latitude: number;
    longitude: number;
    distance_m: number;
    elevation_m: number;
  }[];
}

export interface TrailProvenance {
  checked_at: string;
  route_type: "out_and_back" | "point_to_point";
  access: string;
  precautions: string;
  duration_basis: string;
  official_distance_km: number | null;
  distance_basis: "mapped_geometry";
  sources: { title: string; url: string }[];
  mapping: { source: string; source_url: string; license: string; retrieved_at: string };
  photo: { author: string; page_url: string; license: string; license_url: string; context: string | null };
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
  elevation?: TrailElevation | null;
  provenance?: TrailProvenance | null;
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
  blocks_path: boolean;
  details: string | null;
  latitude: number | null;
  longitude: number | null;
  accuracy_meters: number | null;
  route_progress_meters: number | null;
  reporter_name: string;
  created_at: string;
}

export interface RouteTrackingPoint {
  id?: number;
  trailId: number;
  startedAt: number;
  latitude: number;
  longitude: number;
  accuracyMeters: number | null;
  speedKmh: number | null;
  distanceDeltaMeters: number;
  recordedAt: number;
  simulated: boolean;
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
