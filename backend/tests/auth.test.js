const request = require("supertest");
const jwt = require("jsonwebtoken");
const fs = require("fs");
const path = require("path");
const runMigrations = require("../src/migrate");
const { query } = require("../src/db");
const app = require("../src/server");

beforeAll(async () => {
  await runMigrations();
});

describe("auth", () => {
  const testPassword = process.env.TEST_USER_PASSWORD;

  test("registers a regular user and returns a token", async () => {
    const response = await request(app).post("/api/auth/register").send({
      name: "Ana Pereyra",
      email: "ana@misendero.app",
      password: testPassword,
      accepted_terms_version: "2026-08-13",
    });

    expect(response.status).toBe(201);
    expect(response.body.token).toBeTruthy();
    expect(response.body.user.role).toBe("user");
    expect(response.body.user.password_hash).toBeUndefined();
  });

  test("registers every additional user as admin", async () => {
    const response = await request(app).post("/api/auth/register").send({
      name: "Luis Ferreyra",
      email: "luis@misendero.app",
      password: testPassword,
      accepted_terms_version: "2026-08-13",
    });

    expect(response.status).toBe(201);
    expect(response.body.user.role).toBe("user");
  });

  test("does not promote regular users when migrations run", async () => {
    await query("UPDATE users SET role = 'user' WHERE email = $1", [
      "luis@misendero.app",
    ]);

    const promotionMigration = fs.readFileSync(
      path.join(__dirname, "..", "migrations", "002_promote_all_users_to_admin.sql"),
      "utf8"
    );
    await query(promotionMigration);

    const { rows } = await query("SELECT role FROM users WHERE email = $1", [
      "luis@misendero.app",
    ]);
    expect(rows[0].role).toBe("user");
  });

  test("rejects registration without accepting terms", async () => {
    const response = await request(app).post("/api/auth/register").send({
      name: "Sin Terminos",
      email: "sinterminos@misendero.app",
      password: testPassword,
    });

    expect(response.status).toBe(400);
  });

  test("rejects duplicate email", async () => {
    const response = await request(app).post("/api/auth/register").send({
      name: "Ana Otra",
      email: "ana@misendero.app",
      password: testPassword,
      accepted_terms_version: "2026-08-13",
    });

    expect(response.status).toBe(409);
  });

  test("logs in with valid credentials", async () => {
    const response = await request(app).post("/api/auth/login").send({
      email: "ana@misendero.app",
      password: testPassword,
    });

    expect(response.status).toBe(200);
    expect(response.body.token).toBeTruthy();
  });

  test("rejects invalid credentials", async () => {
    const response = await request(app).post("/api/auth/login").send({
      email: "ana@misendero.app",
      password: `${testPassword}-invalid`,
    });

    expect(response.status).toBe(401);
  });

  test("/me requires a valid session", async () => {
    const withoutToken = await request(app).get("/api/auth/me");
    expect(withoutToken.status).toBe(401);

    const login = await request(app).post("/api/auth/login").send({
      email: "ana@misendero.app",
      password: testPassword,
    });
    const withToken = await request(app)
      .get("/api/auth/me")
      .set("Authorization", `Bearer ${login.body.token}`);

    expect(withToken.status).toBe(200);
    expect(withToken.body.user.email).toBe("ana@misendero.app");
    expect(withToken.body.stats).toEqual({ completed_routes: 0, total_distance_km: 0 });
  });

  test("rejects tokens signed with an algorithm outside the allowlist", async () => {
    const token = jwt.sign(
      { userId: 1, role: "user" },
      process.env.JWT_SECRET,
      { algorithm: "HS384" }
    );

    const response = await request(app)
      .get("/api/auth/me")
      .set("Authorization", `Bearer ${token}`);

    expect(response.status).toBe(401);
  });
});
