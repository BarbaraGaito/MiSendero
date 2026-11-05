// Shared runtime contract for Node and Expo, shipped in the backend image.
// No Node/native dependencies.
const MODEL_TYPES = ["snow", "river_level", "fire_detection"];
const STATUSES = ["available", "experimental", "no_data", "not_approved", "expired", "error"];
const record = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const text = (v) => typeof v === "string" && v.length > 0 && v.length <= 4000;
const date = (v) => text(v) && /(?:Z|[+-]\d\d:\d\d)$/.test(v) && Number.isFinite(Date.parse(v));
const hash = (v) => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
const https = (v) => text(v) && /^https:\/\/[^\s]+$/.test(v);
const finite = (v) => typeof v === "number" && Number.isFinite(v);
const assert = (ok, message) => { if (!ok) throw new Error(`environmental-contract:${message}`); };

function canonicalJSON(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJSON).join(",")}]`;
  if (record(value)) return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJSON(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
}

function geometryCanonical(trail) {
  let route = trail.route_coordinates;
  if (typeof route === "string") { try { route = JSON.parse(route); } catch { throw new Error("environmental-contract:geometry-json"); } }
  if (route == null) route = [];
  assert(Array.isArray(route), "geometry-array");
  const point = (p) => Array.isArray(p) && p.length >= 2 && finite(p[0]) && finite(p[1]) && Math.abs(p[0]) <= 90 && Math.abs(p[1]) <= 180;
  assert(route.every(point), "geometry-coordinate");
  const center = [trail.center_lat, trail.center_lng];
  assert(route.length >= 2 || point(center), "geometry-missing");
  return canonicalJSON({ version: 1, route: route.map((p) => p.slice(0, 2)), center: point(center) ? center : null });
}

function validateSnapshot(s, trailId, geometryHash) {
  assert(record(s) && s.schema_version === 1, "snapshot-version");
  assert(s.trail_id === trailId && s.geometry_hash === geometryHash && hash(geometryHash), "snapshot-route");
  assert(MODEL_TYPES.includes(s.model_type) && STATUSES.includes(s.status), "snapshot-type-status");
  assert(s.model_id === null || text(s.model_id), "model-id");
  assert(s.model_version === null || text(s.model_version), "model-version");
  assert(record(s.source) && text(s.source.name) && https(s.source.url), "source");
  assert(s.source.license === null || text(s.source.license), "source-license");
  assert(record(s.geographic_scope) && text(s.geographic_scope.description), "scope");
  assert(Array.isArray(s.limitations) && s.limitations.length <= 20 && s.limitations.every(text), "limitations");
  assert(s.evidence_sha256 === null || hash(s.evidence_sha256), "evidence");
  for (const key of ["observed_at", "inputs_available_at", "issued_at", "target_at", "valid_until"]) assert(s[key] === null || date(s[key]), key);
  const numeric = ["available", "experimental", "expired"].includes(s.status);
  if (!numeric) { assert(s.prediction === null, "unavailable-value"); return s; }
  assert(text(s.model_id) && text(s.model_version) && hash(s.evidence_sha256), "numeric-provenance");
  assert(["observed_at", "inputs_available_at", "issued_at", "target_at", "valid_until"].every((k) => date(s[k])), "numeric-dates");
  assert(Date.parse(s.observed_at) <= Date.parse(s.inputs_available_at) && Date.parse(s.inputs_available_at) <= Date.parse(s.issued_at)
    && Date.parse(s.issued_at) < Date.parse(s.target_at) && Date.parse(s.target_at) <= Date.parse(s.valid_until), "temporal-order");
  assert(record(s.prediction), "prediction");
  if (s.model_type === "river_level") {
    const p = s.prediction;
    assert(finite(p.level_m) && finite(p.latest_level_m) && finite(p.historical_mae_m) && p.historical_mae_m >= 0, "river-values");
    assert(Number.isInteger(p.station_id) && p.station_id > 0 && text(p.station_name) && text(p.river_name) && [3, 6].includes(p.horizon_hours), "river-station");
    assert(Date.parse(s.target_at) - Date.parse(s.issued_at) === p.horizon_hours * 3600000, "river-horizon");
  } else {
    assert(finite(s.prediction.probability) && s.prediction.probability >= 0 && s.prediction.probability <= 1 && s.prediction.horizon_hours === 24, "probability");
    assert(Date.parse(s.target_at) - Date.parse(s.issued_at) === 24 * 3600000, "satellite-horizon");
    if (s.model_type === "fire_detection") {
      const scope = s.geographic_scope;
      assert(/^h\d{2}v\d{2}:\d{1,4}:\d{1,4}$/.test(scope.pixel_id) && finite(scope.latitude) && Math.abs(scope.latitude) <= 90
        && finite(scope.longitude) && Math.abs(scope.longitude) <= 180, "fire-pixel-scope");
    }
  }
  return s;
}

function batchBody(batch) {
  return { schema_version: batch.schema_version, trail_id: batch.trail_id, geometry_hash: batch.geometry_hash,
    generated_at: batch.generated_at, snapshots: batch.snapshots };
}

function validateBatch(batch, trailId, geometryHash) {
  assert(record(batch) && batch.schema_version === 1 && batch.trail_id === trailId && batch.geometry_hash === geometryHash, "batch-route-version");
  assert(date(batch.generated_at) && hash(batch.payload_sha256), "batch-metadata");
  assert(Array.isArray(batch.snapshots) && batch.snapshots.length >= 3 && batch.snapshots.length <= 8, "batch-size");
  const keys = new Set();
  for (const s of batch.snapshots) {
    validateSnapshot(s, trailId, geometryHash);
    if (s.prediction) assert(Date.parse(s.issued_at) <= Date.parse(batch.generated_at), "batch-issue-time");
    const key = `${s.model_type}:${s.model_id}`;
    assert(!keys.has(key), "duplicate-model"); keys.add(key);
  }
  assert(MODEL_TYPES.every((type) => batch.snapshots.some((s) => s.model_type === type)), "missing-model-status");
  return batch;
}

function visibleSnapshots(batch, now = Date.now()) {
  return batch.snapshots.map((s) => ["available", "experimental"].includes(s.status) && Date.parse(s.valid_until) <= now
    ? { ...s, status: "expired" } : s);
}

module.exports = { MODEL_TYPES, STATUSES, canonicalJSON, geometryCanonical, validateSnapshot, validateBatch, batchBody, visibleSnapshots };
