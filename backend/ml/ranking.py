"""Supervised pointwise learning to rank. Catalog characteristics are not labels."""
from __future__ import annotations

import hashlib
import json
import math
import platform
import re
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestRegressor

SPEC_PATH = Path(__file__).resolve().parents[1] / "src/ai/featureSpec.json"
SPEC = json.loads(SPEC_PATH.read_text(encoding="utf-8-sig"))
ALGORITHM = "random-forest-pointwise-relevance-v1"
SEED = 42
MINIMUMS = {"rows": 300, "queries": 100, "independent_groups": 10, "trails": 10, "informative_queries": 60}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def spec_sha256() -> str:
    # Canonical JSON avoids Windows CRLF / Linux LF differences in deployment.
    return hashlib.sha256(json.dumps(SPEC, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def matrix(vectors: list) -> np.ndarray:
    if not isinstance(vectors, list) or not 0 < len(vectors) <= 10000:
        raise ValueError("Invalid feature batch")
    for vector in vectors:
        if not isinstance(vector, list) or len(vector) != len(SPEC["names"]):
            raise ValueError("Feature schema mismatch")
        if any(v is not None and (type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e8) for v in vector):
            raise ValueError("Invalid feature number")
    # Native missing-value handling: no invented terrain, elevation or geographic attributes.
    return np.asarray([[np.nan if v is None else v for v in row] for row in vectors], dtype=np.float64)


def baseline(vector: list) -> float:
    weights = SPEC["baselineWeights"]
    return (weights["type_match_fraction"] * vector[1]
            + weights["duration_proximity"] * (vector[2] or 0)
            + weights["effort_margin"] * (2 - vector[5]) / 2)


def estimator() -> RandomForestRegressor:
    # Small tabular, graded relevance, nonlinear interactions, bounded CPU/RAM, native NaN.
    return RandomForestRegressor(n_estimators=80, max_depth=6, min_samples_leaf=3,
                                 n_jobs=1, random_state=SEED)


def read_examples(filename: Path, *, synthetic_test=False) -> list[dict]:
    if not filename.exists():
        return []
    if filename.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("Dataset exceeds offline training limit")
    rows = []
    required = {"queryId", "splitGroupId", "preferenceKey", "trailId", "features", "relevance", "source", "consentVerified", "synthetic", "eligible"}
    seen = set()
    for line in filename.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError("Unexpected prepared label fields")
        if row["synthetic"] is not synthetic_test or row["consentVerified"] is not (not synthetic_test) or row["eligible"] is not True:
            raise ValueError("Only consented, non-synthetic, eligible examples may be trained")
        if row["source"] not in ("expert_judgment", "consented_user_rating"):
            raise ValueError("Unsupported label source")
        for key in ("queryId", "splitGroupId"):
            if not isinstance(row[key], str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", row[key]):
                raise ValueError("Use anonymous study identifiers")
        if not re.fullmatch(r"[a-f0-9]{64}", row["preferenceKey"]):
            raise ValueError("Invalid preference fingerprint")
        if type(row["relevance"]) is not int or not 0 <= row["relevance"] <= 3 or type(row["trailId"]) is not int or row["trailId"] <= 0:
            raise ValueError("Invalid label or catalog identity")
        pair = (row["queryId"], row["trailId"])
        if pair in seen:
            raise ValueError("Duplicate query/trail label")
        seen.add(pair)
        matrix([row["features"]])
        rows.append(row)
    return rows


def query_groups(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["queryId"], []).append(row)
    for group in groups.values():
        if len({(r["splitGroupId"], r["preferenceKey"]) for r in group}) != 1:
            raise ValueError("Inconsistent query group")
    return groups


def components(rows: list[dict]) -> dict[str, str]:
    """Keep participants AND repeated identical preferences together, transitively."""
    parent: dict[str, str] = {}
    def find(key):
        parent.setdefault(key, key)
        if parent[key] != key:
            parent[key] = find(parent[key])
        return parent[key]
    for row in rows:
        a, b = find("participant:" + row["splitGroupId"]), find("preference:" + row["preferenceKey"])
        parent[a] = b
    return {r["queryId"]: find("participant:" + r["splitGroupId"]) for r in rows}


def sufficiency(rows: list[dict]) -> dict:
    queries = query_groups(rows)
    groups = components(rows)
    counts = {"rows": len(rows), "queries": len(queries), "independent_groups": len(set(groups.values())),
              "trails": len({r["trailId"] for r in rows}),
              "informative_queries": sum(len({r["relevance"] for r in q}) > 1 for q in queries.values())}
    return {"counts": counts, "minimums": MINIMUMS,
            "sufficient": all(counts[k] >= minimum for k, minimum in MINIMUMS.items())}


def split_examples(rows: list[dict]) -> tuple[list, list, list]:
    membership = components(rows)
    groups = sorted(set(membership.values()))
    if len(groups) < 10:
        raise ValueError("Insufficient independent groups for 60/20/20 holdout")
    np.random.default_rng(SEED).shuffle(groups)
    n_test = max(2, len(groups) // 5)
    n_val = max(2, len(groups) // 5)
    test_groups, val_groups = set(groups[:n_test]), set(groups[n_test:n_test + n_val])
    train, val, test = [], [], []
    for row in rows:
        (test if membership[row["queryId"]] in test_groups else val if membership[row["queryId"]] in val_groups else train).append(row)
    return train, val, test


def evaluate(rows: list[dict], scores: list[float], catalog_size: int, ks=(1, 3)) -> dict:
    if len(rows) != len(scores) or any(not math.isfinite(float(s)) for s in scores):
        raise ValueError("Invalid evaluation scores")
    groups: dict[str, list] = {}
    for row, score in zip(rows, scores):
        groups.setdefault(row["queryId"], []).append((row, float(score)))
    if not groups:
        raise ValueError("Empty evaluation partition")
    result = {"queries": len(groups), "hard_constraint_match_rate": None, "catalog_coverage_at_1": None}
    selected = set()
    matches = []
    metrics = {f"{name}@{k}": [] for k in ks for name in ("precision", "recall", "ndcg")}
    for group in groups.values():
        # Stable tie break identical to the Node fallback/ranker.
        ordered = sorted(group, key=lambda pair: (-pair[1], pair[0]["trailId"]))
        selected.add(ordered[0][0]["trailId"])
        matches.append(int(ordered[0][0]["eligible"]))
        relevant = sum(r["relevance"] >= 2 for r, _ in group)
        ideal = sorted((r["relevance"] for r, _ in group), reverse=True)
        for k in ks:
            top = ordered[:k]
            hits = sum(r["relevance"] >= 2 for r, _ in top)
            metrics[f"precision@{k}"].append(hits / k)
            if relevant:
                metrics[f"recall@{k}"].append(hits / relevant)
            dcg = sum((2 ** r["relevance"] - 1) / math.log2(i + 2) for i, (r, _) in enumerate(top))
            idcg = sum((2 ** label - 1) / math.log2(i + 2) for i, label in enumerate(ideal[:k]))
            if idcg:
                metrics[f"ndcg@{k}"].append(dcg / idcg)
    for name, values in metrics.items():
        result[name] = float(np.mean(values)) if values else None
        result[name + "_queries"] = len(values)
    result["hard_constraint_match_rate"] = float(np.mean(matches))
    result["catalog_coverage_at_1"] = len(selected) / catalog_size if catalog_size else None
    result["coverage_denominator"] = catalog_size
    return result


def load_artifact(directory: Path, *, synthetic_test=False):
    metadata_path, model_path = directory / "metadata.json", directory / "model.joblib"
    if metadata_path.stat().st_size > 1024 * 1024 or model_path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Artifact too large")
    meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    if meta.get("synthetic") is not False or meta.get("deployable") is not True:
        if not (synthetic_test and meta.get("synthetic") is True and meta.get("technicalTestOnly") is True):
            raise ValueError("Artifact is not approved real-data training")
    if meta.get("algorithm") != ALGORITHM or meta.get("featureSchemaVersion") != SPEC["version"] or meta.get("featureNames") != SPEC["names"]:
        raise ValueError("Artifact schema mismatch")
    if meta.get("featureSpecSha256") != spec_sha256():
        raise ValueError("Feature specification changed")
    if meta.get("sklearnVersion") != sklearn.__version__ or meta.get("numpyVersion") != np.__version__ or meta.get("pythonMinor") != ".".join(platform.python_version_tuple()[:2]):
        raise ValueError("Artifact runtime mismatch")
    if not isinstance(meta.get("modelVersion"), str) or not re.fullmatch(r"[a-zA-Z0-9._-]{1,100}", meta["modelVersion"]):
        raise ValueError("Invalid model version")
    if sha256(model_path) != meta.get("modelSha256"):
        raise ValueError("Artifact checksum mismatch")
    # joblib is pickle-based: load ONLY operator-owned artifacts produced by this pipeline.
    # A checksum detects corruption; it does not establish trust in third-party files.
    model = joblib.load(model_path)
    if type(model) is not RandomForestRegressor or model.n_features_in_ != len(SPEC["names"]):
        raise ValueError("Unexpected fitted estimator")
    model.n_jobs = 1
    return model, meta
