// Audit of a supplemental source verified after the initial local import.
// Only appends the documented URL to this batch; never overwrites existing facts or touches RDS.
const path = require("path");
const root = path.resolve(__dirname, "../..");
require(path.join(root, "backend/node_modules/dotenv")).config({ path: path.join(root, "backend/.env"), quiet: true });
const { assertLocalDatabase } = require(path.join(root, "backend/scripts/importCatalogExpansion"));
const { trails, batch } = require(path.join(root, "backend/src/data/catalogExpansion20261017"));
async function main() {
  assertLocalDatabase();
  const pool = await require(path.join(root, "backend/src/db")).getPool();
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const t = trails.find((r) => r.provenance.catalog_key === "llao-llao-villa-tacul");
    const result = await client.query("SELECT id, provenance FROM trails WHERE name = $1 FOR UPDATE", [t.name]);
    const row = result.rows[0];
    if (!row || row.provenance.catalog_batch !== batch || row.provenance.catalog_key !== t.provenance.catalog_key) throw new Error("Batch mismatch; no changes committed");
    const additions = t.provenance.sources.filter((s) => !row.provenance.sources.some((existing) => existing.url === s.url));
    if (additions.length) {
      row.provenance.sources.push(...additions);
      await client.query("UPDATE trails SET provenance = $1 WHERE id = $2", [JSON.stringify(row.provenance), row.id]);
    }
    await client.query("COMMIT");
    console.log(JSON.stringify({ catalog_key: t.provenance.catalog_key, appended_sources: additions.length }));
  } catch (error) { await client.query("ROLLBACK"); throw error; }
  finally { client.release(); await pool.end(); }
}
main().catch(() => { console.error("Supplemental source check failed"); process.exitCode = 1; });
