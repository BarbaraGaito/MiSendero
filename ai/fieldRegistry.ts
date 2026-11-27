import fatigue from "./models/field/fatigue.json";
import ams from "./models/field/ams.json";
import amsEvaluation from "../training/data/field-ai/v1/ams/evaluation/metrics.json";
import type { FieldModel, FieldTask } from "./fieldInference";

// Updated only by the reproducible evaluate stage, then checked by validate.
export const fieldModels: Record<FieldTask, FieldModel | null> = {
  fatigue: fatigue as unknown as FieldModel | null,
  ams: ams as unknown as FieldModel | null,
};

// Conservative delivery restriction after the held-out evaluation. This does
// not retune the frozen threshold or change the scientific eligibility result.
export const amsBinaryDecisionSupported = amsEvaluation.model.specificity > 0 && amsEvaluation.model.sensitivity > 0;
