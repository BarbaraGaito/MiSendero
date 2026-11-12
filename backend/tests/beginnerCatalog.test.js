const request = require("supertest");
const jwt = require("jsonwebtoken");
const { recommendTrail } = require("../dist/ai/assistant");
const { candidateDurationFits, verifiedCatalog } = require("../dist/ai/catalog");
const { getPool, query } = require("../src/db");
const runMigrations = require("../src/migrate");
const seedDatabase = require("../src/seed");
const { importCatalog } = require("../scripts/importCatalogExpansion");
const { importBeginnerCatalog, planBeginnerCatalog } = require("../scripts/importBeginnerCatalog");
const { trails } = require("../src/data/beginnerCatalog20261112");
const app = require("../src/server");

const prefs = (destination, duration) => ({ destination, duration, difficulty: "cualquiera",
  experience: "principiante", trailTypes: ["cualquiera"] });
const withIds = () => trails.map((trail, index) => ({ ...trail, id: index + 1 }));

test("matches confirmed round trips and distinguishes a documented one-way trip", async () => {
  const rows = withIds();
  expect(verifiedCatalog(rows)).toHaveLength(trails.length);
  const fuego = await recommendTrail(prefs("Parque Nacional Tierra del Fuego", "menos-1"), rows);
  expect(fuego.recommendation).toMatchObject({ durationMinutes: 30, routeType: "out_and_back", durationScopeVerified: true });
  expect(fuego.recommendation.preferenceAdjustments).toBeUndefined();
  const iguazu = await recommendTrail(prefs("Parque Nacional Iguazú", "menos-1"), rows);
  expect(iguazu.recommendation).toMatchObject({ durationMinutes: 15, routeType: "point_to_point" });
  expect(iguazu.recommendation.explanation).toContain("coordinar el regreso");
});

test("unknown and unspecified return times cannot satisfy an explicit duration filter", async () => {
  const rows = withIds();
  const [cascada] = verifiedCatalog(rows.filter(t => t.provenance.catalog_key === "leoncito-cascada-rincon"));
  expect(cascada).toMatchObject({ duration: "A confirmar", durationMinutes: null, durationScopeVerified: false });
  expect(candidateDurationFits(cascada, "cualquiera")).toBe(true);
  const rincon = await recommendTrail(prefs("Esquel", "menos-1"), rows);
  expect(rincon.recommendation).toMatchObject({ durationMinutes: 42, durationScopeVerified: true, durationIsEstimated: true });
  expect(rincon.recommendation.dataWarnings).toEqual([expect.stringContaining("21 minutos solo de ida")]);
  const funicular = await recommendTrail(prefs("Sierra de San Javier", "1-2"), rows);
  expect(funicular.recommendation).toMatchObject({ durationMinutes: 75, durationScopeVerified: false, preferenceAdjustments: [expect.stringContaining("no está confirmado")] });
  const leoncito = await recommendTrail(prefs("Parque Nacional El Leoncito", "menos-1"), rows);
  expect(leoncito.recommendation).toMatchObject({ durationMinutes: null, preferenceAdjustments: [expect.stringContaining("No hay un tiempo total publicado")] });
  expect(leoncito.recommendation.exceedsExperience).toBeUndefined();
});

test("the catalog plan confirms only matching legacy durations and preserves different provenance", () => {
  const legacy = require("../src/data/legacyTrails").map((row, index) => ({ ...row, id: index + 1, provenance: null }));
  const original = planBeginnerCatalog(legacy);
  expect(original.durationReviews).toHaveLength(10);
  const reviewed = verifiedCatalog(original.durationReviews.map(change => change.after));
  expect(reviewed.filter(candidate => candidate.durationScopeVerified).map(candidate => candidate.name))
    .toEqual(["Lahuan Solitario - Puerto Chucao", "Caminata al Cerro Morado"]);
  expect(planBeginnerCatalog(legacy.map(row => row.name === "Lahuan Solitario - Puerto Chucao"
    ? { ...row, provenance: { otherSource: true } } : { ...row, distance_km: row.distance_km + 1 })).durationReviews).toEqual([]);
});

