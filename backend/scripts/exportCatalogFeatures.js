const fs = require("fs");
const path = require("path");
const { assertLocalDatabase } = require("./importCatalogExpansion");

function featureRecord(row) {
  const p = row.provenance;
  return {
    schema_version: 1, record_type: "catalog_features", trail_id: row.id,
    catalog_key: p?.catalog_key ?? null, name: row.name, location: row.location,
    province: p?.province ?? null, area: p?.area ?? null,
    difficulty_recorded: row.difficulty, difficulty_native: p?.native?.difficulty ?? null,
    duration_recorded: row.duration, duration_minutes_min: p?.duration_minutes_min ?? null,
    duration_minutes_max: p?.duration_minutes_max ?? null, duration_basis: p?.duration_basis ?? null,
    duration_is_derived: p?.duration_is_derived ?? null,
    distance_km: row.distance_km == null ? null : Number(row.distance_km), distance_basis: p?.distance_basis ?? null,
    route_type: p?.route_type ?? null, trail_types: p?.recommendation?.trail_types ?? null,
    terrain: p?.recommendation?.terrain ?? null, accumulated_ascent_m: null,
    guide: p?.guide ?? null, registration_required: p?.registration_required ?? null,
    source_reviewed_at: p?.checked_at ?? null, sources: p?.sources ?? [],
    provenance: p ?? null, synthetic: false, relevance_label: null,
  };
}

async function main() {
  require("dotenv").config({ path: path.resolve(__dirname, "../.env"), quiet: true });
  assertLocalDatabase();
  const { getPool } = require("../src/db");
  const pool = await getPool();
  try {
    const { rows } = await pool.query("SELECT id, name, location, difficulty, duration, distance_km, provenance FROM trails ORDER BY id");
    const directory = path.resolve(__dirname, "../../training/data/catalog");
    fs.mkdirSync(directory, { recursive: true });
    const filename = path.join(directory, "misendero-catalog.jsonl");
    fs.writeFileSync(filename, rows.map((r) => JSON.stringify(featureRecord(r))).join("\n") + "\n", "utf8");
    console.log(JSON.stringify({ records: rows.length, labeled_examples: 0, file: "training/data/catalog/misendero-catalog.jsonl" }));
  } finally { await pool.end(); }
}
module.exports = { featureRecord };
if (require.main === module) main().catch((error) => { console.error(error.code ? `Export failed (${error.code})` : error.message); process.exitCode = 1; });
