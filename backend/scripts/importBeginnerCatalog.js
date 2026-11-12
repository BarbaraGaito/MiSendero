const { batch, trails, reviewCerroLeoncito } = require("../src/data/beginnerCatalog20261112");
const { reviewLegacyDuration } = require("../src/data/catalogDurationReviews20261112");
const { duplicate, runCatalogCli } = require("./catalogImportRuntime");

function planBeginnerCatalog(rows) {
  const durationReviews = rows.map(row => ({ before: row, after: reviewLegacyDuration(reviewCerroLeoncito(row)) }))
    .filter(({ before, after }) => before !== after);
  const existingRows = rows.slice();
  const pending = [];
  const skipped = [];
  for (const trail of trails) {
    const existing = duplicate(trail, existingRows);
    if (existing) { skipped.push({ name: trail.name, existingId: existing.id ?? null }); continue; }
    pending.push(trail);
    existingRows.push(trail);
  }
  return { durationReviews, pending, skipped };
}

// Only guarded duration/source reviews touch earlier rows; IDs and media remain untouched.
async function importBeginnerCatalog(client, { apply = false } = {}) {
  const report = { batch, mode: apply ? "apply" : "dry-run", before: 0, projectedAfter: 0,
    pending: [], inserted: [], skipped: [], durationReviews: [] };
  await client.query("BEGIN");
  try {
    if (apply) await client.query("LOCK TABLE trails IN SHARE ROW EXCLUSIVE MODE");
    const { rows } = await client.query("SELECT id, name, location, difficulty, duration, distance_km, provenance FROM trails ORDER BY id");
    const { rows: parks } = await client.query("SELECT slug FROM national_parks");
    const knownParks = new Set(parks.map(park => park.slug));
    report.before = rows.length;
    const plan = planBeginnerCatalog(rows);
    report.skipped = plan.skipped;
    for (const { before: row, after: reviewed } of plan.durationReviews) {
      if (apply) {
        await client.query("UPDATE trails SET duration = $1, provenance = $2::jsonb WHERE id = $3",
          [reviewed.duration, JSON.stringify(reviewed.provenance), row.id]);
      }
      report.durationReviews.push({ name: row.name, before: row.duration, after: reviewed.duration, basis: reviewed.provenance.duration_basis });
    }
    for (const trail of plan.pending) {
      if (!apply) { report.pending.push(trail.name); continue; }
      const { rows: [inserted] } = await client.query(`INSERT INTO trails
        (name, location, difficulty, duration, distance_km, description, provenance, national_park_slug)
        VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8) ON CONFLICT (name) DO NOTHING RETURNING id`,
      [trail.name, trail.location, trail.difficulty, trail.duration, trail.distance_km, trail.description,
        JSON.stringify(trail.provenance), knownParks.has(trail.parkSlug) ? trail.parkSlug : null]);
      if (!inserted) throw new Error("Concurrent catalog change; retry the import");
      report.inserted.push({ id: inserted.id, name: trail.name });
    }
    report.projectedAfter = report.before + report.inserted.length + report.pending.length;
    await client.query(apply ? "COMMIT" : "ROLLBACK");
    return report;
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  }
}

module.exports = { importBeginnerCatalog, planBeginnerCatalog };
if (require.main === module) runCatalogCli(importBeginnerCatalog, { backendRoot: process.env.MISENDERO_CATALOG_BACKEND_ROOT || undefined }).catch(error => {
  console.error(error.code ? `Catalog import failed (${error.code}); no partial import committed.` : error.message);
  process.exitCode = 1;
});
