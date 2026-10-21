// Fetches real DEM samples for complete, reviewed repository traces. No database access.
const fs = require("node:fs");
const path = require("node:path");
const { fetchElevation, geometryHash } = require("../src/trailElevation");
const { trails } = require("../src/data/catalogExpansion20261017");
const output = path.resolve(__dirname, "../src/data/recommendationElevation20261021.json");

function eligibleTrails(entries = trails) {
  return entries.filter(t => t.provenance?.mapping?.navigation_ready === true && t.route_coordinates?.length > 1);
}
async function main() {
  if (process.argv.length !== 2) throw new Error("No arguments are accepted; output and public provider are fixed.");
  // No .env/credentials are loaded. Pin the public data provider for this export.
  process.env.ELEVATION_API_URL = "https://api.open-meteo.com/v1/elevation";
  delete process.env.ELEVATION_API_KEY;
  const previous = fs.existsSync(output) ? JSON.parse(fs.readFileSync(output, "utf8")) : { schemaVersion: 1, entries: {} };
  const result = { schemaVersion: 1, entries: {} };
  for (const trail of eligibleTrails()) {
    const key = trail.provenance.catalog_key;
    const saved = previous.entries[key];
    const elevation = saved?.elevation?.geometry_hash === geometryHash(trail)
      ? saved.elevation : await fetchElevation(trail, { timeoutMs: 20000 });
    result.entries[key] = { name: trail.name, geometrySource: trail.provenance.mapping.source_url, basis: "dem_estimate", elevation };
    // A failed fetch preserves all already fetched, real profiles for a retry.
    fs.writeFileSync(output, JSON.stringify(result, null, 2) + "\n");
    console.log(JSON.stringify({ key, ascentM: elevation.ascent_m, samples: elevation.points.length, basis: "dem_estimate" }));
  }
}
module.exports = { eligibleTrails };
if (require.main === module) main().catch(e => { console.error(`Elevation export failed: ${e.cause?.code || e.message}`); process.exitCode = 1; });
