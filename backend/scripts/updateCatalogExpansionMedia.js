const { createHash } = require("node:crypto");
const { batch, trails, retiredDefinitions } = require("../src/data/catalogExpansion20261017");
const { validateCatalog, runCatalogCli } = require("./importCatalogExpansion");
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === "object" && !(value instanceof Date)
  ? Object.fromEntries(Object.keys(value).sort((a, b) => a.localeCompare(b, "en")).map(key => [key, canonical(value[key])])) : value;
const digest = rows => createHash("sha256").update(JSON.stringify(canonical(rows))).digest("hex");

// Target existing batch+key, never numeric IDs or names alone. No migrations or seeds.
// The single owner-requested withdrawal is refused if any related user data exists.
async function assertUnreferenced(client, id, apply) {
  const references = (await client.query(`SELECT n.nspname AS schema_name, t.relname AS table_name,
    a.attname AS column_name, cardinality(c.conkey) AS column_count
    FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
    JOIN pg_namespace n ON n.oid=t.relnamespace
    JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=ANY(c.conkey)
    WHERE c.contype='f' AND c.confrelid='trails'::regclass`)).rows;
  const quote = name => '"' + name.replace(/"/g, '""') + '"';
  for (const ref of references) {
    if (Number(ref.column_count) !== 1) throw new Error("Withdrawal refused: composite trail reference requires manual review");
    const table = `${quote(ref.schema_name)}.${quote(ref.table_name)}`;
    if (apply) await client.query(`LOCK TABLE ${table} IN SHARE ROW EXCLUSIVE MODE`);
    const count = Number((await client.query(`SELECT count(*) AS total FROM ${table} WHERE ${quote(ref.column_name)}=$1`, [id])).rows[0].total);
    if (count) throw new Error(`Withdrawal refused: trail ${id} has related rows in ${ref.table_name}. No user data was deleted.`);
  }
}
async function updateCatalogMedia(client, { apply = false, entries = trails } = {}) {
  validateCatalog(entries);
  await client.query("BEGIN");
  try {
    if (apply) await client.query("LOCK TABLE trails IN SHARE ROW EXCLUSIVE MODE");
    const before = (await client.query("SELECT * FROM trails ORDER BY id")).rows;
    const keys = new Set(entries.map(t => t.provenance.catalog_key));
    const targeted = row => row.provenance?.catalog_batch === batch && keys.has(row.provenance.catalog_key);
    const retired = before.filter(row => row.provenance?.catalog_batch === batch && retiredDefinitions.some(d => d.key === row.provenance.catalog_key));
    for (const row of retired) {
      const definition = retiredDefinitions.find(d => d.key === row.provenance.catalog_key);
      if (row.name !== definition.name || retired.filter(r => r.provenance.catalog_key === definition.key).length !== 1) throw new Error("Withdrawal identity mismatch");
      await assertUnreferenced(client, row.id, apply);
    }
    const retiredIds = new Set(retired.map(row => row.id));
    const untouched = digest(before.filter(row => !targeted(row) && !retiredIds.has(row.id)));
    const report = { batch, mode: apply ? "apply" : "dry-run", before: before.length, updated: [], unchanged: [],
      withdrawn: retired.map(row => ({ id: row.id, name: row.name })), projectedAfter: before.length - retired.length,
      photos: entries.filter(t => t.image_url).length, maps: entries.filter(t => t.route_coordinates).length,
      navigationReady: entries.filter(t => t.provenance.mapping?.navigation_ready).length,
      pending: entries.filter(t => !t.route_coordinates).map(t => ({ name: t.name, reason: t.provenance.mapping_pending_reason })) };
    for (const entry of entries) {
      const matches = before.filter(row => targeted(row) && row.provenance.catalog_key === entry.provenance.catalog_key);
      if (matches.length !== 1 || matches[0].name !== entry.name) throw new Error(`Expected exactly one unchanged identity for ${entry.provenance.catalog_key}; transaction cancelled`);
      const row = matches[0];
      // Preserve training annotations, native facts and any unrelated metadata added by the owner.
      const provenance = { ...row.provenance, photo: entry.provenance.photo, mapping: entry.provenance.mapping,
        source_notice: entry.provenance.source_notice,
        media_revision: entry.provenance.media_revision, mapping_pending_reason: entry.provenance.mapping_pending_reason,
        missing_fields: [...new Set([...(row.provenance.missing_fields || []).filter(f => !["gps_trace", "start_coordinates", "licensed_photo", "complete_trace"].includes(f)),
          ...entry.provenance.missing_fields])].sort((a, b) => a.localeCompare(b, "en")) };
      const next = { ...row, image_url: entry.image_url, center_lat: entry.center_lat, center_lng: entry.center_lng,
        map_zoom: entry.map_zoom, route_coordinates: entry.route_coordinates, provenance };
      // center_* is PostgreSQL REAL (float32), unlike the full-precision JSON geometry.
      const comparable = value => ({ ...value, center_lat: value.center_lat == null ? null : Math.fround(value.center_lat),
        center_lng: value.center_lng == null ? null : Math.fround(value.center_lng) });
      if (digest([comparable(row)]) === digest([comparable(next)])) { report.unchanged.push(row.id); continue; }
      if (apply) {
        const result = await client.query(`UPDATE trails SET image_url=$1, center_lat=$2, center_lng=$3, map_zoom=$4,
          route_coordinates=$5, provenance=$6 WHERE id=$7 RETURNING id`,
        [next.image_url, next.center_lat, next.center_lng, next.map_zoom, JSON.stringify(next.route_coordinates), JSON.stringify(provenance), row.id]);
        if (result.rows.length !== 1) throw new Error("Concurrent catalog change");
      }
      report.updated.push({ id: row.id, name: row.name, points: entry.route_coordinates?.length || 0,
        navigationReady: entry.provenance.mapping?.navigation_ready || false });
    }
    if (apply) for (const row of retired) {
      const result = await client.query("DELETE FROM trails WHERE id=$1 RETURNING id", [row.id]);
      if (result.rows.length !== 1) throw new Error("Concurrent catalog withdrawal");
    }
    const after = (await client.query("SELECT * FROM trails ORDER BY id")).rows;
    const preservedIdentity = before.filter(row => !apply || !retiredIds.has(row.id));
    if (after.length !== preservedIdentity.length || digest(after.filter(row => !targeted(row) && !retiredIds.has(row.id))) !== untouched ||
        JSON.stringify(after.map(row => [row.id, row.name])) !== JSON.stringify(preservedIdentity.map(row => [row.id, row.name]))) throw new Error("Catalog preservation check failed");
    report.after = after.length;
    report.otherRowsPreserved = true;
    report.otherRowsSha256 = untouched;
    await client.query(apply ? "COMMIT" : "ROLLBACK");
    return report;
  } catch (error) { await client.query("ROLLBACK"); throw error; }
}
module.exports = { updateCatalogMedia, assertUnreferenced };
if (require.main === module) runCatalogCli(updateCatalogMedia).catch(error => {
  console.error(error.code ? `Catalog correction failed (${error.code}); no partial update committed.` : error.message);
  process.exitCode = 1;
});
