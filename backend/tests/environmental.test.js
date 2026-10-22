// Integration tests use isolated software fixtures, never scientific data.
const request = require("supertest");
const app = require("../src/server");
const migrate = require("../src/migrate");
const { query } = require("../src/db");
const registry = require("../src/data/environmentalModels.json");
const { checksum } = require("../src/environmental");
const { batchBody, validateBatch } = require("../src/contracts/environmental");
const { importEnvironmentalBatch } = require("../src/environmentalImport");
const { buildEnvironmentalBatches } = require("../src/environmentalBatch");
const fixture = require("../../testing/fixtures/environmental.cjs");
let trail, batch;
beforeAll(migrate);
beforeEach(async () => {
  jest.spyOn(Date, "now").mockReturnValue(fixture.now);
  await query("DELETE FROM environmental_snapshots"); await query("DELETE FROM trails");
  trail = (await query(`INSERT INTO trails (name, location, difficulty, center_lat, center_lng, route_coordinates)
    VALUES ('Fixture', 'Test', 'Media', -41, -71, $1) RETURNING *`, [fixture.fixtureTrail.route_coordinates])).rows[0];
  batch = fixture.makeBatch(trail);
  registry.artifacts["fixture-river-3h"] = { ...fixture.artifact };
  registry.reviewed_route_associations.push(fixture.association(batch));
});
afterEach(() => {
  delete registry.artifacts["fixture-river-3h"];
  delete registry.artifacts["fixture-fire"];
  registry.reviewed_route_associations = registry.reviewed_route_associations.filter((r) => !["fixture-river-3h", "fixture-fire"].includes(r.model_id));
  jest.restoreAllMocks();
});

test("a route without observations returns three honest states and a verifiable payload", async () => {
  const result = await request(app).get(`/api/trails/${trail.id}/environmental`);
  expect(result.status).toBe(200);
  expect(result.body.snapshots).toHaveLength(3);
  expect(result.body.snapshots.every((s) => ["no_data", "not_approved"].includes(s.status) && s.prediction === null)).toBe(true);
  expect(checksum(batchBody(result.body))).toBe(result.body.payload_sha256);
  expect(validateBatch(result.body, trail.id, batch.geometry_hash)).toEqual(result.body);
});

test("reviewed import is previewable, idempotent, queryable and becomes historical on expiration", async () => {
  expect(await importEnvironmentalBatch(batch)).toMatchObject({ applied: false, snapshots: 1 });
  expect((await query("SELECT * FROM environmental_snapshots")).rows).toHaveLength(0);
  await importEnvironmentalBatch(batch, true); await importEnvironmentalBatch(batch, true);
  expect((await query("SELECT * FROM environmental_snapshots")).rows).toHaveLength(1);
  const result = await request(app).get(`/api/trails/${trail.id}/environmental`);
  expect(result.body.snapshots.find((s) => s.model_type === "river_level")).toMatchObject({ status: "experimental", prediction: { level_m: 1.23 } });
  Date.now.mockReturnValue(fixture.now + 4 * 3600000);
  const expired = await request(app).get(`/api/trails/${trail.id}/environmental`);
  expect(expired.body.snapshots.find((s) => s.model_type === "river_level").status).toBe("expired");
});

test("changed geometry or revoked geographic review prevents displaying a numerical forecast", async () => {
  await importEnvironmentalBatch(batch, true);
  registry.reviewed_route_associations = [];
  expect((await request(app).get(`/api/trails/${trail.id}/environmental`)).body.snapshots.every((s) => s.prediction === null)).toBe(true);
  registry.reviewed_route_associations.push(fixture.association(batch));
  await query("UPDATE trails SET center_lat = -42 WHERE id = $1", [trail.id]);
  expect((await request(app).get(`/api/trails/${trail.id}/environmental`)).body.snapshots.every((s) => s.prediction === null)).toBe(true);
});

