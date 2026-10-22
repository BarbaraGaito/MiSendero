import contract from "./modelContract.json";
import raw from "./fallModel.json";
import type { Classification } from "./detector";

// Pure-TypeScript tree-ensemble evaluator: no native module, no network. Equivalence with the Python
// model is checked in __tests__/fallDetection.test.ts against vectors exported by export_model.py.
interface XgbTree { feature: number[]; threshold: number[]; yes: number[]; no: number[]; leaf: number[] }
interface ForestTree { feature: number[]; threshold: number[]; left: number[]; right: number[]; p1: number[] }

export interface FallModelFile {
  schema_version: 1;
  id: string;
  version: string;
  algorithm: "xgboost" | "random_forest";
  status: "experimental";
  deployment_approved: false;
  trained_at: string;
  threshold: number;
  feature_order: string[];
  xgboost?: { base_margin: number; trees: XgbTree[] };
  random_forest?: { trees: ForestTree[] };
}

export interface FallModel {
  id: string;
  version: string;
  algorithm: FallModelFile["algorithm"];
  threshold: number;
  classify: (features: number[]) => Classification;
}

export const buildFallModel = (file: FallModelFile): FallModel => {
  if (file.schema_version !== 1) throw new Error("Versión de esquema del modelo no soportada.");
  if (file.deployment_approved !== false || file.status !== "experimental") throw new Error("El modelo debe figurar como experimental.");
  if (file.feature_order.length !== contract.features.order.length || file.feature_order.some((name, i) => name !== contract.features.order[i])) {
    throw new Error("El modelo y el preprocesamiento no usan las mismas características.");
  }
  if (!(file.threshold > 0 && file.threshold < 1)) throw new Error("Umbral del modelo inválido.");
  const width = file.feature_order.length;
  const check = (x: number[]) => {
    if (x.length !== width || x.some((value) => !Number.isFinite(value))) throw new Error("Vector de características inválido.");
  };
  if (file.algorithm === "xgboost" && file.xgboost?.trees.length) {
    const base = file.xgboost.base_margin;
    // Typed arrays keep the exact float32 thresholds and a small, flat memory footprint.
    const trees = file.xgboost.trees.map((tree) => ({
      feature: Int16Array.from(tree.feature), threshold: Float32Array.from(tree.threshold),
      yes: Int16Array.from(tree.yes), no: Int16Array.from(tree.no), leaf: Float32Array.from(tree.leaf),
    }));
    return { id: file.id, version: file.version, algorithm: file.algorithm, threshold: file.threshold, classify: (x) => {
      check(x);
      let margin = base;
      for (const tree of trees) {
        let node = 0;
        // xgboost compares float32 features with `<` against the float32 split value.
        while (tree.feature[node] >= 0) node = Math.fround(x[tree.feature[node]]) < tree.threshold[node] ? tree.yes[node] : tree.no[node];
        margin += tree.leaf[node];
      }
      return { probability: 1 / (1 + Math.exp(-margin)) };
    } };
  }
  if (file.algorithm === "random_forest" && file.random_forest?.trees.length) {
    const { trees } = file.random_forest;
    return { id: file.id, version: file.version, algorithm: file.algorithm, threshold: file.threshold, classify: (x) => {
      check(x);
      let sum = 0;
      for (const tree of trees) {
        let node = 0;
        while (tree.left[node] !== -1) node = Math.fround(x[tree.feature[node]]) <= tree.threshold[node] ? tree.left[node] : tree.right[node];
        sum += tree.p1[node];
      }
      return { probability: sum / trees.length };
    } };
  }
  throw new Error("El archivo del modelo no contiene árboles.");
};

let cached: FallModel | null = null;
export const loadFallModel = (): FallModel => cached ??= buildFallModel(raw as unknown as FallModelFile);
export const FALL_MODEL_FILE = raw as unknown as FallModelFile;
