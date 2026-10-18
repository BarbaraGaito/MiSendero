// Functional acceptance probe kept separate from the regression-suite command.
// A failure is retained as evidence, never converted to an expected success.
const request = require('supertest');
const app = require('../../src/server');
const migrate = require('../../src/migrate');
const { query } = require('../../src/db');
const terms = require('../../src/terms.json');
let token, trailId;
beforeAll(async () => {
  await migrate();
  trailId = (await query("INSERT INTO trails (name, location, difficulty) VALUES ('Functional retry', 'Fixture', 'Baja') RETURNING id")).rows[0].id;
  const registered = await request(app).post('/api/auth/register').send({ name: 'Functional fixture', email: 'functional-retry@example.test',
    password: process.env.TEST_USER_PASSWORD, accepted_terms_version: terms.version });
  expect(registered.status).toBe(201);
  token = registered.body.token;
});
test('MF07 retrying a report after a lost response creates one remote observation', async () => {
  const payload = { issue_summary: 'Barro funcional', severity: 'Media', trail_state: 'Precaución', observed_at: new Date().toISOString() };
  const first = await request(app).post(`/api/trails/${trailId}/reports`).set('Authorization', `Bearer ${token}`).send(payload);
  expect(first.status).toBe(201); // Server commits; client is assumed to lose this acknowledgement.
  const retry = await request(app).post(`/api/trails/${trailId}/reports`).set('Authorization', `Bearer ${token}`).send(payload);
  expect(retry.status).toBe(201);
  const persisted = (await query('SELECT id FROM trail_reports WHERE trail_id = $1', [trailId])).rows;
  console.info(JSON.stringify({ scenario: 'MF07', firstId: first.body.id, retryId: retry.body.id, persistedRows: persisted.length }));
  expect(persisted).toHaveLength(1);
  expect(retry.body.id).toBe(first.body.id);
});
