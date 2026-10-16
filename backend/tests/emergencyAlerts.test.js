const request = require("supertest");
const runMigrations = require("../src/migrate");
const seedDatabase = require("../src/seed");
const app = require("../src/server");

let token;
const testPassword = process.env.TEST_USER_PASSWORD;

beforeAll(async () => {
  await runMigrations();
  await seedDatabase();

  const registered = await request(app).post("/api/auth/register").send({
    name: "Excursionista",
    email: "excursionista@misendero.app",
    password: testPassword,
    accepted_terms_version: "2026-10-16",
  });
  token = registered.body.token;
});

describe("emergency alerts", () => {
  test("accepts an SOS without GPS, ignores claimed delivery and deduplicates retries", async () => {
    const event = require("crypto").randomUUID();
    const payload = { client_event_id: event, latitude: null, longitude: null, status: "sent" };
    const first = await request(app).post("/api/emergency-alerts").set("Authorization", `Bearer ${token}`).send(payload);
    const retry = await request(app).post("/api/emergency-alerts").set("Authorization", `Bearer ${token}`).send(payload);
    expect(first.status).toBe(201);
    expect(first.body.status).toBe("registered");
    expect(first.body.latitude).toBeNull();
    expect(retry.body.id).toBe(first.body.id);
  });
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
      .send({
        latitude: -41.17,
        longitude: -71.47,
        device_battery_percent: 42,
        contact_name: "Contacto Uno",
        contact_phone: "+5491100000000",
        message_body: "SOS MiSendero. Necesito asistencia.",
        last_known_at: "2026-08-27T12:00:00.000Z",
      });

    expect(created.status).toBe(201);
    expect(created.body.status).toBe("registered");
    expect(created.body.contact_name).toBe("Contacto Uno");
    expect(created.body.message_body).toContain("SOS MiSendero");

    const list = await request(app)
      .get("/api/emergency-alerts")
      .set("Authorization", `Bearer ${token}`);

    expect(list.status).toBe(200);
    const saved = list.body.find((alert) => alert.id === created.body.id);
    expect(saved.device_battery_percent).toBe(42);
    expect(saved.contact_phone).toBe("+5491100000000");
  });

  test("rejects an out-of-range latitude", async () => {
    const response = await request(app)
      .post("/api/emergency-alerts")
      .set("Authorization", `Bearer ${token}`)
      .send({ latitude: 200, longitude: -71.47 });

    expect(response.status).toBe(400);
  });
});
