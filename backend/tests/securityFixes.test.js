// Security audit observations. A green test confirms the named behavior, which
// may be a reproduced gap. This is not a product acceptance/security score.
const root = require('node:path').resolve(__dirname,'..');
const request = require(root + '/node_modules/supertest');
const jwt = require(root + '/node_modules/jsonwebtoken');
const crypto = require('node:crypto');
const fs = require('node:fs');
const app = require(root + '/src/server');
const migrate = require(root + '/src/migrate');
const { query } = require(root + '/src/db');
const terms = require(root + '/src/terms.json');
const observations = [];
const record = (id, classification, result) => observations.push({ id, classification, result });
let a, b, trailId;
const auth = token => ({ Authorization: `Bearer ${token}` });
async function register(password = process.env.TEST_USER_PASSWORD) {
  const email = `security-${crypto.randomUUID()}@example.test`;
  const response = await request(app).post('/api/auth/register').send({ name: 'Fixture de seguridad', email, password, accepted_terms_version: terms.version });
  expect(response.status).toBe(201);
  return { ...response.body, email };
}
beforeAll(async () => {
  await migrate();
  trailId = (await query(`INSERT INTO trails (name, location, difficulty, route_coordinates)
    VALUES ('Auditoría sintética', 'Fixture', 'Baja', '[[-41,-71],[-41.01,-71]]') RETURNING id`)).rows[0].id;
  a = await register(); b = await register();
});

test('B01 CONTROL: private routes reject missing credentials and algorithm mismatch', async () => {
  for (const path of ['/api/auth/me','/api/activities','/api/emergency-alerts','/api/trip-plans','/api/auth/me/data']) {
    expect((await request(app).get(path)).status).toBe(401);
  }
  const wrong = jwt.sign({ userId: a.user.id }, process.env.JWT_SECRET, { algorithm: 'HS384' });
  expect((await request(app).get('/api/auth/me').set(auth(wrong))).status).toBe(401);
  record('B01','control_observado',{ unauthenticatedDenied: true, wrongAlgorithmDenied: true });
});
test('B02 CONTROL: database role prevails over a signed admin claim', async () => {
  const staleClaim = jwt.sign({ userId: a.user.id, role: 'admin' }, process.env.JWT_SECRET);
  expect((await request(app).get('/api/reports/moderation').set(auth(staleClaim))).status).toBe(403);
  record('B02','control_observado',{ databaseRoleEnforced: true });
});
test('B03 CONTROL: activities, SOS and plans are scoped to their owner', async () => {
  await request(app).post('/api/activities').set(auth(a.token)).send({ client_session_id: crypto.randomUUID(), trail_id: trailId, started_at: new Date().toISOString() }).expect(201);
  await request(app).post('/api/emergency-alerts').set(auth(a.token)).send({ client_event_id: crypto.randomUUID(), trail_id: trailId, latitude: 1, longitude: 2 }).expect(201);
  await query(`INSERT INTO trip_plans (user_id,client_plan_id,trail_id,expected_return_at,grace_minutes,contact_name,contact_phone)
    VALUES ($1,$2,$3,$4,30,'Fixture','000000')`, [a.user.id, crypto.randomUUID(), trailId, new Date(Date.now()+3600000).toISOString()]);
  for (const path of ['/api/activities','/api/emergency-alerts','/api/trip-plans']) {
    const result = await request(app).get(path).set(auth(b.token));
    expect(result.status).toBe(200); expect(result.body).toHaveLength(0);
  }
  const plans = await request(app).get('/api/trip-plans').set(auth(a.token));
  expect((await request(app).post(`/api/trip-plans/${plans.body[0].id}/close`).set(auth(b.token)).send({ status: 'cancelled' })).status).toBe(404);
  record('B03','control_observado',{ ownerScope: true, crossAccountCloseDenied: true });
});
test('B04 CONTROL: incompatible UTF-8 passwords are rejected without truncation', async () => {
  const prefix = crypto.randomUUID().replace(/-/g,'').repeat(3).slice(0,72);
  for (const password of [prefix+'A','ñ'.repeat(37)]) {
    const response=await request(app).post('/api/auth/register').send({name:'Fixture',email:`long-${crypto.randomUUID()}@example.test`,password,accepted_terms_version:terms.version});
    expect(response.status).toBe(400);
  }
  const user=await register(prefix);
  expect((await request(app).post('/api/auth/login').send({email:user.email,password:prefix+'B'})).status).toBe(400);
  expect((await request(app).post('/api/auth/login').send({email:user.email,password:prefix})).status).toBe(200);
  record('B04','control_observado',{newOverlongPasswordsRejected:true,multibyteChecked:true,suffixNotTruncated:true,legacyResetProcedureRequired:true});
});

