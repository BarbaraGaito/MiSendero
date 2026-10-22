require("dotenv").config();
const fs = require("node:fs");
const { importEnvironmentalBatch } = require("../src/environmentalImport");
const { getPool } = require("../src/db");
async function main() {
  const args = process.argv.slice(2);
  const index = args.indexOf("--file");
  if (index < 0 || !args[index + 1]) throw new Error("Usage: node scripts/importEnvironmentalSnapshots.js --file snapshot.json [--apply --local-only]");
  const apply = args.includes("--apply");
  if (apply) {
    const host = process.env.DATABASE_URL ? new URL(process.env.DATABASE_URL).hostname : process.env.PGHOST;
    if (!args.includes("--local-only") || process.env.NODE_ENV === "production" || !["localhost", "127.0.0.1", "[::1]", "::1"].includes(host)) {
      throw new Error("This research import only applies to an explicitly configured local database; production publication is separate.");
    }
  }
  const path = args[index + 1];
  if (fs.statSync(path).size > 1024 * 1024) throw new Error("Snapshot file exceeds 1 MB");
  console.log(JSON.stringify(await importEnvironmentalBatch(JSON.parse(fs.readFileSync(path, "utf8")), apply)));
}
main().catch((error) => { console.error(error.message); process.exitCode = 1; })
  .finally(async () => { try { await (await getPool()).end(); } catch { /* No configured database. */ } });
