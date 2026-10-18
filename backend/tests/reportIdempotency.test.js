const request = require("supertest");
const { randomUUID } = require("node:crypto");
const app = require("../src/server");
const migrate = require("../src/migrate");
const { query } = require("../src/db");
let token, other, trailId;
beforeAll(async () => {
  await migrate();
  await query(require('node:fs').readFileSync(require('node:path').join(__dirname, '../migrations/009_report_idempotency.sql'), 'utf8'));
  trailId = (await query("INSERT INTO trails (name, location, difficulty) VALUES ('Fixture', 'Fixture', 'Baja') RETURNING id")).rows[0].id;
  for (const email of ['retry-a@example.test', 'retry-b@example.test']) {
    const response = await request(app).post('/api/auth/register').send({ name: 'Fixture', email,
      password: process.env.TEST_USER_PASSWORD, accepted_terms_version: require('../src/terms.json').version });
    expect(response.status).toBe(201); if (!token) token = response.body.token; else other = response.body.token;
  }
});
const send = (payload, auth = token) => request(app).post(`/api/trails/${trailId}/reports`).set('Authorization', `Bearer ${auth}`).send(payload);
test('lost response and concurrent retries return the same observation without overwriting it', async () => {
  const payload = { client_event_id: randomUUID(), issue_summary: 'Barro', severity: 'Media', trail_state: 'Precaucion', observed_at: new Date().toISOString() };
  const first = await send(payload); expect(first.status).toBe(201);
  const retries = await Promise.all([send(payload), send(payload), send(payload)]);
  retries.forEach(r => { expect(r.status).toBe(201); expect(r.body.id).toBe(first.body.id); });
  const conflict = await send({ ...payload, issue_summary: 'Otro evento' });
  expect(conflict.status).toBe(409); expect(conflict.body.code).toBe('IDEMPOTENCY_CONFLICT');
  expect((await query('SELECT * FROM trail_reports WHERE client_event_id = $1', [payload.client_event_id])).rows).toHaveLength(1);
  const secondAuthor = await send(payload, other); expect(secondAuthor.status).toBe(201); expect(secondAuthor.body.id).not.toBe(first.body.id);
});
test('legacy clients remain compatible but separate events require separate UUIDs', async () => {
  const payload = { issue_summary: 'Barro', severity: 'Media', trail_state: 'Precaucion' };
  expect((await send(payload)).status).toBe(201);
  expect((await send({ ...payload, client_event_id: 'bad-uuid' })).status).toBe(400);
  const a = await send({ ...payload, client_event_id: randomUUID() });
  const b = await send({ ...payload, client_event_id: randomUUID() });
  expect(a.status).toBe(201); expect(b.status).toBe(201); expect(a.body.id).not.toBe(b.body.id);
});
