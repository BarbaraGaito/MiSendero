import fatigueMetricsJson from "./models/fatigueMetrics.json";
import riskMetricsJson from "./models/riskMetrics.json";
import routeDifficultyMetricsJson from "./models/routeDifficultyMetrics.json";
import apnRouteDifficultyMetricsJson from "./models/apnRouteDifficultyMetrics.json";

export type AiModelGuardrailStatus =
  | "ok"
  | "review_recommended"
  | "requires_more_real_data";

export interface AiMetricSummary {
  accuracy: number;
  precision_macro: number;
  recall_macro: number;
  f1_macro: number;
  support: number;
}

export interface AiCrossValidationSummary {
  folds: number;
  accuracy_mean?: number;
  accuracy_std?: number;
  precision_macro_mean?: number;
  precision_macro_std?: number;
  recall_macro_mean?: number;
  recall_macro_std?: number;
  f1_macro_mean: number;
  f1_macro_std: number;
}

export interface AiTrainingMetrics {
  evaluation_details?: {
    version: number;
    model: AiMetricSummary & { balanced_accuracy: number };
    baseline: AiMetricSummary & { label: string; balanced_accuracy: number };
    difference_from_baseline: { accuracy: number; f1_macro: number; balanced_accuracy: number };
    class_coverage: {
      training_counts: Record<string, number>;
      test_counts: Record<string, number>;
      missing_in_training: string[];
      missing_in_test: string[];
      labels_total: number;
      labels_in_training: number;
      labels_in_test: number;
    };
    group_support: { training: number; test: number };
    interpretation: string;
  };
  baseline?: {
    test_accuracy: number;
    label: string;
    strategy: string;
    tied_labels_test_accuracy?: Record<string, number>;
  };
  evaluation_protocol?: {
    independent_group_count: number;
    test_groups: string[];
  };
  evaluation_validity: {
    real_public_ground_truth: boolean;
    status: string;
    reason: string;
    deployment_approved: boolean;
    synthetic_rows: number;
  };
  schema_version: number;
  trained_at: string;
  dataset: {
    name: string;
    declared_source: string;
    source_note: string;
    rows_total: number;
    rows_train: number;
    rows_test: number;
    rows_by_label: Record<string, number>;
    features: string[];
  };
  metrics: {
    train: AiMetricSummary;
    test: AiMetricSummary;
    cross_validation: AiCrossValidationSummary | null;
  };
  guardrails: {
    status: AiModelGuardrailStatus;
    overfitting_risk: boolean;
    underfitting_risk: boolean;
    high_variance_risk: boolean;
    insufficient_real_data: boolean;
    train_test_f1_gap: number;
    warnings: string[];
  };
  hyperparameters: {
    n_estimators: number;
    max_depth: number;
    min_samples_leaf: number;
    selection_method: "cross_validated" | "fallback_too_few_rows";
    cv_folds: number | null;
    cv_f1_macro_mean: number | null;
  };
}

export const adminAiModelMetrics: AiTrainingMetrics[] = [
  fatigueMetricsJson,
  riskMetricsJson,
  routeDifficultyMetricsJson,
  apnRouteDifficultyMetricsJson,
] as AiTrainingMetrics[];
