/** Shared with the mobile client, like the existing AI contracts. */
export type EnvironmentalModelType = "snow" | "river_level" | "fire_detection";
export type EnvironmentalStatus = "available" | "experimental" | "no_data" | "not_approved" | "expired" | "error";
export type EnvironmentalValue = { probability: number; horizon_hours: 24 } | {
  level_m: number; latest_level_m: number; historical_mae_m: number;
  station_id: number; station_name: string; river_name: string; horizon_hours: 3 | 6;
};
export interface EnvironmentalSnapshot {
  schema_version: 1; trail_id: number; geometry_hash: string;
  model_type: EnvironmentalModelType; model_id: string | null; model_version: string | null;
  status: EnvironmentalStatus; prediction: EnvironmentalValue | null;
  source: { name: string; url: string; license: string | null };
  observed_at: string | null; inputs_available_at: string | null; issued_at: string | null;
  target_at: string | null; valid_until: string | null; evidence_sha256: string | null;
  geographic_scope: { description: string; station_id?: number; kind?: string; pixel_id?: string; latitude?: number; longitude?: number };
  limitations: string[];
}
export interface EnvironmentalBatch {
  schema_version: 1; trail_id: number; geometry_hash: string; generated_at: string;
  snapshots: EnvironmentalSnapshot[]; payload_sha256: string;
}
export const MODEL_TYPES: EnvironmentalModelType[];
export const STATUSES: EnvironmentalStatus[];
export function canonicalJSON(value: unknown): string;
export function geometryCanonical(trail: { route_coordinates: unknown; center_lat: unknown; center_lng: unknown }): string;
export function validateSnapshot(value: unknown, trailId: number, hash: string): EnvironmentalSnapshot;
export function validateBatch(value: unknown, trailId: number, hash: string): EnvironmentalBatch;
export function batchBody(batch: EnvironmentalBatch): Omit<EnvironmentalBatch, "payload_sha256">;
export function visibleSnapshots(batch: EnvironmentalBatch, now?: number): EnvironmentalSnapshot[];