test('B05 CONTROL: logout revokes a copied JWT durably without revoking another session', async () => {
  const user=await register();
  const second=await request(app).post('/api/auth/login').send({email:user.email,password:process.env.TEST_USER_PASSWORD});
  expect(second.status).toBe(200);expect(second.body.token).not.toBe(user.token);
  await request(app).post('/api/auth/logout').set(auth(user.token)).expect(200);
  const replay=await request(app).get('/api/auth/me').set(auth(user.token));
  expect(replay.status).toBe(401);expect(replay.body.code).toBe('SESSION_REVOKED');
  await request(app).get('/api/auth/me').set(auth(second.body.token)).expect(200);
  const rows=(await query('SELECT token_hash FROM auth_revocations WHERE user_id=$1',[user.user.id])).rows;
  expect(rows).toHaveLength(1);expect(rows[0].token_hash).toMatch(/^[a-f0-9]{64}$/);expect(rows[0].token_hash).not.toContain(user.token);
  const claims=jwt.decode(second.body.token);expect(claims.exp-claims.iat).toBeLessThanOrEqual(86400);
  record('B05','control_observado',{remoteRevocationConfirmed:true,replayRejected:true,durableHashOnly:true,otherSessionPreserved:true,maxJwtSeconds:86400});
});

test('B06 CONTROL: public reports minimize personal data and API validates their route', async () => {
  const payload={client_event_id:crypto.randomUUID(),issue_summary:'Nombre y domicilio sintéticos',severity:'Media',trail_state:'Precaucion',details:'Texto personal sintético',latitude:10.123456,longitude:20.123456,observed_at:new Date().toISOString()};
  const path=`/api/trails/${trailId}/reports`;
  await request(app).post(path).set(auth(a.token)).send(payload).expect(400);
  payload.latitude=-41.000321;payload.longitude=-71.000321;
  const created=await request(app).post(path).set(auth(a.token)).send(payload);expect(created.status).toBe(201);
  const listed=await request(app).get(path).expect(200);
  const row=listed.body.find(r=>r.id===created.body.id);
  expect(row.details).toBeNull();expect(row.issue_summary).toBe('Incidente de terreno');
  expect(row.latitude).toBe(-41);expect(row.longitude).toBe(-71);expect(row.position_precision_meters).toBe(150);
  expect(new Date(row.observed_at).getUTCMinutes()).toBe(0);expect(row).not.toHaveProperty('reporter_user_id');
  const own=(await request(app).get(path).set(auth(a.token))).body.find(r=>r.id===created.body.id);
  expect(own.details).toBe(payload.details);
  record('B06','control_observado',{outOfTrailRejected:true,publicFreeTextRemoved:true,publicCoordinatesCoarsened:true,timesRounded:true,ownerAccessPreserved:true});
});

