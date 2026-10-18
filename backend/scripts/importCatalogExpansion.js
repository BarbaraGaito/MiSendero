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
  image_url: z.url(), center_lat: z.number().min(-90).max(90).nullable(), center_lng: z.number().min(-180).max(180).nullable(),
  map_zoom: z.number().int().min(1).max(20).nullable(),
  route_coordinates: z.array(z.tuple([z.number().min(-90).max(90), z.number().min(-180).max(180)])).min(2).nullable(),
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
    if (!p.photo?.author || !p.photo?.license || p.photo.url !== entry.image_url || !p.photo.page_url) throw new Error("Undocumented photo");
    if (entry.route_coordinates) {
      if (!p.mapping?.source_url || !p.mapping?.source_sha256 || typeof p.mapping.navigation_ready !== "boolean") throw new Error("Undocumented geometry");
      if (entry.center_lat !== entry.route_coordinates[0][0] || entry.center_lng !== entry.route_coordinates[0][1]) throw new Error("Start differs from mapped geometry");
    } else if (entry.center_lat !== null || entry.center_lng !== null || entry.map_zoom !== null) throw new Error("Coordinates without geometry");
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
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
        ON CONFLICT (name) DO NOTHING RETURNING id`,
      [entry.name, entry.location, entry.difficulty, entry.duration, entry.distance_km, entry.description,
        entry.image_url, entry.center_lat, entry.center_lng, entry.map_zoom, JSON.stringify(entry.route_coordinates), JSON.stringify(entry.provenance)]);
      if (!result.rows[0]) throw new Error("Concurrent catalog change; retry the import");
      rows.push({ id: result.rows[0].id, name: entry.name, provenance: entry.provenance });
      report.inserted.push({ id: result.rows[0].id, name: entry.name });
    }
    report.after = report.before + report.inserted.length;
    report.projectedAfter = report.after + report.pending.length;
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

function databaseTarget(env = process.env) {
  let host = env.PGHOST, port = env.PGPORT || "5432", database = env.PGDATABASE;
  if (env.DATABASE_URL) {
    try {
      const url = new URL(env.DATABASE_URL);
      if (!["postgres:", "postgresql:"].includes(url.protocol) || ["host", "port", "database", "dbname"].some((key) => url.searchParams.has(key))) throw new Error();
      host = url.hostname; port = url.port || "5432"; database = decodeURIComponent(url.pathname.slice(1));
    } catch { throw new Error("Invalid database target configuration (credentials omitted)"); }
  }
  if (!host || !database || /[\s/]/.test(host) || !/^\d+$/.test(String(port)) || Number(port) < 1 || Number(port) > 65535) {
    throw new Error("Set an explicit database host, port and database name using the existing server configuration.");
  }
  // Only non-secret connection identity; never include username, password or URL options.
  return `${host.toLowerCase()}:${Number(port)}/${database}`;
}

function importOptions(args, env = process.env) {
  const confirmation = args.filter((arg) => arg.startsWith("--confirm-target="));
  const allowed = ["--apply", "--dry-run", "--local-only", "--remote"];
  if (args.some((arg) => !allowed.includes(arg) && !arg.startsWith("--confirm-target=")) ||
      new Set(args).size !== args.length || confirmation.length > 1 ||
      (args.includes("--apply") && args.includes("--dry-run")) ||
      (args.includes("--remote") && args.includes("--local-only"))) {
    throw new Error("Usage: --dry-run | --apply [--local-only | --remote --confirm-target=HOST:PORT/DATABASE]");
  }
  const apply = args.includes("--apply"), remote = args.includes("--remote");
  if (!remote) {
    if (confirmation.length) throw new Error("Target confirmation requires --remote");
    if (apply && !args.includes("--local-only")) throw new Error("Apply requires --local-only or explicit --remote target confirmation");
    assertLocalDatabase(env);
    return { apply, remote, target: databaseTarget(env) };
  }
  if (env.NODE_ENV === "test") throw new Error("Remote import cannot use the in-memory test database");
  const target = databaseTarget(env);
  if (apply && confirmation[0]?.slice("--confirm-target=".length) !== target) {
    throw new Error("Remote apply refused: copy the exact target from --remote --dry-run into --confirm-target=HOST:PORT/DATABASE");
  }
  if (!apply && confirmation.length) throw new Error("Target confirmation is only accepted with --apply");
  return { apply, remote, target };
}

async function runCatalogCli(operation = importCatalog) {
  require("dotenv").config({ path: path.resolve(__dirname, "../.env"), quiet: true });
  const options = importOptions(process.argv.slice(2));
  const { getPool } = require("../src/db");
  const pool = await getPool();
  try {
    const client = await pool.connect();
    try {
      // Check the effective pg connection, not just the URL supplied to the command.
      const actual = databaseTarget({ PGHOST: client.connectionParameters.host, PGPORT: client.connectionParameters.port, PGDATABASE: client.connectionParameters.database });
      if (actual !== options.target) throw new Error("Effective database differs from the confirmed target; import refused.");
      await client.query("SET statement_timeout = '15s'");
      await client.query("SET lock_timeout = '5s'");
      if (!options.apply) await client.query("SET default_transaction_read_only = on");
      console.log(JSON.stringify({ target: actual, ...await operation(client, { apply: options.apply }) }, null, 2));
    }
    finally { client.release(); }
  } finally { await pool.end(); }
}

module.exports = { importCatalog, validateCatalog, normalizeName, duplicate, assertLocalDatabase, databaseTarget, importOptions, runCatalogCli };
if (require.main === module) runCatalogCli().catch((error) => {
  // PG errors may contain connection details; do not print environment or passwords.
  console.error(error.code ? `Catalog import failed (${error.code}); no partial import committed.` : error.message);
  process.exitCode = 1;
});
