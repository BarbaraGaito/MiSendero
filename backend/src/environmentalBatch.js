// Prepare route files offline. Database import independently checks the actual
// stored route geometry; no association is inferred from station proximity.
const { checksum, verifyArtifact, reviewedAssociation } = require("./environmental");
const { MODEL_TYPES, validateBatch } = require("./contracts/environmental");
const registry = require("./data/environmentalModels.json");

function buildEnvironmentalBatches(run, now = Date.now()) {
  if (run?.schema_version !== 1 || !Array.isArray(run.forecasts)) throw new Error("environmental-export:station-run");
  const grouped = new Map();
  for (const link of registry.reviewed_route_associations) {
    const forecast = run.forecasts.find((f) => f.model_id === link.model_id && f.status === "experimental");
    if (!forecast || Date.parse(forecast.valid_until) <= now) continue;
    if (!Number.isSafeInteger(link.trail_id) || link.trail_id <= 0) throw new Error("environmental-export:trail-id");
    const type = registry.artifacts[forecast.model_id]?.model_type;
    if (!["river_level", "fire_detection"].includes(type)) throw new Error("environmental-export:unsupported-model");
    if (type === "fire_detection" && forecast.region_geometry_hash !== link.geometry_hash) throw new Error("environmental-export:fire-sector-geometry");
    const snapshot = {
      schema_version: 1, trail_id: link.trail_id, geometry_hash: link.geometry_hash,
      model_type: type, model_id: forecast.model_id, model_version: forecast.model_version,
      status: "experimental", source: registry.models[type].source,
      prediction: type === "river_level" ? { station_id: forecast.series_id, station_name: forecast.station_name, river_name: link.river_name,
        horizon_hours: forecast.horizon_hours, level_m: forecast.level_m, latest_level_m: forecast.latest_level_m,
        historical_mae_m: forecast.historical_mae_m } : forecast.prediction,
      observed_at: forecast.observed_at, inputs_available_at: forecast.inputs_available_at,
      issued_at: forecast.issued_at, target_at: forecast.target_at, valid_until: forecast.valid_until,
      evidence_sha256: forecast.evidence_sha256,
      geographic_scope: type === "fire_detection" ? forecast.geographic_scope : { description: link.description || `Estación ${forecast.station_name}; relación hidrológica revisada para este sector.` },
      limitations: registry.models[type].limitations,
    };
    if (!verifyArtifact(snapshot) || !reviewedAssociation(snapshot) || Date.parse(snapshot.issued_at) > now) {
      throw new Error("environmental-export:unreviewed-or-incompatible-forecast");
    }
    const key = `${link.trail_id}:${link.geometry_hash}`;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(snapshot);
  }
  const batches = [];
  for (const snapshots of grouped.values()) {
    const { trail_id, geometry_hash } = snapshots[0];
    for (const type of MODEL_TYPES) {
      if (snapshots.some((s) => s.model_type === type)) continue;
      const model = registry.models[type];
      snapshots.push({ schema_version: 1, trail_id, geometry_hash, model_type: type, model_id: null,
        model_version: null, status: model.fallback_status === "not_approved" ? "not_approved" : "no_data", prediction: null, source: model.source,
        observed_at: null, inputs_available_at: null, issued_at: null, target_at: null, valid_until: null,
        evidence_sha256: null, geographic_scope: { description: model.unavailable_message }, limitations: model.limitations });
    }
    const body = { schema_version: 1, trail_id, geometry_hash, generated_at: new Date(now).toISOString(), snapshots };
    batches.push(validateBatch({ ...body, payload_sha256: checksum(body) }, trail_id, geometry_hash));
  }
  return batches;
}

module.exports = { buildEnvironmentalBatches };
