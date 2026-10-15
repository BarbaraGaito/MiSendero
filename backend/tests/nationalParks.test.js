const request = require("supertest");
jest.mock("../src/trailElevation", () => ({
  ...jest.requireActual("../src/trailElevation"),
  ensureTrailElevation: jest.fn().mockResolvedValue(null),
}));
const runMigrations = require("../src/migrate");
const seedDatabase = require("../src/seed");
const app = require("../src/server");
const definitions = require("../src/data/nationalParks");
const { query } = require("../src/db");

beforeAll(async () => { await runMigrations(); await seedDatabase(); });

test("only explicitly verified national-park trails are linked", async () => {
  const list = await request(app).get("/api/trails");
  const eligible = definitions.flatMap((park) => park.trails);
  expect(eligible).toHaveLength(15);
  expect(new Set(eligible).size).toBe(15);
  expect(list.body.filter((trail) => trail.national_park).map((trail) => trail.name).sort()).toEqual(eligible.sort());
  for (const trail of list.body) {
    if (!eligible.includes(trail.name)) {
      expect(trail.national_park).toBeNull();
      expect(trail.national_park_slug).toBeNull();
    } else expect(trail.national_park.slug).toBe(trail.national_park_slug);
  }
  for (const name of ["Sendero a Confluencia", "Caminata al Cerro Morado", "Laguna Esmeralda"]) {
    expect(list.body.find((trail) => trail.name === name)?.national_park).toBeNull();
  }
});

test("park endpoints include complete sourced profiles and real catalog IDs", async () => {
  const list = await request(app).get("/api/national-parks");
  expect(list.status).toBe(200);
  expect(list.body).toHaveLength(11);
  const trails = (await request(app).get("/api/trails")).body;
  for (const park of list.body) {
    const detail = await request(app).get(`/api/national-parks/${park.slug}`);
    expect(detail.body).toEqual(park);
    expect(park.checked_at).toBe("2026-10-11");
    if (park.registration.form_url) {
      expect(park.registration.form_url).toMatch(/^https:\/\/(forms.gle|docs.google.com|www.qsistemas.com.ar)\//);
      expect(park.registration.mode || "online").toBe("online");
    } else expect(["in_person", "consult"]).toContain(park.registration.mode);
    for (const section of ["registration", "rules", "access", "overnight", "fire", "contact"]) {
      expect(park[section].source_url).toMatch(/^https:\/\/(www.argentina.gob.ar|nahuelhuapi.gov.ar|quebradadelcondorito.com.ar|www.pnlanin.com.ar|www.larutanatural.gob.ar)\//);
    }
    expect(park.trails.length).toBeGreaterThan(0);
    for (const trail of park.trails) {
      expect(trails.find((item) => item.id === trail.id).national_park_slug).toBe(park.slug);
    }
  }
});

test("every national park explicitly named in the catalog now has a full profile", async () => {
  const trails = (await request(app).get("/api/trails")).body;
  const nationalTrails = trails.filter((trail) => /^Parque Nacional /i.test(trail.location));
  expect(nationalTrails).toHaveLength(15);
  for (const trail of nationalTrails) {
    expect(trail.national_park).not.toBeNull();
    const detail = await request(app).get(`/api/trails/${trail.id}`);
    expect(detail.body.national_park).toEqual(trail.national_park);
  }
});

test("presential registration and requirements for different Quijadas trails are distinct", async () => {
  const lihue = (await request(app).get("/api/national-parks/lihue-calel")).body;
  expect(lihue.registration).toMatchObject({ requirement: "always", mode: "in_person", form_url: null });
  const quijadas = (await request(app).get("/api/national-parks/sierra-de-las-quijadas")).body;
  const requirements = quijadas.registration_by_trail;
  expect(requirements["Sendero Guanacos - Sierra de las Quijadas"]).toMatchObject({ requirement: "always", mode: "in_person", form_url: null });
  expect(requirements["Miradores de Sierra de las Quijadas"].requirement).toBe("consult");
  for (const name of Object.keys(requirements)) expect(quijadas.trails.some((trail) => trail.name === name)).toBe(true);
  const palmar = (await request(app).get("/api/national-parks/el-palmar")).body;
  expect(palmar.contact.phone).toBeNull();
  expect(palmar.contact.email).toBe("elpalmar@apn.gob.ar");
});

test("weather estimates and community reports are never official closure data", async () => {
  const list = await request(app).get("/api/national-parks");
  for (const park of list.body) {
    expect(park.live_status).toEqual({ closures: "not_integrated", weather_alerts: "not_integrated", weather_url: "https://www.smn.gob.ar/alertas" });
    expect(park).not.toHaveProperty("is_open");
    expect(park).not.toHaveProperty("registration_completed");
  }
});

test("seasonal registration and northern fire restrictions are not generalized", async () => {
  const park = (await request(app).get("/api/national-parks/los-glaciares")).body;
  expect(park.registration.requirement).toBe("seasonal");
  expect(park.registration.required_months).toEqual([5, 6, 7, 8, 9]);
  expect(park.fire.text).toMatch(/^Zona Norte:/);
});

test("unknown and provincial parks have no institutional profile", async () => {
  for (const slug of ["aconcagua", "ischigualasto", "missing", "undefined"]) {
    expect((await request(app).get(`/api/national-parks/${slug}`)).status).toBe(404);
  }
});

test("reseeding is idempotent without replacing catalog IDs", async () => {
  const before = await query("SELECT id, name, national_park_slug FROM trails ORDER BY id");
  await seedDatabase();
  expect((await query("SELECT id, name, national_park_slug FROM trails ORDER BY id")).rows).toEqual(before.rows);
  expect((await query("SELECT * FROM national_parks")).rows).toHaveLength(11);
});
