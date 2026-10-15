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
  reason?: string;
  label: string;
  confidence: number;
  distances: Record<string, number>;
}

export interface RandomForestTree {
  feature: number[];
  threshold: number[];
  left: number[];
  right: number[];
  value: number[][];
}

export interface RandomForestModel {
  evaluation_validity?: {
    real_public_ground_truth: boolean;
    deployment_approved: boolean;
    reason: string;
  };
  type: "random_forest_json";
  version: number;
  trained_at?: string;
  feature_order: string[];
  classes: string[];
  trees: RandomForestTree[];
  training_summary?: {
    dataset_rows: number;
    synthetic_rows?: number;
    test_accuracy: number;
    test_f1_macro: number;
    guardrail_status: string;
  };
}