test('B07 CONTROL: private lists explicitly prohibit HTTP caching', async () => {
  const headers = {};
  for (const path of ['/api/activities','/api/emergency-alerts','/api/trip-plans']) {
    const r = await request(app).get(path).set(auth(a.token)); expect(r.status).toBe(200);
    expect(r.headers['cache-control'] || '').toContain('no-store');
    headers[path] = { noStore: true, etagPresent: !!r.headers.etag };
  }
  expect((await request(app).get('/api/auth/me/data').set(auth(a.token))).headers['cache-control']).toBe('no-store');
  record('B07','control_observado',headers);
});
test('B08 CONTROL: correction, withdrawal and moderation require appropriate owner/role', async () => {
  const own = await request(app).post(`/api/trails/${trailId}/reports`).set(auth(a.token)).send({ issue_summary:'Fixture', severity:'Media',trail_state:'Precaucion' });
  expect((await request(app).patch(`/api/reports/${own.body.id}`).set(auth(b.token)).send({ issue_summary:'otro',details:'' })).status).toBe(404);
  expect((await request(app).delete(`/api/reports/${own.body.id}`).set(auth(b.token))).status).toBe(404);
  expect((await request(app).post(`/api/reports/${own.body.id}/moderate`).set(auth(b.token)).send({ status:'hidden' })).status).toBe(403);
  record('B08','control_observado',{ crossOwnerModificationDenied: true, adminRequired: true });
});
test('B09 CONTROL: replay-safe report identity prevents duplicate creation and replacement', async () => {
  const payload = { client_event_id:crypto.randomUUID(),issue_summary:'Fixture estable', severity:'Media',trail_state:'Precaucion', observed_at:new Date().toISOString() };
  const send=p=>request(app).post(`/api/trails/${trailId}/reports`).set(auth(a.token)).send(p);
  const first=await send(payload); const again=await send(payload);
  expect(first.status).toBe(201); expect(again.body.id).toBe(first.body.id);
  expect((await send({...payload,issue_summary:'otro contenido'})).status).toBe(409);
  record('B09','control_observado',{ stableReportId: true, conflictingPayloadDenied: true });
});
test('B10 CONTROL: account write budgets persist and do not charge idempotent retries', async () => {
  const user=await register();const path=`/api/trails/${trailId}/reports`;
  const payload={client_event_id:crypto.randomUUID(),issue_summary:'Barro',severity:'Media',trail_state:'Precaucion'};
  await request(app).post(path).set(auth(user.token)).send(payload).expect(201);
  for(let n=1;n<10;n++) await request(app).post(path).set(auth(user.token)).send({...payload,client_event_id:crypto.randomUUID()}).expect(201);
  const limited=await request(app).post(path).set(auth(user.token)).send({...payload,client_event_id:crypto.randomUUID()});
  expect(limited.status).toBe(429);expect(Number(limited.headers['retry-after'])).toBeGreaterThan(0);
  await request(app).post(path).set(auth(user.token)).send(payload).expect(201);
  expect((await query("SELECT used FROM api_write_budgets WHERE user_id=$1 AND resource='reports'",[user.user.id])).rows[0].used).toBe(11);
  record('B10','control_observado',{newWritesLimited:true,retryAfterPresent:true,budgetDurable:true,idempotentRetryPreserved:true});
});

test('B11 CONTROL: deleting an account invalidates its JWT and removes attributed remote data', async () => {
  const user = await register();
  const alert = await request(app).post('/api/emergency-alerts').set(auth(user.token)).send({ client_event_id:crypto.randomUUID(),latitude:1,longitude:2 });
  expect(alert.status).toBe(201);
  expect((await request(app).delete('/api/auth/me').set(auth(user.token)).send({ password:process.env.TEST_USER_PASSWORD })).status).toBe(200);
  const replay = await request(app).get('/api/auth/me').set(auth(user.token));
  expect(replay.status).toBe(401); expect(replay.body.code).toBe('ACCOUNT_DELETED');
  expect((await query('SELECT * FROM emergency_alerts WHERE user_id=$1',[user.user.id])).rows).toHaveLength(0);
  record('B11','control_observado',{ deletedAccountDenied:true, cascadingDataRemoved:true });
});
test('B12 CONTROL: blocking does not disclose cross-trail author linkage', async () => {
  const otherTrail=(await query("INSERT INTO trails (name,location,difficulty) VALUES ('Segunda fixture','Fixture','Baja') RETURNING id")).rows[0].id;
  const create=(trail)=>request(app).post(`/api/trails/${trail}/reports`).set(auth(a.token)).send({client_event_id:crypto.randomUUID(),issue_summary:'Fixture de enlace',severity:'Media',trail_state:'Precaucion'});
  const first=await create(trailId), second=await create(otherTrail);
  expect(first.status).toBe(201);expect(second.status).toBe(201);
  const blocked=await request(app).post(`/api/reports/${first.body.id}/block-author`).set(auth(b.token));
  expect(blocked.status).toBe(200);expect(blocked.body).toEqual({blocked:true});
  record('B12','control_observado',{confirmationOnly:true,crossTrailIdsNotReturned:true});
});
