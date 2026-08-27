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

  test("persists an activity ended before destination without counting it as completed", async () => {
    const startedAt = new Date(Date.now() - 45 * 60 * 1000).toISOString();
    const endedAt = new Date().toISOString();

    const created = await request(app)
      .post("/api/activities")
      .set("Authorization", `Bearer ${token}`)
      .send({
        trail_id: trailId,
        started_at: startedAt,
        ended_at: endedAt,
        distance_km: 1.2,
        duration_minutes: 45,
        completion_status: "ended_early",
        route_progress_meters: 1200,
        route_total_meters: 5000,
        ended_latitude: -41.1734,
        ended_longitude: -71.4752,
      });

    expect(created.status).toBe(201);
    expect(created.body.completion_status).toBe("ended_early");
    expect(created.body.route_progress_meters).toBe(1200);
    expect(created.body.ended_latitude).toBe(-41.1734);

    const profile = await request(app)
      .get("/api/auth/me")
      .set("Authorization", `Bearer ${token}`);

    expect(profile.body.stats.completed_routes).toBe(1);
    expect(profile.body.stats.total_distance_km).toBe(9.6);
  });

  test("uses client_session_id to keep activity creation idempotent", async () => {
    const startedAt = new Date(Date.now() - 30 * 60 * 1000).toISOString();
    const endedAt = new Date().toISOString();
    const payload = {
      client_session_id: "local-session-idempotent-test",
      trail_id: trailId,
      started_at: startedAt,
      ended_at: endedAt,
      distance_km: 2.5,
      duration_minutes: 30,
      completion_status: "ended_early",
    };

    const first = await request(app)
      .post("/api/activities")
      .set("Authorization", `Bearer ${token}`)
      .send(payload);
    const second = await request(app)
      .post("/api/activities")
      .set("Authorization", `Bearer ${token}`)
      .send({ ...payload, distance_km: 2.8 });

    expect(first.status).toBe(201);
    expect(second.status).toBe(201);
    expect(second.body.id).toBe(first.body.id);
    expect(second.body.distance_km).toBe(2.8);

    const list = await request(app)
      .get("/api/activities")
      .set("Authorization", `Bearer ${token}`);
    const matching = list.body.filter(
      (activity) => activity.client_session_id === payload.client_session_id
    );

    expect(matching).toHaveLength(1);
  });
});
