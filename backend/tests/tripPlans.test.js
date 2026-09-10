const request = require("supertest");
const { randomUUID } = require("crypto");
const runMigrations = require("../src/migrate");
const seedDatabase = require("../src/seed");
const { query } = require("../src/db");
const { processTripNotifications } = require("../src/tripNotifications");
const app = require("../src/server");
let token, otherToken, trailId;
const auth = () => ({ Authorization: `Bearer ${token}` });
beforeAll(async () => {
  await runMigrations(); await seedDatabase();
  trailId = (await query("SELECT id FROM trails LIMIT 1")).rows[0].id;
  const register = (email) => request(app).post("/api/auth/register").send({ name: "Test", email, password: process.env.TEST_USER_PASSWORD, accepted_terms_version: "2026-08-13" });
  token = (await register("plan@example.test")).body.token;
  otherToken = (await register("other-plan@example.test")).body.token;
});
beforeEach(async () => {
  await query("DELETE FROM trip_notifications"); await query("DELETE FROM trip_plans");
  process.env.ALERT_WEBHOOK_URL = "https://notifications.example.test/events";
  process.env.ALERT_WEBHOOK_TOKEN = "test-channel-only";
});
afterAll(() => { delete process.env.ALERT_WEBHOOK_URL; delete process.env.ALERT_WEBHOOK_TOKEN; });
const payload = () => ({ client_plan_id: randomUUID(), trail_id: trailId,
  expected_return_at: new Date(Date.now() + 3600000).toISOString(), grace_minutes: 30,
  contact_name: "Contacto", contact_phone: "+5491100000000" });
const create = (body = payload()) => request(app).post("/api/trip-plans").set(auth()).send(body);

test("cannot activate automatic alerts without a configured channel", async () => {
  delete process.env.ALERT_WEBHOOK_TOKEN;
  expect((await create()).status).toBe(503);
  expect((await query("SELECT * FROM trip_plans")).rows).toHaveLength(0);
});
test("requires authentication and validates deadlines", async () => {
  expect((await request(app).post("/api/trip-plans").send(payload())).status).toBe(401);
  expect((await create({ ...payload(), expected_return_at: new Date(Date.now() - 1000).toISOString() })).status).toBe(400);
});
test("creation and retries preserve one durable plan; other accounts cannot close it", async () => {
  const body = payload();
  const first = await create(body); const retry = await create(body);
  expect(first.status).toBe(201); expect(retry.body.id).toBe(first.body.id);
  expect((await query("SELECT * FROM trip_plans")).rows).toHaveLength(1);
  const denied = await request(app).post(`/api/trip-plans/${first.body.id}/close`).set("Authorization", `Bearer ${otherToken}`).send({ status: "checked_in" });
  expect(denied.status).toBe(404);
  const list = await request(app).get("/api/trip-plans").set("Authorization", `Bearer ${otherToken}`);
  expect(list.body).toEqual([]);
});
test("missing check-in triggers once after grace, even without further phone requests", async () => {
  const body = payload(); const created = await create(body);
  const send = jest.fn().mockResolvedValue(undefined);
  await processTripNotifications({ now: new Date(Date.parse(body.expected_return_at) + 29 * 60000), send });
  expect(send).not.toHaveBeenCalled();
  const now = new Date(Date.parse(body.expected_return_at) + 31 * 60000);
  await Promise.all([processTripNotifications({ now, send }), processTripNotifications({ now, send })]);
  await processTripNotifications({ now, send });
  expect(send).toHaveBeenCalledTimes(1);
  const status = (await request(app).get("/api/trip-plans").set(auth())).body.find((plan) => plan.id === created.body.id);
  expect(status.status).toBe("overdue");
  expect(status.notification_status).toBe("accepted");
  expect(status.notification_status).not.toBe("delivered");
});
test("check-in closes the plan idempotently and suppresses an unsent notification", async () => {
  const body = payload(); const created = await create(body);
  const close = () => request(app).post(`/api/trip-plans/${created.body.id}/close`).set(auth()).send({ status: "checked_in" });
  expect((await close()).body.status).toBe("checked_in");
  expect((await close()).body.status).toBe("checked_in");
  const send = jest.fn();
  await processTripNotifications({ now: new Date(Date.parse(body.expected_return_at) + 40 * 60000), send });
  expect(send).not.toHaveBeenCalled();
});
test("provider failure and a stale lease are retried with the same notification identity", async () => {
  const body = payload(); await create(body);
  const now = new Date(Date.parse(body.expected_return_at) + 40 * 60000);
  const send = jest.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(undefined);
  await processTripNotifications({ now, send });
  expect((await query("SELECT * FROM trip_notifications")).rows[0].status).toBe("pending");
  await query("UPDATE trip_notifications SET status = 'processing', lease_until = $1", [now.toISOString()]);
  await processTripNotifications({ now: new Date(now.getTime() + 120000), send });
  expect(send).toHaveBeenCalledTimes(2);
  expect(send.mock.calls[0][1]).toBe(send.mock.calls[1][1]);
});