test("unreviewed links, unapproved artifacts, corrupt integrity and future predictor dates are rejected", async () => {
  registry.reviewed_route_associations = [];
  await expect(importEnvironmentalBatch(batch, true)).rejects.toThrow("unreviewed-geographic");
  registry.reviewed_route_associations.push(fixture.association(batch));
  registry.artifacts["fixture-river-3h"].visualization_allowed = false;
  await expect(importEnvironmentalBatch(batch, true)).rejects.toThrow("unapproved-artifact");
  registry.artifacts["fixture-river-3h"].visualization_allowed = true;
  batch.payload_sha256 = "b".repeat(64);
  await expect(importEnvironmentalBatch(batch, true)).rejects.toThrow("checksum");
  batch = fixture.makeBatch(trail); batch.snapshots[1].inputs_available_at = "2026-10-22T13:00:00Z";
  expect(() => validateBatch(batch, trail.id, batch.geometry_hash)).toThrow("temporal-order");
});

test("operational status cannot be supplied for an experimental artifact; unknown routes are not predictions", async () => {
  batch.snapshots[1].status = "available"; batch.payload_sha256 = checksum(batchBody(batch));
  await expect(importEnvironmentalBatch(batch, true)).rejects.toThrow("unapproved-artifact");
  expect((await request(app).get("/api/trails/999999/environmental")).status).toBe(404);
  expect((await request(app).get("/api/trails/not-a-number/environmental")).status).toBe(400);
});

test("station forecasts export to route files only with reviewed links and preserve the numerical result", async () => {
  const s = batch.snapshots[1];
  const run = { schema_version: 1, forecasts: [{ ...s, ...s.prediction,
    series_id: s.prediction.station_id, model_id: s.model_id }] };
  const output = buildEnvironmentalBatches(run);
  expect(output).toHaveLength(1);
  expect(output[0].snapshots.find((row) => row.model_type === "river_level").prediction).toEqual(s.prediction);
  expect(await importEnvironmentalBatch(output[0])).toMatchObject({ applied: false, snapshots: 1 });
  registry.reviewed_route_associations = [];
  expect(buildEnvironmentalBatches(run)).toEqual([]);
});

test("malformed geometry and inconsistent satellite horizons cannot become forecasts", async () => {
  await query("UPDATE trails SET route_coordinates = '[]', center_lat = NULL, center_lng = NULL WHERE id = $1", [trail.id]);
  expect((await request(app).get(`/api/trails/${trail.id}/environmental`)).status).toBe(422);
  batch.snapshots[1].model_type = "snow";
  batch.snapshots[1].prediction = { probability: 0.5, horizon_hours: 24 };
  expect(() => validateBatch(batch, trail.id, batch.geometry_hash)).toThrow("satellite-horizon");
});

test("fire keeps its exact pixel and probability through export/import, and an unapproved diagnostic is never displayed", async () => {
  const s = batch.snapshots[1];
  registry.artifacts['fixture-fire'] = { model_type: 'fire_detection', version: '1', evidence_sha256: s.evidence_sha256,
    visualization_allowed: true, deployment_approved: false };
  const scope = { description: 'Software fixture, one observed land pixel', pixel_id: 'h12v13:142:746', latitude: -41, longitude: -71 };
  registry.reviewed_route_associations.push({ ...fixture.association(batch), model_id: 'fixture-fire', pixel_id: scope.pixel_id });
  const forecast = { ...s, model_id: 'fixture-fire', region_geometry_hash: batch.geometry_hash,
    prediction: { probability: .25, horizon_hours: 24 }, geographic_scope: scope,
    target_at: '2026-10-23T12:00:00Z', valid_until: '2026-10-23T12:00:00Z' };
  const output = buildEnvironmentalBatches({ schema_version: 1, forecasts: [forecast] });
  await importEnvironmentalBatch(output[0], true);
  const result = await request(app).get(`/api/trails/${trail.id}/environmental`);
  expect(result.body.snapshots.find((row) => row.model_type === 'fire_detection').prediction).toEqual(forecast.prediction);
  expect(buildEnvironmentalBatches({ schema_version: 1, forecasts: [{ ...forecast, status: 'not_approved', prediction: null,
    research_candidate_probability: .99 }] })).toEqual([]);
  registry.reviewed_route_associations.find((row) => row.model_id === 'fixture-fire').pixel_id = 'h12v13:999:999';
  expect((await request(app).get(`/api/trails/${trail.id}/environmental`)).body.snapshots.find((row) => row.model_type === 'fire_detection').prediction).toBeNull();
});
