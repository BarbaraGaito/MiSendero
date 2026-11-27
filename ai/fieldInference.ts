/** Portable inference and explicit eligibility for the informational prototype. */
export type FieldTask = "fatigue" | "ams";
export type FieldStatus = "available" | "missing_inputs" | "not_eligible" | "outside_scope" | "invalid_model";
export type FieldFeatures = Record<string, number | null | undefined>;
export interface PortableClassifier {
  type: "random_forest_json" | "scaled_classifier_json";
  feature_order: string[];
  classes: string[];
  trees?: Array<{ feature: number[]; threshold: number[]; left: number[]; right: number[]; value: number[][] }>;
  scaler?: { mean: number[]; scale: number[] };
  linear?: { coef: number[][]; intercept: number[]; multiclass: "ovr" | "multinomial" };
  network?: { coefs: number[][][]; intercepts: number[][]; activation: string; out_activation: string };
}
export interface FieldModel {
  schema_version: number;
  id: string;
  task: FieldTask;
  scope: "fatigue_recent_borg" | "ams_morning_next_ascent";
  scope_description: string;
  input_features: string[];
  required_features: string[];
  input_ranges: Record<string, [number, number]>;
  imputation: number[];
  runtime_eligible: boolean;
  eligibility_reason: string;
  clinical_or_general_field_approved: false;
  historical_test_reused: boolean;
  dataset_sha256: string;
  selection_sha256: string;
  protocol_sha256: string;
  calibration: { coef: number; intercept: number } | null;
  threshold: number | null;
  classifier: PortableClassifier;
}
export interface FieldPrediction {
  task: FieldTask;
  status: FieldStatus;
  value: number | null;
  score: number | null;
  label: string | null;
  modelId: string | null;
  assessedAt: number;
  reason: string;
  scope: string;
}

export const fieldUnavailable = (task: FieldTask, status: FieldStatus, reason: string, assessedAt = Date.now(), model: FieldModel | null = null): FieldPrediction =>
  ({ task, status, value: null, score: null, label: null, modelId: model?.id ?? null, assessedAt, reason, scope: model?.scope_description ?? "" });

const sigmoid = (x: number) => x >= 0 ? 1 / (1 + Math.exp(-x)) : Math.exp(x) / (1 + Math.exp(x));
const softmax = (values: number[]) => {
  const max = Math.max(...values);
  const exps = values.map(value => Math.exp(value - max));
  const total = exps.reduce((sum, value) => sum + value, 0);
  return exps.map(value => value / total);
};
const normalized = (values: number[]) => {
  const total = values.reduce((sum, value) => sum + value, 0);
  if (!values.length || !values.every(value => Number.isFinite(value) && value >= 0) || total <= 0) throw new Error("Distribución inválida.");
  return values.map(value => value / total);
};
const dense = (input: number[], coefficients: number[][], intercepts: number[]) => {
  if (coefficients.length !== input.length || !coefficients.every(row => row.length === intercepts.length)) throw new Error("Dimensiones inválidas.");
  return intercepts.map((bias, column) => coefficients.reduce((sum, row, index) => sum + input[index] * row[column], bias));
};
const activate = (input: number[], activation: string): number[] => {
  switch (activation) {
    case "identity": return input;
    case "relu": return input.map(value => Math.max(0, value));
    case "tanh": return input.map(Math.tanh);
    case "logistic": return input.map(sigmoid);
    case "softmax": return softmax(input);
    default: throw new Error("Activación no compatible.");
  }
};

/** Scientific/raw evaluator. App decisions must use predictFieldModel below. */
export function classifierProbabilities(classifier: PortableClassifier, features: number[]): number[] {
  if (features.length !== classifier.feature_order.length || !features.every(Number.isFinite) || classifier.classes.length < 2) throw new Error("Entradas inválidas.");
  if (classifier.type === "random_forest_json") {
    if (!classifier.trees?.length) throw new Error("Bosque vacío.");
    const values = features.map(Math.fround); // sklearn tree comparisons use float32.
    const sum = classifier.classes.map(() => 0);
    for (const tree of classifier.trees) {
      let node = 0;
      let steps = 0;
      while (tree.left[node] !== -1) {
        if (++steps > tree.left.length || !Number.isInteger(node) || node < 0 || node >= tree.left.length ||
            !Number.isInteger(tree.feature[node]) || !Number.isFinite(tree.threshold[node]) ||
            tree.feature[node] < 0 || tree.feature[node] >= values.length) throw new Error("Árbol inválido.");
        node = values[tree.feature[node]] <= tree.threshold[node] ? tree.left[node] : tree.right[node];
      }
      const leaf = tree.value[node];
      if (!leaf || leaf.length !== sum.length) throw new Error("Hoja inválida.");
      normalized(leaf).forEach((value, index) => { sum[index] += value; });
    }
    return normalized(sum);
  }
  if (classifier.type !== "scaled_classifier_json" || !classifier.scaler ||
      classifier.scaler.mean.length !== features.length || classifier.scaler.scale.length !== features.length ||
      !classifier.scaler.scale.every(value => Number.isFinite(value) && value > 0)) throw new Error("Escalado inválido.");
  let values = features.map((value, index) => (value - classifier.scaler!.mean[index]) / classifier.scaler!.scale[index]);
  if (classifier.linear) {
    const { coef, intercept, multiclass } = classifier.linear;
    if (coef.length !== intercept.length || !coef.every(row => row.length === values.length)) throw new Error("Modelo lineal inválido.");
    const scores = coef.map((row, index) => row.reduce((sum, value, j) => sum + value * values[j], intercept[index]));
    if (scores.length === 1) { const p = sigmoid(scores[0]); return normalized([1-p, p]); }
    return multiclass === "multinomial" ? normalized(softmax(scores)) : normalized(scores.map(sigmoid));
  }
  const network = classifier.network;
  if (!network || !network.coefs.length || network.coefs.length !== network.intercepts.length) throw new Error("Red inválida.");
  network.coefs.forEach((coefficients, index) => {
    values = activate(dense(values, coefficients, network.intercepts[index]), index === network.coefs.length-1 ? network.out_activation : network.activation);
  });
  return normalized(values.length === 1 ? [1-values[0], values[0]] : values);
}

