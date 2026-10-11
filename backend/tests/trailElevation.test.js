const request = require("supertest");
const runMigrations = require("../src/migrate");
const { query } = require("../src/db");
const app = require("../src/server");
const {
  accumulatedElevation, sampleRoute, fetchElevation, cachedElevation, ensureTrailElevation,
} = require("../src/trailElevation");

let fetchMock;
let id = 0;
const createTrail = async (coordinates = [[-32.82, -69.94], [-32.81, -69.94]]) => {
  const { rows } = await query(
    "INSERT INTO trails (name, location, difficulty, route_coordinates) VALUES ($1, $2, $3, $4::jsonb) RETURNING *",
    [`Elevacion ${++id}`, "Mendoza", "Media", JSON.stringify(coordinates)]
  );
  return rows[0];
};

beforeAll(runMigrations);
beforeEach(() => {
  fetchMock = jest.spyOn(global, "fetch").mockImplementation(async (url) => {
    const count = new URL(url).searchParams.get("latitude").split(",").length;
    return { ok: true, json: async () => ({ elevation: Array.from({ length: count }, (_, i) => 2000 + i * 10) }) };
  });
});
afterEach(() => fetchMock.mockRestore());

test("samples the entire trace, including endpoints, within the request budget", () => {
  const coordinates = [[-32, -69], [-32, -69], [-32, -69.01], [-32.01, -69.01]];
  const { samples } = sampleRoute(coordinates);
  expect(samples[0]).toMatchObject({ latitude: -32, longitude: -69, distance_m: 0 });
  expect(samples.at(-1).latitude).toBeCloseTo(-32.01);
  expect(samples.at(-1).longitude).toBeCloseTo(-69.01);
  expect(samples.at(-1).distance_m).toBeGreaterThan(1900);
  expect(samples.every((point, index) => index === 0 || point.distance_m > samples[index - 1].distance_m)).toBe(true);
  expect(sampleRoute([[-32, -69], [-45, -69]]).samples).toHaveLength(500);
  expect(() => sampleRoute([[-32, -69], [-32, -69]])).toThrow("elevation-no-geometry");
});

test("accumulation distinguishes climbs, descents and small DEM fluctuations", () => {
  expect(accumulatedElevation([100, 102, 104, 106, 110])).toEqual({ ascent_m: 10, descent_m: 0 });
  expect(accumulatedElevation([110, 108, 106, 104, 100])).toEqual({ ascent_m: 0, descent_m: 10 });
  expect(accumulatedElevation([100, 101, 99, 102, 100])).toEqual({ ascent_m: 0, descent_m: 0 });
  expect(accumulatedElevation([100, 120, 105, 130])).toEqual({ ascent_m: 45, descent_m: 15 });
  expect(accumulatedElevation([-20, -10, 0])).toEqual({ ascent_m: 20, descent_m: 0 });
});

test("batches at most 100 locations and retains provider heights including zero", async () => {
  fetchMock.mockImplementation(async (url) => {
    const count = new URL(url).searchParams.get("latitude").split(",").length;
    expect(count).toBeLessThanOrEqual(100);
    return { ok: true, json: async () => ({ elevation: Array(count).fill(0) }) };
  });
  const elevation = await fetchElevation({ route_coordinates: [[-32, -69], [-32.2, -69]] });
  expect(fetchMock.mock.calls.length).toBeGreaterThan(1);
  expect(elevation.min_m).toBe(0);
  expect(elevation.ascent_m).toBe(0);
  expect(elevation.points.every((point) => point.elevation_m === 0)).toBe(true);
});

test.each([null, "2100", undefined, NaN])("rejects missing or nonnumeric elevations (%s) without fabricating heights", async (height) => {
  fetchMock.mockImplementation(async (url) => ({ ok: true, json: async () => ({
    elevation: Array(new URL(url).searchParams.get("latitude").split(",").length).fill(height),
  }) }));
  await expect(fetchElevation({ route_coordinates: [[-32, -69], [-32.001, -69]] }))
    .rejects.toThrow("elevation-incomplete-data");
});

test("detail persists the profile and later requests work without the provider", async () => {
  const trail = await createTrail();
  const first = await request(app).get(`/api/trails/${trail.id}`);
  expect(first.status).toBe(200);
  expect(first.body.elevation.points.length).toBeGreaterThan(2);
  expect(first.body.elevation.source).toContain("Copernicus");
  const { rows } = await query("SELECT * FROM trails WHERE id = $1", [trail.id]);
  expect(rows[0].elevation).toEqual(first.body.elevation);
  const calls = fetchMock.mock.calls.length;
  fetchMock.mockRejectedValue(new Error("offline"));
  const second = await request(app).get(`/api/trails/${trail.id}`);
  expect(second.body.elevation).toEqual(first.body.elevation);
  expect(fetchMock).toHaveBeenCalledTimes(calls);
});

test("provider failure leaves the route usable, with elevation unavailable", async () => {
  const trail = await createTrail();
  fetchMock.mockResolvedValue({ ok: false, status: 503 });
  const response = await request(app).get(`/api/trails/${trail.id}`);
  expect(response.status).toBe(200);
  expect(response.body.elevation).toBeNull();
  const { rows } = await query("SELECT elevation FROM trails WHERE id = $1", [trail.id]);
  expect(rows[0].elevation).toBeNull();
});

test("a changed geometry invalidates the old profile and coalesces simultaneous requests", async () => {
  const trail = await createTrail();
  const elevation = await ensureTrailElevation(trail);
  const changed = { ...trail, elevation, route_coordinates: [[-32.84, -69.94], [-32.82, -69.94]] };
  expect(cachedElevation(changed)).toBeNull();
  await query("UPDATE trails SET route_coordinates = $2::jsonb WHERE id = $1", [trail.id, JSON.stringify(changed.route_coordinates)]);
  fetchMock.mockClear();
  const [a, b] = await Promise.all([ensureTrailElevation(changed), ensureTrailElevation(changed)]);
  expect(a).toEqual(b);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(a.geometry_hash).not.toBe(elevation.geometry_hash);
});

test("a route without geometry never contacts the elevation provider", async () => {
  const trail = await createTrail(null);
  const response = await request(app).get(`/api/trails/${trail.id}`);
  expect(response.body.elevation).toBeNull();
  expect(fetchMock).not.toHaveBeenCalled();
});
