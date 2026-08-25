const request = require("supertest");
const runMigrations = require("../src/migrate");
const seedDatabase = require("../src/seed");
const app = require("../src/server");

let token;
let trailId;

beforeAll(async () => {
  await runMigrations();
  await seedDatabase();

  const registered = await request(app).post("/api/auth/register").send({
    name: "Corredora",
    email: "corredora@misendero.app",
    password: "correcta123",
    accepted_terms_version: "2026-08-13",
  });
  token = registered.body.token;

  const trails = await request(app).get("/api/trails");
  trailId = trails.body[0].id;
});

describe("activities", () => {
  test("rejects creation without authentication", async () => {
    const response = await request(app).post("/api/activities").send({
      trail_id: trailId,
      started_at: new Date().toISOString(),
    });

    expect(response.status).toBe(401);
  });

  test("persists a finished activity and reflects it in /me stats", async () => {
    const startedAt = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    const endedAt = new Date().toISOString();

    const created = await request(app)
      .post("/api/activities")
      .set("Authorization", `Bearer ${token}`)
      .send({
        trail_id: trailId,
        started_at: startedAt,
        ended_at: endedAt,
        distance_km: 8.4,
        duration_minutes: 60,
      });

    expect(created.status).toBe(201);
    expect(created.body.trail_id).toBe(trailId);

    const list = await request(app)
      .get("/api/activities")
      .set("Authorization", `Bearer ${token}`);

    expect(list.status).toBe(200);
    expect(list.body).toHaveLength(1);

    const profile = await request(app)
      .get("/api/auth/me")
      .set("Authorization", `Bearer ${token}`);

    expect(profile.body.stats.completed_routes).toBe(1);
    expect(profile.body.stats.total_distance_km).toBe(8.4);
  });
});
