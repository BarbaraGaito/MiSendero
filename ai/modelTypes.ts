export type OfflineAiLabel = string;

export interface OfflineAiModel {
  id: string;
  version: number;
  trained_at: string;
  algorithm: "nearest_centroid_standardized";
  source: string;
  features: string[];
  labels: OfflineAiLabel[];
  statistics: Record<string, { mean: number; std: number }>;
  centroids: Record<string, Record<string, number>>;
}

export interface OfflinePrediction {
  label: string;
  confidence: number;
  distances: Record<string, number>;
}
