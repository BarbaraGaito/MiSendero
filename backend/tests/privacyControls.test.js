const request = require("supertest");
const jwt = require("jsonwebtoken");
const { randomUUID } = require("crypto");
process.env.AUTH_RATE_LIMIT_MAX = "1000";
const app = require("../src/server");
const migrate = require("../src/migrate");
const { query } = require("../src/db");
const terms = require("../src/terms.json");
const notices = require("../src/privacyNotices.json");
let trailId;
const password = process.env.TEST_USER_PASSWORD;
const register = async () => (await request(app).post("/api/auth/register").send({ name: "Nombre privado", email: `${randomUUID()}@example.test`, password, accepted_terms_version: terms.version })).body;
const auth = (user) => ({ Authorization: `Bearer ${user.token}` });
const report = (user, extra = {}) => request(app).post(`/api/trails/${trailId}/reports`).set(auth(user)).send({ issue_summary: "Barro", severity: "Media", trail_state: "Precaución", ...extra });
beforeAll(async () => {
  await migrate();
  trailId = (await query("INSERT INTO trails (name, location, difficulty) VALUES ('Test privacidad', 'Test', 'Baja') RETURNING id")).rows[0].id;
});

test("records exact versioned decisions and withdrawal without changing another purpose", async () => {
  const user = await register();
  const decision = { client_event_id: randomUUID(), purpose: "analyticsTrainingConsent", notice_version: notices.version,
    notice_text: notices.analyticsTrainingConsent, granted: true, decided_at: new Date().toISOString() };
  const post = (body) => request(app).post("/api/auth/me/privacy-decisions").set(auth(user)).send(body);
  expect((await post(decision)).status).toBe(201);
  expect((await post(decision)).status).toBe(201);
  expect((await post({ ...decision, client_event_id: randomUUID(), granted: false })).status).toBe(201);
  expect((await post({ ...decision, notice_text: "otro texto" })).status).toBe(400);
  const rows = (await query("SELECT * FROM privacy_decisions WHERE user_id = $1 ORDER BY id", [user.user.id])).rows;
  expect(rows).toHaveLength(2);
  expect(rows.map((row) => row.granted)).toEqual([true, false]);
  expect(rows.every((row) => row.purpose === "analyticsTrainingConsent" && row.notice_text === notices.analyticsTrainingConsent && row.received_at)).toBe(true);
});

test("terms acceptance stores its text and excludes physiological or analytics grants", async () => {
  const user = await register();
  const saved = (await query("SELECT terms_version, terms_text FROM users WHERE id = $1", [user.user.id])).rows[0];
  expect(saved.terms_version).toBe(terms.version);
  expect(JSON.parse(saved.terms_text)).toEqual(terms);
  expect((await query("SELECT * FROM privacy_decisions WHERE user_id = $1", [user.user.id])).rows).toEqual([]);
  const invalid = await request(app).post("/api/auth/register").send({ name: "Test", email: "old@example.test", password, accepted_terms_version: "inventada" });
  expect(invalid.status).toBe(400);
});

test("deletion requires password and removes names, activities, contact copies, jobs and all installation credentials", async () => {
  const user = await register();
  const login = await request(app).post("/api/auth/login").send({ email: user.user.email, password });
  const expiredToken = jwt.sign({ userId: user.user.id }, process.env.JWT_SECRET, { expiresIn: -1 });
  const expiredWhileActive = await request(app).get("/api/auth/me").set("Authorization", `Bearer ${expiredToken}`);
  expect(expiredWhileActive.status).toBe(401);
  expect(expiredWhileActive.body.code).toBeUndefined();
  await report(user, { details: "Copia del nombre privado" });
  await query("INSERT INTO activities (user_id, started_at) VALUES ($1, now())", [user.user.id]);
  await query("INSERT INTO emergency_alerts (user_id, latitude, longitude, contact_name, contact_phone) VALUES ($1, -41, -71, 'Contacto', '123456')", [user.user.id]);
  const plan = (await query(`INSERT INTO trip_plans (user_id, client_plan_id, trail_id, expected_return_at, grace_minutes, contact_name, contact_phone)
    VALUES ($1, 'test-plan', $2, now(), 30, 'Contacto', '123456') RETURNING id`, [user.user.id, trailId])).rows[0];
  await query("INSERT INTO trip_notifications (plan_id, due_at, next_attempt_at) VALUES ($1, now(), now())", [plan.id]);
  expect((await request(app).delete("/api/auth/me").set(auth(user)).send({ password: "incorrecta" })).status).toBe(401);
  expect((await request(app).get("/api/auth/me").set(auth(user))).status).toBe(200);
  expect((await request(app).delete("/api/auth/me").set(auth(user)).send({ password })).body.deleted).toBe(true);
  for (const token of [user.token, login.body.token, expiredToken]) {
    expect((await request(app).get("/api/auth/me").set("Authorization", `Bearer ${token}`)).body.code).toBe("ACCOUNT_DELETED");
    expect((await request(app).post(`/api/trails/${trailId}/reports`).set("Authorization", `Bearer ${token}`).send({ issue_summary: "Cola antigua", severity: "Alta", trail_state: "Cerrado" })).status).toBe(401);
  }
  for (const table of ["activities", "emergency_alerts", "trip_plans", "privacy_decisions"]) expect((await query(`SELECT * FROM ${table} WHERE user_id = $1`, [user.user.id])).rows).toEqual([]);
  expect((await query("SELECT * FROM trail_reports WHERE reporter_user_id = $1", [user.user.id])).rows).toEqual([]);
  expect((await query("SELECT * FROM trip_notifications WHERE plan_id = $1", [plan.id])).rows).toEqual([]);
  expect((await request(app).post("/api/auth/login").send({ email: user.user.email, password })).status).toBe(401);
});

