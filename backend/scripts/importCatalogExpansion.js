const path = require("path");
const { createHash } = require("crypto");
const { z } = require("zod");
const { batch, trails } = require("../src/data/catalogExpansion20261017");

const normalizeName = (value) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const sourceSchema = z.object({ title: z.string().min(1), url: z.url().refine((url) => {
  const parsed = new URL(url);
  return parsed.protocol === "https:" && ["www.argentina.gob.ar", "barilochetrekking.com", "patagonia.gob.ar", "www.barilocheturismo.gob.ar"].includes(parsed.hostname);
}) });
const trailSchema = z.object({
  name: z.string().min(3), location: z.string().min(3), difficulty: z.enum(["Baja", "Media", "Alta"]),
  duration: z.string().min(1), distance_km: z.number().positive(), description: z.string().min(15),
  image_url: z.null(), center_lat: z.null(), center_lng: z.null(), map_zoom: z.null(), route_coordinates: z.null(),
  provenance: z.object({ catalog_batch: z.literal(batch), catalog_key: z.string().min(1), checked_at: z.iso.date(),
    province: z.string().min(1), area: z.string().min(1), route_type: z.enum(["out_and_back", "loop", "point_to_point"]),
    duration_basis: z.enum(["official_round_trip", "round_trip_from_official_one_way", "official_one_way", "official_circuit"]),
    sources: z.array(sourceSchema).min(1), aliases: z.array(z.string()), access: z.string().min(1), precautions: z.string().min(1),
    duration_minutes_min: z.number().positive(), duration_minutes_max: z.number().positive(), duration_is_derived: z.boolean(),
    recommendation: z.object({ trail_types: z.array(z.enum(["naturaleza", "montaña", "cascadas", "lagos", "bosques", "miradores"])).min(1), terrain: z.array(z.string()).nullable(), source_url: z.url() }),
    training: z.object({ record_type: z.literal("verified_catalog_features"), relevance_label: z.null(), synthetic: z.literal(false) }),
  }).passthrough(),
});

function validateCatalog(entries = trails) {
  const keys = new Set();
  const names = new Set();
  for (const entry of entries) {
    trailSchema.parse(entry);
    const p = entry.provenance;
    if (keys.has(p.catalog_key) || names.has(normalizeName(entry.name))) throw new Error("Duplicate catalog key/name");
    if (p.duration_minutes_max < p.duration_minutes_min) throw new Error("Invalid duration interval");
    if (!p.sources.some((s) => s.url === p.recommendation.source_url)) throw new Error("Undocumented landscape source");
    keys.add(p.catalog_key);
    names.add(normalizeName(entry.name));
  }
  return entries;
}

function duplicate(entry, rows) {
  const names = new Set([entry.name, ...entry.provenance.aliases].map(normalizeName));
  return rows.find((row) => row.provenance?.catalog_key === entry.provenance.catalog_key ||
    [row.name, ...(row.provenance?.aliases || [])].some((name) => names.has(normalizeName(name))));
}

// Explicit additive transaction: never runs migrations, seeds, UPDATE or DELETE.
async function importCatalog(client, { apply = false, entries = trails } = {}) {
  validateCatalog(entries);
  const report = { batch, mode: apply ? "apply" : "dry-run", before: 0, after: 0, inserted: [], pending: [], skipped: [] };
  await client.query("BEGIN");
  try {
    if (apply) await client.query("LOCK TABLE trails IN SHARE ROW EXCLUSIVE MODE");
    const { rows } = await client.query("SELECT * FROM trails ORDER BY id");
    const originalIds = new Set(rows.map((row) => row.id));
    const digest = (values) => createHash("sha256").update(JSON.stringify(values)).digest("hex");
    const originalDigest = digest(rows);
    report.before = rows.length;
    for (const entry of entries) {
      const existing = duplicate(entry, rows);
      if (existing) { report.skipped.push({ name: entry.name, existingId: existing.id, existingName: existing.name }); continue; }
      if (!apply) { report.pending.push(entry.name); rows.push({ name: entry.name, provenance: entry.provenance }); continue; }
      const result = await client.query(`INSERT INTO trails
        (name, location, difficulty, duration, distance_km, description, image_url, center_lat, center_lng, map_zoom, route_coordinates, provenance)
        VALUES ($1,$2,$3,$4,$5,$6,NULL,NULL,NULL,NULL,NULL,$7)
        ON CONFLICT (name) DO NOTHING RETURNING id`,
      [entry.name, entry.location, entry.difficulty, entry.duration, entry.distance_km, entry.description, JSON.stringify(entry.provenance)]);
      if (!result.rows[0]) throw new Error("Concurrent catalog change; retry the import");
      rows.push({ id: result.rows[0].id, name: entry.name, provenance: entry.provenance });
      report.inserted.push({ id: result.rows[0].id, name: entry.name });
    }
    report.after = report.before + report.inserted.length;
    if (apply) {
      const after = (await client.query("SELECT * FROM trails ORDER BY id")).rows;
      const preserved = after.filter((row) => originalIds.has(row.id));
      if (digest(preserved) !== originalDigest || after.length !== report.after) throw new Error("Catalog integrity check failed; rolling back");
      report.existingRowsPreserved = true;
      report.existingRowsSha256 = originalDigest;
    }
    await client.query(apply ? "COMMIT" : "ROLLBACK");
    return report;
  } catch (error) { await client.query("ROLLBACK"); throw error; }
}

function assertLocalDatabase(env = process.env) {
  let host;
  try { host = env.DATABASE_URL ? new URL(env.DATABASE_URL).hostname : env.PGHOST; }
  catch { throw new Error("Invalid database configuration (credentials omitted)"); }
  if (!["localhost", "127.0.0.1", "[::1]", "::1"].includes(host)) {
    throw new Error("Local-only import refused: target is not a loopback database. RDS was not modified.");
  }
}

async function main() {
  require("dotenv").config({ path: path.resolve(__dirname, "../.env"), quiet: true });
  const args = process.argv.slice(2);
  if (args.some((a) => !["--apply", "--dry-run", "--local-only"].includes(a)) || (args.includes("--apply") && args.includes("--dry-run"))) throw new Error("Usage: --dry-run | --apply --local-only");
  if (args.includes("--apply") && !args.includes("--local-only")) throw new Error("Apply requires --local-only");
  assertLocalDatabase(); // Even dry-run is confined to the local DB in this CLI.
  const { getPool } = require("../src/db");
  const pool = await getPool();
  try {
    const client = await pool.connect();
    try { console.log(JSON.stringify(await importCatalog(client, { apply: args.includes("--apply") }), null, 2)); }
    finally { client.release(); }
  } finally { await pool.end(); }
}

module.exports = { importCatalog, validateCatalog, normalizeName, duplicate, assertLocalDatabase };
if (require.main === module) main().catch((error) => {
  // PG errors may contain connection details; do not print environment or passwords.
  console.error(error.code ? `Catalog import failed (${error.code}); no partial import committed.` : error.message);
  process.exitCode = 1;
});
