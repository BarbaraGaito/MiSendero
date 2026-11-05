const { createHash } = require("node:crypto");
const { query } = require("./db");
const contract = require("./contracts/environmental");
const registry = require("./data/environmentalModels.json");
const geometryHash = (trail) => createHash("sha256").update(contract.geometryCanonical(trail)).digest("hex");
const checksum = (value) => createHash("sha256").update(contract.canonicalJSON(value)).digest("hex");

function unavailable(trail, hash, modelType, status = "no_data") {
  const model = registry.models[modelType];
  if (status === "no_data" && model.fallback_status === "not_approved") status = "not_approved";
  return { schema_version: 1, trail_id: trail.id, geometry_hash: hash, model_type: modelType,
    model_id: null, model_version: null, status, prediction: null, source: model.source,
    observed_at: null, inputs_available_at: null, issued_at: null, target_at: null, valid_until: null,
    evidence_sha256: null, geographic_scope: { description: model.unavailable_message }, limitations: model.limitations };
}

function verifyArtifact(snapshot) {
  const artifact = registry.artifacts[snapshot.model_id];
  if (!artifact || artifact.visualization_allowed !== true || artifact.model_type !== snapshot.model_type || artifact.version !== snapshot.model_version || artifact.evidence_sha256 !== snapshot.evidence_sha256) return false;
  if (snapshot.status === "available" && artifact.deployment_approved !== true) return false;
  if (snapshot.model_type === "river_level" && (artifact.series_id !== snapshot.prediction?.station_id || artifact.horizon_hours !== snapshot.prediction?.horizon_hours
    || artifact.station_name !== snapshot.prediction?.station_name || artifact.historical_mae_m !== snapshot.prediction?.historical_mae_m)) return false;
  return true;
}

function reviewedAssociation(snapshot) {
  return registry.reviewed_route_associations.find((link) => link.trail_id === snapshot.trail_id
    && link.geometry_hash === snapshot.geometry_hash && link.model_id === snapshot.model_id
    && Array.isArray(link.sources) && link.sources.length > 0 && link.sources.every((s) => /^https:\/\//.test(s.url))
    && Number.isFinite(Date.parse(link.reviewed_at)) && Date.parse(link.reviewed_at) <= Date.parse(snapshot.issued_at)
    && (snapshot.model_type !== "river_level" || (link.station_id === snapshot.prediction?.station_id && link.river_name === snapshot.prediction?.river_name))
    && (snapshot.model_type !== "fire_detection" || link.pixel_id === snapshot.geographic_scope.pixel_id));
}

async function getEnvironmentalBatch(trail, now = Date.now()) {
  const hash = geometryHash(trail);
  let rows, storageFailed = false;
  try { rows = (await query("SELECT payload FROM environmental_snapshots WHERE trail_id = $1 ORDER BY issued_at DESC", [trail.id])).rows; }
  catch { rows = []; storageFailed = true; }
  const snapshots = [], seen = new Set();
  for (const row of rows) {
    try {
      const s = contract.validateSnapshot(row.payload, trail.id, hash);
      if (!verifyArtifact(s) || !reviewedAssociation(s) || seen.has(s.model_id) || Date.parse(s.issued_at) > now) continue;
      seen.add(s.model_id); snapshots.push(s);
    } catch { /* Incompatible geometry, unapproved artifact or corrupt stored payload. */ }
  }
  for (const type of contract.MODEL_TYPES) if (!snapshots.some((s) => s.model_type === type)) snapshots.push(unavailable(trail, hash, type, storageFailed ? "error" : "no_data"));
  const body = { schema_version: 1, trail_id: trail.id, geometry_hash: hash,
    generated_at: new Date(now).toISOString(), snapshots: contract.visibleSnapshots({ snapshots }, now) };
  const batch = { ...body, payload_sha256: checksum(body) };
  return contract.validateBatch(batch, trail.id, hash);
}

module.exports = { geometryHash, checksum, getEnvironmentalBatch, verifyArtifact, reviewedAssociation };