test("an out-of-profile alternative is marked as a reference, not a fit", async () => {
  const [row] = withIds();
  const result = await recommendTrail(prefs("Parque Nacional Tierra del Fuego", "menos-1"), [{ ...row, difficulty: "Alta" }]);
  expect(result).toMatchObject({ message: "No hay senderos de tu nivel en este destino.", recommendation: { exceedsExperience: true } });
  expect(result.recommendation.preferenceAdjustments).toEqual([expect.stringContaining("supera ese nivel")]);
});

test("previews and applies the catalog changes idempotently while preserving existing rows and GPS data", async () => {
  await runMigrations();
  await seedDatabase();
  const connection = await (await getPool()).connect();
  // pg-mem does not implement table locks; SQL writes and reads use the real schema.
  const client = { query: (sql, params) => sql.startsWith("LOCK TABLE") ? Promise.resolve({ rows: [] }) : connection.query(sql, params) };
  try {
    await importCatalog(client, { apply: true });
    await query("UPDATE trails SET provenance = NULL WHERE name = $1", ["Lahuan Solitario - Puerto Chucao"]);
    const snapshot = async () => (await query("SELECT * FROM trails ORDER BY id")).rows;
    const before = await snapshot();
    const preview = await importBeginnerCatalog(client);
    expect(preview).toMatchObject({ before: 51, projectedAfter: 51 + trails.length, pending: expect.arrayContaining(["Sendero Verde - Iguazú"]),
      durationReviews: expect.arrayContaining([{ name: "Cerro Leoncito - El Leoncito", before: "3 h", after: "3 a 4 h", basis: "official_round_trip" },
        { name: "Lahuan Solitario - Puerto Chucao", before: "1 h 30 min", after: "1 h 30 min", basis: "official_round_trip" }]) });
    expect(await snapshot()).toEqual(before);
    const applied = await importBeginnerCatalog(client, { apply: true });
    expect(applied.inserted).toHaveLength(trails.length);
    const after = await snapshot();
    const previous = before.find(row => row.provenance?.catalog_key === "leoncito-cerro");
    const updated = after.find(row => row.id === previous.id);
    expect(updated).toEqual({ ...previous, duration: "3 a 4 h", provenance: expect.objectContaining({ duration_minutes_max: 240 }) });
    const reviewed = verifiedCatalog([updated])[0];
    expect(candidateDurationFits(reviewed, "2-4")).toBe(true);
    expect(candidateDurationFits(reviewed, "4-6")).toBe(false);
    const lahuan = before.find(row => row.name === "Lahuan Solitario - Puerto Chucao");
    expect(after.find(row => row.id === lahuan.id)).toEqual({ ...lahuan, provenance: expect.objectContaining({ duration_basis: "official_round_trip" }) });
    const unchanged = r => ![previous.id, lahuan.id].includes(r.id);
    expect(after.slice(0, before.length).filter(unchanged)).toEqual(before.filter(unchanged));
    expect(after.find(r => r.name === "Sendero Verde - Iguazú")).toMatchObject({ route_coordinates: null, image_url: null, national_park_slug: "iguazu" });
    const repeated = await importBeginnerCatalog(client, { apply: true });
    expect(repeated).toMatchObject({ inserted: [], durationReviews: [] });
    expect(await snapshot()).toEqual(after);
    const { rows: [user] } = await query("INSERT INTO users (name,email,password_hash) VALUES ($1,$2,$3) RETURNING id",
      ["Beginner catalog test", "beginner-catalog@test.app", "unused"]);
    const token = jwt.sign({ userId: user.id }, process.env.JWT_SECRET);
    const call = () => request(app).post("/api/ai/recommend-trail").set("Authorization", `Bearer ${token}`)
      .send(prefs("Parque Nacional El Leoncito", "menos-1"));
    const older = await call();
    expect(older.status).toBe(200);
    expect(older.body.recommendation).toMatchObject({ durationMinutes: 240, exceedsExperience: true });
    const newer = await call().set("X-MiSendero-Unpublished-Duration", "1");
    expect(newer.status).toBe(200);
    expect(newer.body.recommendation).toMatchObject({ name: "Cascada El Rincón - El Leoncito", durationMinutes: null, durationScopeVerified: false });
  } finally { connection.release(); }
});