test("reports omit author and distinguish old observations uploaded recently", async () => {
  const user = await register();
  const observed_at = new Date(Date.now() - 3600000).toISOString();
  const created = await report(user, { observed_at });
  expect(created.status).toBe(201);
  expect(created.body.observed_at).toBe(observed_at);
  expect(Date.parse(created.body.received_at)).toBeGreaterThan(Date.parse(observed_at));
  expect(created.body).not.toHaveProperty("reporter_name");
  expect(created.body).not.toHaveProperty("reporter_user_id");
  expect(created.body).not.toHaveProperty("accuracy_meters");
  const expired = await report(user, { observed_at: new Date(Date.now() - 40 * 86400000).toISOString() });
  expect(expired.status).toBe(201);
  const listed = await request(app).get(`/api/trails/${trailId}/reports`);
  expect(listed.body.some((item) => item.id === expired.body.id)).toBe(false);
  expect(listed.body.some((item) => item.id === created.body.id)).toBe(true);
});

test("withdrawal, correction, blocking, flags and admin moderation enforce ownership", async () => {
  const author = await register(), reader = await register(), admin = await register();
  const first = (await report(author)).body;
  const second = (await report(author)).body;
  const path = `/api/reports/${first.id}`;
  expect((await request(app).delete(path).set(auth(reader))).status).toBe(404);
  expect((await request(app).patch(path).set(auth(author)).send({ issue_summary: "Corregido", details: "Información actualizada" })).status).toBe(200);
  expect((await request(app).post(`${path}/flag`).set(auth(reader)).send({ reason: "Información personal" })).status).toBe(201);
  expect((await request(app).post(`${path}/moderate`).set(auth(reader)).send({ status: "hidden" })).status).toBe(403);
  const forged = jwt.sign({ userId: reader.user.id, role: "admin" }, process.env.JWT_SECRET);
  expect((await request(app).get("/api/reports/moderation").set("Authorization", `Bearer ${forged}`)).status).toBe(403);
  await query("UPDATE users SET role = 'admin' WHERE id = $1", [admin.user.id]);
  expect((await request(app).get("/api/reports/moderation").set(auth(admin))).body.some((flag) => flag.report_id === first.id)).toBe(true);
  expect((await request(app).post(`${path}/moderate`).set(auth(admin)).send({ status: "hidden" })).status).toBe(200);
  expect((await request(app).get(`/api/trails/${trailId}/reports`)).body.some((item) => item.id === first.id)).toBe(false);
  const blocked = await request(app).post(`/api/reports/${second.id}/block-author`).set(auth(reader));
  expect(blocked.body.hidden_report_ids).toEqual(expect.arrayContaining([first.id, second.id]));
  expect((await request(app).get(`/api/trails/${trailId}/reports`).set(auth(reader))).body.some((item) => item.id === second.id)).toBe(false);
  expect((await request(app).delete(`/api/reports/${second.id}`).set(auth(author))).status).toBe(200);
});

test("web account resource and data export support self service without exposing credentials", async () => {
  expect((await request(app).get("/account-deletion")).text).toContain("Eliminar definitivamente");
  expect((await request(app).get("/account-assets/account.js")).status).toBe(200);
  expect((await request(app).get("/api/auth/me/data")).status).toBe(401);
  const user = await register();
  await request(app).patch("/api/auth/me").set(auth(user)).send({ name: "Nombre corregido" }).expect(200);
  const data = await request(app).get("/api/auth/me/data").set(auth(user));
  expect(data.body.user.name).toBe("Nombre corregido");
  expect(data.body.user).not.toHaveProperty("password_hash");
  expect(data.headers["cache-control"]).toBe("no-store");
});
