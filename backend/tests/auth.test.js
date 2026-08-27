const request = require("supertest");
const runMigrations = require("../src/migrate");
const app = require("../src/server");

beforeAll(async () => {
  await runMigrations();
});

describe("auth", () => {
  test("registers the first user as admin and returns a token", async () => {
    const response = await request(app).post("/api/auth/register").send({
      name: "Ana Pereyra",
      email: "ana@misendero.app",
      password: "correcta123",
      accepted_terms_version: "2026-08-13",
    });

    expect(response.status).toBe(201);
    expect(response.body.token).toBeTruthy();
    expect(response.body.user.role).toBe("admin");
    expect(response.body.user.password_hash).toBeUndefined();
  });

  test("registers a second user as a regular user", async () => {
    const response = await request(app).post("/api/auth/register").send({
      name: "Luis Ferreyra",
      email: "luis@misendero.app",
      password: "correcta123",
      accepted_terms_version: "2026-08-13",
    });

    expect(response.status).toBe(201);
    expect(response.body.user.role).toBe("user");
  });

  test("rejects registration without accepting terms", async () => {
    const response = await request(app).post("/api/auth/register").send({
      name: "Sin Terminos",
      email: "sinterminos@misendero.app",
      password: "correcta123",
    });

    expect(response.status).toBe(400);
  });

  test("rejects duplicate email", async () => {
    const response = await request(app).post("/api/auth/register").send({
      name: "Ana Otra",
      email: "ana@misendero.app",
      password: "correcta123",
      accepted_terms_version: "2026-08-13",
    });

    expect(response.status).toBe(409);
  });

  test("logs in with valid credentials", async () => {
    const response = await request(app).post("/api/auth/login").send({
      email: "ana@misendero.app",
      password: "correcta123",
    });

    expect(response.status).toBe(200);
    expect(response.body.token).toBeTruthy();
  });

  test("rejects invalid credentials", async () => {
    const response = await request(app).post("/api/auth/login").send({
      email: "ana@misendero.app",
      password: "incorrecta",
    });

    expect(response.status).toBe(401);
  });

  test("/me requires a valid session", async () => {
    const withoutToken = await request(app).get("/api/auth/me");
    expect(withoutToken.status).toBe(401);

    const login = await request(app).post("/api/auth/login").send({
      email: "ana@misendero.app",
      password: "correcta123",
    });
    const withToken = await request(app)
      .get("/api/auth/me")
      .set("Authorization", `Bearer ${login.body.token}`);

    expect(withToken.status).toBe(200);
    expect(withToken.body.user.email).toBe("ana@misendero.app");
    expect(withToken.body.stats).toEqual({ completed_routes: 0, total_distance_km: 0 });
  });
});
