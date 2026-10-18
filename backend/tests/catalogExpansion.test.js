const { trails, definitions, batch } = require("../src/data/catalogExpansion20261017");
const { importCatalog, validateCatalog, assertLocalDatabase } = require("../scripts/importCatalogExpansion");
const { featureRecord } = require("../scripts/exportCatalogFeatures");
const { verifiedCatalog, compatibleCandidates, durationMinutes } = require("../dist/ai/catalog");
const runMigrations = require("../src/migrate");
const seedDatabase = require("../src/seed");
const { getPool, query } = require("../src/db");

const withIds = () => trails.map((t, i) => ({ ...t, id: i + 100 }));
const prefs = (destination, duration = "cualquiera") => ({ destination, duration, trailTypes: ["cualquiera"], difficulty: "cualquiera", experience: "avanzado" });

describe("documented catalog expansion 2026-10-17", () => {
  test("contains 20 real catalog feature records across 12 provinces and all three grades", () => {
    expect(validateCatalog()).toHaveLength(20);
    expect(new Set(definitions.map((t) => t.province)).size).toBe(12);
    expect(new Set(trails.map((t) => t.difficulty))).toEqual(new Set(["Baja", "Media", "Alta"]));
    expect(new Set(trails.map((t) => t.provenance.catalog_key)).size).toBe(20);
    expect(Math.min(...trails.map((t) => t.provenance.duration_minutes_min))).toBe(30);
    expect(Math.max(...trails.map((t) => t.provenance.duration_minutes_max))).toBe(540);
  });

  test.each(trails)("$name preserves audit and missing-data information", (t) => {
    expect(t.provenance.training).toEqual({ record_type: "verified_catalog_features", relevance_label: null, synthetic: false });
    expect(t.provenance.sources[0].url).toMatch(/^https:\/\//);
    expect(t.provenance.native.section).toBeTruthy();
    expect(t.center_lat).toBeNull();
    expect(t.center_lng).toBeNull();
    expect(t.route_coordinates).toBeNull();
    expect(t.image_url).toBeNull();
    const exported = featureRecord({ ...t, id: 1 });
    expect(exported.accumulated_ascent_m).toBeNull();
    expect(exported.relevance_label).toBeNull();
    expect(exported.provenance).toEqual(t.provenance);
  });

  test("retains one-way facts and explicitly marks the two derived round-trip times", () => {
    const derived = trails.filter((t) => t.provenance.duration_is_derived);
    expect(derived).toHaveLength(2);
    for (const t of derived) {
      expect(t.provenance.duration_minutes_max).toBe(t.provenance.native.duration_minutes_max * 2);
      expect(t.distance_km).toBeCloseTo(t.provenance.native.distance_km * 2, 3);
      expect(t.provenance.precautions).toContain("no es un tiempo oficial de ida y vuelta");
    }
    const pampa = trails.find((t) => t.provenance.catalog_key === "fuego-pampa-alta");
    expect(pampa.distance_km).toBe(4.7);
    expect(pampa.provenance.duration_basis).toBe("official_one_way");
    expect(pampa.provenance.native.vertical_reference_m).toBe(252);
    expect(pampa.provenance.missing_fields).toContain("accumulated_ascent");
  });

  test("all 20 can be read by the recommender without fabricating image or ascent", () => {
    const candidates = verifiedCatalog(withIds());
    expect(candidates).toHaveLength(20);
    candidates.forEach((c) => { expect(c.imageUrl).toBeNull(); expect(c.ascentM).toBeNull(); });
    expect(compatibleCandidates(candidates, prefs("Bariloche"))).toHaveLength(1);
    expect(compatibleCandidates(candidates, prefs("Corrientes"))).toHaveLength(2);
    expect(compatibleCandidates(candidates, prefs("Neuquén", "mas-6"))).toHaveLength(1);
  });

  test("keeps official duration ranges and requires the entire interval to fit", () => {
    const candidates = verifiedCatalog(withIds());
    expect(durationMinutes("3-4 h")).toBe(240);
    expect(durationMinutes("6-3 h")).toBeNull();
    expect(compatibleCandidates(candidates, prefs("Santa Cruz", "2-4")).map((c) => c.name)).toEqual(["Península Belgrano - Circuito Chico"]);
    expect(compatibleCandidates(candidates, prefs("Santa Cruz", "4-6")).map((c) => c.name)).toEqual(["Península Belgrano - Circuito Grande"]);
  });

  test("refuses incomplete metadata, untrusted sources and duplicates before SQL", () => {
    const modified = (change) => { const t = structuredClone(trails[0]); change(t); return [t]; };
    expect(() => validateCatalog(modified((t) => t.distance_km = null))).toThrow();
    expect(() => validateCatalog(modified((t) => t.provenance.sources[0].url = "https://example.com/fake"))).toThrow();
    expect(() => validateCatalog(modified((t) => t.provenance.duration_minutes_min = 10000))).toThrow();
    expect(() => validateCatalog([trails[0], trails[0]])).toThrow();
  });

  test.each(["localhost", "127.0.0.1", "[::1]"])("allows explicitly local database %s", (host) => {
    expect(() => assertLocalDatabase({ DATABASE_URL: `postgresql://user:secret@${host}:5432/local` })).not.toThrow();
  });
  test("rejects RDS, remote hosts, omitted hosts and socket paths", () => {
    for (const env of [{ DATABASE_URL: "postgresql://u:private@db.us-east-2.rds.amazonaws.com/misendero" }, { PGHOST: "db" }, {}, { PGHOST: "/tmp" }]) {
      expect(() => assertLocalDatabase(env)).toThrow("Local-only");
    }
  });

  test("imports 20 into the real schema, preserves original 32, and repeats without duplicates", async () => {
    await runMigrations();
    await seedDatabase();
    const before = (await query("SELECT * FROM trails ORDER BY id")).rows;
    expect(before).toHaveLength(32);
    const pool = await getPool();
    const connection = await pool.connect();
    // pg-mem has no table lock implementation; real PostgreSQL uses this lock in the CLI.
    const client = { query: (sql, params) => sql === "LOCK TABLE trails IN SHARE ROW EXCLUSIVE MODE" ? Promise.resolve({ rows: [] }) : connection.query(sql, params) };
    try {
      const preview = await importCatalog(client);
      expect(preview.pending).toHaveLength(20);
      expect((await query("SELECT id FROM trails")).rows).toHaveLength(32);
      const applied = await importCatalog(client, { apply: true });
      expect(applied.inserted).toHaveLength(20);
      expect(applied.after).toBe(52);
      const repeated = await importCatalog(client, { apply: true });
      expect(repeated.inserted).toHaveLength(0);
      expect(repeated.skipped).toHaveLength(20);
      const after = (await query("SELECT * FROM trails ORDER BY id")).rows;
      expect(after).toHaveLength(52);
      expect(after.slice(0, 32)).toEqual(before);
      expect(after.slice(32).every((t) => t.provenance.catalog_batch === batch)).toBe(true);
    } finally { connection.release(); }
  });

  test("recognizes normalized aliases without overwriting a previously entered trail", async () => {
    const client = { query: jest.fn(async (sql) => sql.startsWith("SELECT") ? { rows: [{ id: 900, name: "SENDERO PEDESTRE CHE ROGA", provenance: null }] } : { rows: [] }) };
    const report = await importCatalog(client, { apply: true, entries: [trails[0]] });
    expect(report.skipped[0].existingId).toBe(900);
    expect(client.query.mock.calls.some(([sql]) => sql.includes("INSERT"))).toBe(false);
  });

  test("rolls back any SQL failure instead of committing a partial batch", async () => {
    const client = { query: jest.fn(async (sql) => {
      if (sql.startsWith("SELECT")) return { rows: [] };
      if (sql.startsWith("INSERT")) throw new Error("write failed");
      return { rows: [] };
    }) };
    await expect(importCatalog(client, { apply: true })).rejects.toThrow("write failed");
    expect(client.query).toHaveBeenLastCalledWith("ROLLBACK");
    expect(client.query.mock.calls.some(([sql]) => sql === "COMMIT")).toBe(false);
  });
});
