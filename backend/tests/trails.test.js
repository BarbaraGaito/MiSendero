const request = require("supertest");
const runMigrations = require("../src/migrate");
const seedDatabase = require("../src/seed");
const app = require("../src/server");

let adminToken;
let userToken;

beforeAll(async () => {
  await runMigrations();
  await seedDatabase();

  const admin = await request(app).post("/api/auth/register").send({
    name: "Admin Uno",
    email: "admin@misendero.app",
    password: "correcta123",
    accepted_terms_version: "2026-08-13",
  });
  adminToken = admin.body.token;

  const user = await request(app).post("/api/auth/register").send({
    name: "Usuaria Dos",
    email: "usuaria@misendero.app",
    password: "correcta123",
    accepted_terms_version: "2026-08-13",
  });
  userToken = user.body.token;
});

describe("trails", () => {
  test("lists seeded trails", async () => {
    const response = await request(app).get("/api/trails");

    expect(response.status).toBe(200);
    expect(response.body.length).toBeGreaterThan(0);
    expect(response.body[0]).toHaveProperty("route_coordinates");
  });

  test("returns a single trail by id", async () => {
    const list = await request(app).get("/api/trails");
    const [first] = list.body;

    const response = await request(app).get(`/api/trails/${first.id}`);

    expect(response.status).toBe(200);
    expect(response.body.name).toBe(first.name);
  });

  test("404s for a missing trail", async () => {
    const response = await request(app).get("/api/trails/999999");
    expect(response.status).toBe(404);
  });

  test("falls back to a local weather estimate when the trail has no coordinates", async () => {
    const created = await request(app)
      .post("/api/trails")
      .set("Authorization", `Bearer ${adminToken}`)
      .send({ name: "Sin coordenadas", location: "Test", difficulty: "Baja" });

    const response = await request(app).get(`/api/trails/${created.body.id}/weather`);

    expect(response.status).toBe(200);
    expect(response.body.source).toContain("sin conexion");
  });

  test("rejects trail creation without authentication", async () => {
    const response = await request(app)
      .post("/api/trails")
      .send({ name: "Sin auth", location: "Test", difficulty: "Baja" });

    expect(response.status).toBe(401);
  });

  test("rejects trail creation from a non-admin user", async () => {
    const response = await request(app)
      .post("/api/trails")
      .set("Authorization", `Bearer ${userToken}`)
      .send({ name: "No admin", location: "Test", difficulty: "Baja" });

    expect(response.status).toBe(403);
  });

  test("allows an admin to create a trail", async () => {
    const response = await request(app)
      .post("/api/trails")
      .set("Authorization", `Bearer ${adminToken}`)
      .send({
        name: "Sendero de prueba",
        location: "Zona de test",
        difficulty: "Media",
        distance_km: 5.5,
        route_coordinates: [
          [-32.1, -70.1],
          [-32.2, -70.2],
        ],
      });

    expect(response.status).toBe(201);
    expect(JSON.parse(response.body.route_coordinates)).toEqual([
      [-32.1, -70.1],
      [-32.2, -70.2],
    ]);
  });

  test("creates and lists reports for a trail, requiring authentication", async () => {
    const list = await request(app).get("/api/trails");
    const [trail] = list.body;

    const unauthenticated = await request(app)
      .post(`/api/trails/${trail.id}/reports`)
      .send({ issue_summary: "Barro", severity: "Media", trail_state: "Precaucion" });
    expect(unauthenticated.status).toBe(401);

    const created = await request(app)
      .post(`/api/trails/${trail.id}/reports`)
      .set("Authorization", `Bearer ${userToken}`)
      .send({ issue_summary: "Barro", severity: "Media", trail_state: "Precaucion" });

    expect(created.status).toBe(201);
    expect(created.body.reporter_name).toBe("Usuaria Dos");

    const reports = await request(app).get(`/api/trails/${trail.id}/reports`);
    expect(reports.status).toBe(200);
    expect(reports.body.some((report) => report.id === created.body.id)).toBe(true);
  });
});
