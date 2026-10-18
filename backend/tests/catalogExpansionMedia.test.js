const { trails, batch, retiredDefinitions } = require("../src/data/catalogExpansion20261017");
const routes = require("../src/data/catalogExpansionRoutes20261017.json");
const { updateCatalogMedia, assertUnreferenced } = require("../scripts/updateCatalogExpansionMedia");
const { importCatalog } = require("../scripts/importCatalogExpansion");
const { getPool, query } = require("../src/db");
const { sampleRoute } = require("../src/trailElevation");
const migrate = require("../src/migrate");
const seed = require("../src/seed");

test("each of the 19 retained photos has a distinct source, credit, licence and context", () => {
  expect(new Set(trails.map(t => t.image_url)).size).toBe(19);
  for (const t of trails) {
    const photo = t.provenance.photo;
    expect(photo.url).toBe(t.image_url);
    expect(photo.author).toBeTruthy();
    expect(photo.license_url).toMatch(/^https:\/\//);
    expect(photo.context).toBeTruthy();
    expect(photo.sha256).toMatch(/^[a-f0-9]{64}$/);
    expect(t.provenance.missing_fields).not.toContain("licensed_photo");
  }
});

test("keeps 19 sourced maps and withdraws Piedra Movediza from future imports", () => {
  expect(Object.keys(routes)).toHaveLength(19);
  const pending = trails.filter(t => !t.route_coordinates);
  expect(pending).toEqual([]);
  expect(retiredDefinitions.map(t => t.key)).toEqual(["lihue-piedra-movediza"]);
  for (const t of trails.filter(t => t.route_coordinates)) {
    const r = routes[t.provenance.catalog_key];
    expect(sampleRoute(r.points).samples.at(-1).distance_m / 1000).toBeCloseTo(r.distance_km, 2);
    expect(r.points.every(([lat, lon]) => lat > -56 && lat < -21 && lon > -74 && lon < -53)).toBe(true);
    expect(r.source_sha256).toMatch(/^[a-f0-9]{64}$/);
    if (r.scope === "partial_reference") expect(r.navigation_ready).toBe(false);
  }
});

test("separates itinerary variants and excludes the closed Laguna Escondida path", () => {
  expect(routes["moreno-belgrano-chico"].source_sha256).not.toBe(routes["moreno-belgrano-grande"].source_sha256);
  expect(routes["alerces-laguna-escondida"].ways.map(w => w.id)).not.toContain(1222371563);
  expect(routes["llao-llao-villa-tacul"].points[0]).toEqual([-41.0411141, -71.5615845]);
  const rosales = routes["lanin-rosales-san-martin"];
  expect(rosales.ways.map(w => w.id)).not.toContain(55685740); // disconnected member omitted, never bridged
  expect(rosales.navigation_ready).toBe(false);
  expect(routes["alerces-cerro-cocinero"].note).toContain("cierre por incendio");
});

describe("targeted media correction", () => {
  let connection, client;
  beforeAll(async () => {
    await migrate(); await seed();
    connection = await (await getPool()).connect();
    // pg-mem cannot parse table locks; the real local PostgreSQL check exercises that lock.
    client = { query: (sql, params) => {
      if (sql.startsWith("LOCK TABLE")) return Promise.resolve({ rows: [] });
      if (sql.includes("FROM pg_constraint")) return Promise.resolve({ rows: ["activities", "trail_reports", "emergency_alerts", "trip_plans"].map(table_name => ({ schema_name: "public", table_name, column_name: "trail_id", column_count: 1 })) });
      return connection.query(sql, params);
    } };
    await importCatalog(client, { apply: true });
    const retired = retiredDefinitions[0];
    await connection.query("INSERT INTO trails (name,location,difficulty,provenance) VALUES ($1,$2,$3,$4)",
      [retired.name, retired.area, "Media", JSON.stringify({ catalog_batch: batch, catalog_key: retired.key })]);
    // Reproduce the original 20 incomplete rows while preserving additional owner metadata.
    for (const t of trails) {
      const p = structuredClone(t.provenance);
      delete p.photo; delete p.mapping; delete p.media_revision; delete p.mapping_pending_reason;
      p.owner_note = "preserve this";
      p.missing_fields = ["gps_trace", "start_coordinates", "licensed_photo", "accumulated_ascent"];
      await connection.query("UPDATE trails SET image_url=NULL, center_lat=NULL, center_lng=NULL, map_zoom=NULL, route_coordinates=NULL, provenance=$1 WHERE name=$2", [JSON.stringify(p), t.name]);
    }
  });
  afterAll(() => connection.release());
  test("preview does not write; application preserves all IDs, original 32 rows and native facts; repeat is idempotent", async () => {
    const before = (await query("SELECT * FROM trails ORDER BY id")).rows;
    const preview = await updateCatalogMedia(client);
    expect(preview.updated).toHaveLength(19);
    expect((await query("SELECT * FROM trails ORDER BY id")).rows).toEqual(before);
    const report = await updateCatalogMedia(client, { apply: true });
    expect(report).toMatchObject({ before: 52, after: 51, photos: 19, maps: 19, otherRowsPreserved: true });
    expect(report.withdrawn.map(t => t.name)).toEqual([retiredDefinitions[0].name]);
    const after = (await query("SELECT * FROM trails ORDER BY id")).rows;
    expect(after.filter(r => r.provenance?.catalog_batch !== batch)).toEqual(before.filter(r => r.provenance?.catalog_batch !== batch));
    expect(after.map(r => [r.id, r.name])).toEqual(before.filter(r => r.provenance?.catalog_key !== retiredDefinitions[0].key).map(r => [r.id, r.name]));
    for (const row of after.filter(r => r.provenance?.catalog_batch === batch)) {
      expect(row.provenance.owner_note).toBe("preserve this");
      expect(row.provenance.native).toEqual(before.find(r => r.id === row.id).provenance.native);
    }
    expect((await updateCatalogMedia(client, { apply: true })).unchanged).toHaveLength(19);
  });
  test("missing batch identity cancels instead of creating or replacing another trail", async () => {
    const entry = structuredClone(trails[0]); entry.provenance.catalog_key = "missing";
    await expect(updateCatalogMedia(client, { apply: true, entries: [entry] })).rejects.toThrow("Expected exactly one");
    expect((await query("SELECT id FROM trails")).rows).toHaveLength(51);
  });
  test("the API returns the PostgreSQL geometry as the JSON text expected by Expo", async () => {
    const request = require("supertest");
    const app = require("../src/server");
    const response = await request(app).get("/api/trails").expect(200);
    expect(response.body).toHaveLength(51);
    const expansion = response.body.filter(row => row.provenance?.catalog_batch === batch);
    expect(expansion).toHaveLength(19);
    for (const row of expansion) {
      const expected = trails.find(t => t.provenance.catalog_key === row.provenance.catalog_key);
      expect(row.image_url).toBe(expected.image_url);
      expect(JSON.parse(row.route_coordinates)).toEqual(expected.route_coordinates);
    }
  });
  test("SQL failures roll back the entire correction", async () => {
    const row = { ...trails[0], id: 50, image_url: null };
    const client = { query: jest.fn(async sql => {
      if (sql.startsWith("SELECT")) return { rows: [row] };
      if (sql.startsWith("UPDATE")) throw new Error("write failed");
      return { rows: [] };
    }) };
    await expect(updateCatalogMedia(client, { apply: true, entries: [trails[0]] })).rejects.toThrow("write failed");
    expect(client.query).toHaveBeenLastCalledWith("ROLLBACK");
  });
});

test("withdrawal refuses cascading deletion or loss of related user history", async () => {
  const client = { query: jest.fn(async sql => sql.includes("pg_constraint")
    ? { rows: [{ schema_name: "public", table_name: "trail_reports", column_name: "trail_id", column_count: 1 }] }
    : { rows: [{ total: "2" }] }) };
  await expect(assertUnreferenced(client, 313, true)).rejects.toThrow("No user data was deleted");
  expect(client.query.mock.calls.some(([sql]) => sql.startsWith("DELETE"))).toBe(false);
});
