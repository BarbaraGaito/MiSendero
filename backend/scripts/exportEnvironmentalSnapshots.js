const fs = require("node:fs");
const path = require("node:path");
const { buildEnvironmentalBatches } = require("../src/environmentalBatch");
const destination = path.resolve(__dirname, "../../training/data/environmental/private");
const run = JSON.parse(fs.readFileSync(path.join(destination, "station-forecasts.json"), "utf8"));
const firePath = path.join(destination, "fire-forecasts.json");
if (fs.existsSync(firePath)) run.forecasts.push(...JSON.parse(fs.readFileSync(firePath, "utf8")).forecasts);
const batches = buildEnvironmentalBatches(run);
// Remove obsolete prepared route files only inside this fixed local output
// directory. These are derived forecasts; original observations are elsewhere.
for (const filename of fs.readdirSync(destination)) {
  if (/^route-[1-9]\d*-snapshots\.json$/.test(filename)) fs.unlinkSync(path.join(destination, filename));
}
for (const batch of batches) fs.writeFileSync(path.join(destination, `route-${batch.trail_id}-snapshots.json`), `${JSON.stringify(batch, null, 2)}\n`);
console.log(`Prepared ${batches.length} route batches with independently reviewed associations; no database writes.`);
