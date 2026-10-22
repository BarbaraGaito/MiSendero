const { getPool, query } = require("./db");
const { geometryHash, checksum, verifyArtifact, reviewedAssociation } = require("./environmental");
const { validateBatch, batchBody } = require("./contracts/environmental");
const registry = require("./data/environmentalModels.json");

async function importEnvironmentalBatch(raw, apply = false, now = Date.now()) {
  const { rows } = await query("SELECT id, center_lat, center_lng, route_coordinates FROM trails WHERE id = $1", [raw?.trail_id]);
  if (!rows.length) throw new Error("environmental-import:unknown-trail");
  const batch = validateBatch(raw, rows[0].id, geometryHash(rows[0]));
  if (checksum(batchBody(batch)) !== batch.payload_sha256) throw new Error("environmental-import:checksum");
  const prepared = [];
  for (const snapshot of batch.snapshots) {
    if (!snapshot.prediction) continue;
    if (!["experimental", "available"].includes(snapshot.status) || !verifyArtifact(snapshot)) throw new Error("environmental-import:unapproved-artifact");
    if (Date.parse(snapshot.issued_at) > now || Date.parse(snapshot.valid_until) <= now) throw new Error("environmental-import:invalid-validity");
    const association = reviewedAssociation(snapshot);
    if (!association) throw new Error("environmental-import:unreviewed-geographic-association");
    const artifact = registry.artifacts[snapshot.model_id];
    if (snapshot.model_type === "river_level" && (snapshot.prediction.station_id !== association.station_id
      || snapshot.prediction.river_name !== association.river_name || snapshot.prediction.station_name !== artifact.station_name
      || snapshot.prediction.historical_mae_m !== artifact.historical_mae_m)) throw new Error("environmental-import:station-evidence-mismatch");
    prepared.push(snapshot);
  }
  if (apply && prepared.length) {
    const client = await (await getPool()).connect();
    try {
      await client.query("BEGIN");
      for (const s of prepared) await client.query(`INSERT INTO environmental_snapshots
        (snapshot_id, trail_id, model_type, issued_at, valid_until, payload) VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (snapshot_id) DO NOTHING`, [checksum(s), s.trail_id, s.model_type, s.issued_at, s.valid_until, JSON.stringify(s)]);
      await client.query("COMMIT");
    } catch (error) { await client.query("ROLLBACK"); throw error; }
    finally { client.release(); }
  }
  return { applied: apply, snapshots: prepared.length, trail_id: batch.trail_id };
}

module.exports = { importEnvironmentalBatch };
