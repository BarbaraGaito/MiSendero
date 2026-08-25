const request = require("supertest");
const runMigrations = require("../src/migrate");
const seedDatabase = require("../src/seed");
const app = require("../src/server");

let token;

beforeAll(async () => {
  await runMigrations();
  await seedDatabase();

  const registered = await request(app).post("/api/auth/register").send({
    name: "Excursionista",
    email: "excursionista@misendero.app",
    password: "correcta123",
    accepted_terms_version: "2026-08-13",
  });
  token = registered.body.token;
});

describe("emergency alerts", () => {
  test("rejects creation without authentication", async () => {
    const response = await request(app)
      .post("/api/emergency-alerts")
      .send({ latitude: -41.17, longitude: -71.47 });

    expect(response.status).toBe(401);
  });

  test("persists an alert and lists it back for the same user", async () => {
    const created = await request(app)
      .post("/api/emergency-alerts")
      .set("Authorization", `Bearer ${token}`)
      .send({ latitude: -41.17, longitude: -71.47, device_battery_percent: 42 });

    expect(created.status).toBe(201);
    expect(created.body.status).toBe("sent");

    const list = await request(app)
      .get("/api/emergency-alerts")
      .set("Authorization", `Bearer ${token}`);

    expect(list.status).toBe(200);
    expect(list.body).toHaveLength(1);
    expect(list.body[0].device_battery_percent).toBe(42);
  });

  test("rejects an out-of-range latitude", async () => {
    const response = await request(app)
      .post("/api/emergency-alerts")
      .set("Authorization", `Bearer ${token}`)
      .send({ latitude: 200, longitude: -71.47 });

    expect(response.status).toBe(400);
  });
});
