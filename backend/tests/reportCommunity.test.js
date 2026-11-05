const request = require("supertest");
const { randomUUID } = require("node:crypto");
const app = require("../src/server");
const migrate = require("../src/migrate");
const { query } = require("../src/db");
const { cleanupStaleReports } = require("../src/cleanupStaleReports");
const terms = require("../src/terms.json");
let owner, first, second, trailId, report;
const auth = user => ({ Authorization: `Bearer ${user.token}` });
const ago = seconds => new Date(Date.now() - seconds * 1000).toISOString();
const feedback = (user, value, observed_at = ago(1), id = report.id) => request(app).post(`/api/reports/${id}/feedback`).set(auth(user)).send({ feedback: value, observed_at });
const create = body => request(app).post(`/api/trails/${trailId}/reports`).set(auth(owner)).send({
  issue_summary: "Barro", severity: "Media", trail_state: "Precaucion", observed_at: ago(7200),
  latitude: -41.001234, longitude: -71, route_progress_meters: 137, ...body,
});
beforeAll(async () => {
  await migrate();
  for (const key of ["owner", "first", "second"]) {
    const result = await request(app).post("/api/auth/register").send({ name: "Privado", email: `${key}-${randomUUID()}@example.test`,
      password: process.env.TEST_USER_PASSWORD, accepted_terms_version: terms.version });
    expect(result.status).toBe(201);
    if (key === "owner") owner = result.body; else if (key === "first") first = result.body; else second = result.body;
  }
  trailId = (await query(`INSERT INTO trails (name, location, difficulty, route_coordinates) VALUES ('Comunidad', 'Fixture', 'Baja', $1) RETURNING id`,
    [JSON.stringify([[-41, -71], [-41.01, -71]])])).rows[0].id;
});
beforeEach(async () => { const result = await create({}); expect(result.status).toBe(201); report = result.body; });

test("feedback requires authentication, validates values and keeps one current response per account", async () => {
  expect((await request(app).post(`/api/reports/${report.id}/feedback`).send({ feedback: "still_there", observed_at: ago(1) })).status).toBe(401);
  expect((await feedback(first, "inventado")).status).toBe(400);
  const at = ago(20);
  const a = await feedback(first, "still_there", at); expect(a.status).toBe(200); expect(a.body.confirmation_count).toBe(1);
  expect((await feedback(first, "still_there", at)).body.confirmation_count).toBe(1);
  expect((await query("SELECT * FROM report_feedback WHERE report_id=$1", [report.id])).rows).toHaveLength(1);
  const anonymous = await request(app).get(`/api/trails/${trailId}/reports`);
  const shared = anonymous.body.find(item => item.id === report.id);
  expect(shared).toMatchObject({ confirmation_count: 1, community_status: "confirmed", latitude: -41.001, my_feedback: null });
  expect(shared).not.toHaveProperty("reporter_user_id"); expect(shared).not.toHaveProperty("user_id");
  expect(shared.last_confirmed_at).toMatch(/:00:00\.000Z$/);
});

test("one disagreement keeps the hazard visible; two independent clearances resolve it and a later sighting reopens it", async () => {
  const one = await feedback(first, "not_there", ago(30));
  expect(one.status).toBe(200); expect(one.body.community_status).toBe("disputed");
  expect((await feedback(first, "not_there", ago(25))).body.community_status).toBe("disputed");
  const two = await feedback(second, "not_there", ago(20)); expect(two.body.community_status).toBe("resolved");
  const reopened = await feedback(first, "still_there", ago(10));
  expect(reopened.body.community_status).toBe("confirmed"); expect(reopened.body.cleared_count).toBe(1);
});

test("the author can resolve their own observation and older retries cannot overwrite a newer answer", async () => {
  expect((await feedback(owner, "not_there", ago(20))).body.community_status).toBe("resolved");
  const old = await feedback(owner, "still_there", ago(40));
  expect(old.body.my_feedback).toBe("not_there"); expect(old.body.community_status).toBe("resolved");
  expect(old.body.last_confirmed_at).not.toBeNull();
});

test("an unsure answer preserves the last real sighting and cannot silently expire a renewed hazard", async () => {
  await query("UPDATE trail_reports SET observed_at=$2 WHERE id=$1", [report.id, ago(40 * 86400)]);
  await query("INSERT INTO report_feedback (report_id,user_id,feedback,observed_at,last_seen_at) VALUES ($1,$2,'still_there',$3,$3)", [report.id, first.user.id, ago(86400)]);
  const response = await feedback(first, "unsure", ago(10)); expect(response.status).toBe(200);
  expect(Date.parse(response.body.expires_at)).toBeGreaterThan(Date.now());
  await cleanupStaleReports();
  const reports = await request(app).get(`/api/trails/${trailId}/reports`);
  expect(reports.body.some(item => item.id === report.id)).toBe(true);
});

test("affected sections validate both endpoints and progress, preserve retry identity and minimize public coordinates", async () => {
  const payload = { client_event_id: randomUUID(), observed_at: ago(7200), end_latitude: -41.005678, end_longitude: -71, route_end_progress_meters: 631 };
  const result = await create(payload); expect(result.status).toBe(201); expect(result.body.end_latitude).toBeCloseTo(-41.005678, 5);
  expect((await create(payload)).body.id).toBe(result.body.id);
  expect((await create({ ...payload, route_end_progress_meters: 700 })).status).toBe(409);
  expect((await create({ ...payload, client_event_id: randomUUID(), end_latitude: -42 })).status).toBe(400);
  expect((await create({ end_latitude: -41.005 })).status).toBe(400);
  expect((await create({ ...payload, client_event_id: randomUUID(), route_end_progress_meters: 20 })).status).toBe(400);
  const shared = (await request(app).get(`/api/trails/${trailId}/reports`)).body.find(item => item.id === result.body.id);
  expect(shared.end_latitude).toBe(-41.006); expect(shared.route_end_progress_meters).toBe(600);
});

test("hidden and blocked-author reports cannot receive community feedback", async () => {
  await query("UPDATE trail_reports SET moderation_status='hidden' WHERE id=$1", [report.id]);
  expect((await feedback(first, "still_there")).status).toBe(404);
  await query("UPDATE trail_reports SET moderation_status='visible' WHERE id=$1", [report.id]);
  await query("INSERT INTO report_blocks (user_id,blocked_user_id) VALUES ($1,$2)", [first.user.id, owner.user.id]);
  expect((await feedback(first, "still_there")).status).toBe(404);
});