export function fieldVector(model: FieldModel, input: FieldFeatures): number[] {
  if (model.imputation.length !== model.input_features.length || !model.imputation.every(Number.isFinite)) throw new Error("Imputación inválida.");
  const observed = model.input_features.map(name => input[name]);
  if (observed.some(value => typeof value === "number" && !Number.isFinite(value))) throw new Error("Entrada no finita.");
  return observed.map((value, index) => value ?? model.imputation[index]).concat(observed.map(value => value == null ? 1 : 0));
}

export function fieldDecision(model: FieldModel, probabilities: number[]): { value: number | null; score: number | null; label: string } {
  if (probabilities.length !== model.classifier.classes.length) throw new Error("Clases inválidas.");
  if (model.task === "fatigue") {
    const ordered = model.classifier.classes.map((label, index) => ({ label, value: Number(label.replace(/^Borg /, "")), probability: probabilities[index] })).sort((a, b) => a.value-b.value);
    if (!ordered.every(item => Number.isFinite(item.value) && item.value >= 0 && item.value <= 10)) throw new Error("Escala Borg inválida.");
    let cumulative = 0;
    const selected = ordered.find(item => (cumulative += item.probability) >= .5) ?? ordered[ordered.length-1];
    return { value: selected.value, score: null, label: selected.label };
  }
  const positive = model.classifier.classes.indexOf("AMS+");
  if (positive < 0 || !model.calibration || model.threshold === null || !Number.isFinite(model.threshold) || model.threshold < 0 || model.threshold > 1) throw new Error("Calibración inválida.");
  const p = Math.min(1-1e-6, Math.max(1e-6, probabilities[positive]));
  const score = sigmoid(Math.log(p/(1-p)) * model.calibration.coef + model.calibration.intercept);
  if (!Number.isFinite(score)) throw new Error("Puntuación inválida.");
  return { value: null, score, label: score >= model.threshold ? "AMS+" : "AMS-" };
}

export function predictFieldModel(model: FieldModel | null, task: FieldTask, input: FieldFeatures, scope: string, assessedAt = Date.now()): FieldPrediction {
  if (!model || model.runtime_eligible !== true) return fieldUnavailable(task, "not_eligible", model?.eligibility_reason ?? "Todavía no hay un candidato evaluado para este control.", assessedAt, model);
  if (model.schema_version !== 1 || model.task !== task || model.clinical_or_general_field_approved !== false ||
      ![model.dataset_sha256, model.selection_sha256, model.protocol_sha256].every(hash => /^[a-f0-9]{64}$/.test(hash))) return fieldUnavailable(task, "invalid_model", "El artefacto no coincide con el protocolo evaluado.", assessedAt, model);
  if (scope !== model.scope) return fieldUnavailable(task, "outside_scope", "Este modelo corresponde a otro momento de evaluación.", assessedAt, model);
  if (model.required_features.some(name => input[name] == null || !Number.isFinite(input[name]))) return fieldUnavailable(task, "missing_inputs", "Faltan mediciones o autorreportes compatibles con este control.", assessedAt, model);
  for (const name of model.input_features) {
    const value = input[name];
    const range = model.input_ranges[name];
    if (value != null && (!Number.isFinite(value) || !range || value < range[0] || value > range[1])) return fieldUnavailable(task, "outside_scope", "Una entrada está fuera del rango observado durante el entrenamiento.", assessedAt, model);
  }
  try {
    const decision = fieldDecision(model, classifierProbabilities(model.classifier, fieldVector(model, input)));
    return { task, status: "available", ...decision, modelId: model.id, assessedAt, reason: "Estimación orientativa dentro del alcance público evaluado.", scope: model.scope_description };
  } catch {
    return fieldUnavailable(task, "invalid_model", "No pudimos evaluar este artefacto. Podés continuar usando el mapa y los avisos de lectura.", assessedAt, model);
  }
}

export interface BorgCheckin { borg: number; recordedAt: number }
export function fatigueInputs(hr: number | null, checkins: BorgCheckin[], now: number): FieldFeatures {
  const history = checkins.filter(row => Number.isFinite(row.borg) && row.borg >= 0 && row.borg <= 10 && Number.isFinite(row.recordedAt) && row.recordedAt <= now-60000 && row.recordedAt >= now-15*60000).sort((a, b) => b.recordedAt-a.recordedAt);
  return { hr, prior_borg: history[0]?.borg ?? null, prior_age_minutes: history[0] ? (now-history[0].recordedAt)/60000 : null,
    prior2_borg: history[1]?.borg ?? null, prior2_age_minutes: history[1] ? (now-history[1].recordedAt)/60000 : null };
}
