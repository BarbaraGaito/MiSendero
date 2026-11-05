// SOFTWARE TEST FIXTURES ONLY. Never acquisition/training/evaluation evidence.
const { createHash } = require("node:crypto");
const { geometryCanonical, canonicalJSON } = require("../../backend/src/contracts/environmental");
const fixtureTrail = { id: 7, name: "Software fixture", location: "Test", difficulty: "Media", duration: null, distance_km: null,
  description: null, image_url: null, center_lat: -41, center_lng: -71, map_zoom: 12,
  route_coordinates: "[[-41,-71],[-41.01,-71]]", created_at: "2026-10-22" };
const digest = (v) => createHash("sha256").update(v).digest("hex");
const now = Date.parse("2026-10-22T12:30:00Z");
function makeBatch(trail = fixtureTrail, level = 1.23) {
  const geometryHash = digest(geometryCanonical(trail));
  const snapshots = ["snow", "river_level", "fire_detection"].map((type) => ({
    schema_version: 1, trail_id: trail.id, geometry_hash: geometryHash, model_type: type,
    model_id: null, model_version: null, status: "no_data", prediction: null,
    source: { name: "Software fixture", url: "https://example.invalid/software-fixture", license: null },
    observed_at: null, inputs_available_at: null, issued_at: null, target_at: null, valid_until: null,
    evidence_sha256: null, geographic_scope: { description: "Software test scope" }, limitations: ["Software fixture; not a scientific result."]
  }));
  Object.assign(snapshots[1], { model_id: "fixture-river-3h", model_version: "1", status: "experimental",
    prediction: { station_id: 42, station_name: "Fixture station", river_name: "Fixture river", horizon_hours: 3,
      level_m: level, latest_level_m: 1.2, historical_mae_m: 0.1 },
    observed_at: "2026-10-22T10:00:00Z", inputs_available_at: "2026-10-22T11:00:00Z", issued_at: "2026-10-22T12:00:00Z",
    target_at: "2026-10-22T15:00:00Z", valid_until: "2026-10-22T15:00:00Z", evidence_sha256: "a".repeat(64) });
  const body = { schema_version: 1, trail_id: trail.id, geometry_hash: geometryHash, generated_at: "2026-10-22T12:30:00Z", snapshots };
  return { ...body, payload_sha256: digest(canonicalJSON(body)) };
}
const artifact = { model_type: "river_level", version: "1", series_id: 42, station_name: "Fixture station", horizon_hours: 3,
  evidence_sha256: "a".repeat(64), historical_mae_m: 0.1, visualization_allowed: true, deployment_approved: false };
function association(batch) { return { trail_id: batch.trail_id, geometry_hash: batch.geometry_hash, model_id: "fixture-river-3h",
  station_id: 42, river_name: "Fixture river", reviewed_at: "2026-10-21T00:00:00Z", sources: [{ url: "https://example.invalid/software-fixture" }] }; }
module.exports = { fixtureTrail, makeBatch, artifact, association, now };
