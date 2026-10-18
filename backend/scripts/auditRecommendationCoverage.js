// Functional coverage of the existing LOCAL catalog, not training labels or ranking-accuracy metrics.
const fs = require("node:fs");
const path = require("node:path");
const { verifiedCatalog, compatibleCandidates, destinationMatches } = require("../dist/ai/catalog");
const { destinationIsSafe } = require("../dist/ai/assistant");
async function main() {
  require("dotenv").config({ path: path.resolve(__dirname, "../.env"), quiet: true });
  require("./importCatalogExpansion").assertLocalDatabase();
  const pool = await require("../src/db").getPool();
  try {
    const rows = (await pool.query("SELECT * FROM trails ORDER BY id")).rows;
    const catalog = verifiedCatalog(rows);
    const destinations = [...new Set(catalog.map(c => c.location))].filter(d => d.length <= 120 && destinationIsSafe(d));
    let cases = 0, empty = 0, outsideDestination = 0;
    for (const destination of destinations)
      for (const type of ["naturaleza", "montaña", "cascadas", "lagos", "bosques", "miradores", "cualquiera"])
        for (const duration of ["menos-1", "1-2", "2-4", "4-6", "mas-6", "cualquiera"])
          for (const difficulty of ["facil", "moderada", "dificil", "cualquiera"])
            for (const experience of ["principiante", "intermedio", "avanzado"]) {
              const candidates = compatibleCandidates(catalog, { destination, trailTypes: [type], duration, difficulty, experience });
              cases++;
              if (!candidates.length) empty++;
              if (candidates.some(c => !destinationMatches(c, destination))) outsideDestination++;
            }
    const report = { purpose: "functional coverage only; generated survey cases are not training data or real accuracy evidence",
      databaseWrites: 0, catalogRecords: rows.length, eligibleRecords: catalog.length,
      catalogOnlyRecords: catalog.filter(c => c.catalogVerification === "catalog_only").length,
      destinations: destinations.length, surveyCombinationsPerDestination: 504, cases, empty, outsideDestination };
    const output = path.resolve(__dirname, "../../docs/trail-ranking-2026-10-17/policy-v4-coverage.json");
    fs.writeFileSync(output, JSON.stringify(report, null, 2) + "\n");
    console.log(JSON.stringify(report, null, 2));
    if (empty || outsideDestination) process.exitCode = 1;
  } finally { await pool.end(); }
}
if (require.main === module) main().catch(error => { console.error(error.code || error.message); process.exitCode = 1; });
