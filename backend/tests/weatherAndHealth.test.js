const request = require("supertest");
const app = require("../src/server");
const migrate = require("../src/migrate");
const { query } = require("../src/db");
let trailId;
beforeAll(migrate);
beforeEach(async () => { await query("DELETE FROM trails"); trailId = (await query("INSERT INTO trails (name, location, difficulty, center_lat, center_lng) VALUES ('Medido', 'Bariloche', 'Baja', -41, -71) RETURNING id")).rows[0].id; });
afterEach(() => { jest.restoreAllMocks(); delete process.env.PRIVACY_CONTACT_URL; });
test.each([[10, 0, 0, "bajo"], [28, 0, 0, "medio"], [10, 40, 0, "medio"], [45, 0, 0, "alto"], [10, 70, 0, "alto"], [10, 0, 95, "alto"], [10, 0, 75, "alto"]])("forecast evaluates measured wind=%s rain=%s code=%s as %s", async (wind, rain, code, risk) => {
  jest.spyOn(global, "fetch").mockResolvedValue({ ok: true, json: async () => ({ current: { temperature_2m: 11.4, wind_speed_10m: wind, weather_code: code, time: "2026-10-16T10:00" }, daily: { precipitation_probability_max: [rain], temperature_2m_min: [3], temperature_2m_max: [15] } }) });
  const response = await request(app).get(`/api/trails/${trailId}/weather`); expect(response.status).toBe(200); expect(response.body).toMatchObject({ risk_level: risk, temperature_c: 11, source: "Open-Meteo", date: "2026-10-16" }); expect(response.body.recommendation).toContain(risk === "alto" ? "postergar" : risk === "medio" ? "precaucion" : "favorables");
});
test("missing trail, unavailable coordinates and provider failure never produce a local forecast", async () => {
  const fetchMock = jest.spyOn(global, "fetch").mockResolvedValue({ ok: false, status: 503 }); expect((await request(app).get("/api/trails/999999/weather")).status).toBe(404);
  await query("UPDATE trails SET center_lat = NULL WHERE id = $1", [trailId]); expect((await request(app).get(`/api/trails/${trailId}/weather`)).status).toBe(422); expect(fetchMock).not.toHaveBeenCalled();
  await query("UPDATE trails SET center_lat = -41 WHERE id = $1", [trailId]); expect((await request(app).get(`/api/trails/${trailId}/weather`)).status).toBe(503); fetchMock.mockRejectedValueOnce(new Error("network")); expect((await request(app).get(`/api/trails/${trailId}/weather`)).status).toBe(503);
});

test("3D atmosphere receives timestamp, day/night, clouds and wind without inventing missing optional data", async () => {
  const body = { utc_offset_seconds: -10800, current: { temperature_2m: 11, wind_speed_10m: 24, weather_code: 3,
    wind_direction_10m: 270, cloud_cover: 88, is_day: 0, time: "2026-11-03T19:15" },
    daily: { precipitation_probability_max: [70], temperature_2m_min: [3], temperature_2m_max: [15] } };
  const fetchMock = jest.spyOn(global, "fetch").mockResolvedValue({ ok: true, json: async () => body });
  const response = await request(app).get(`/api/trails/${trailId}/weather`);
  expect(response.status).toBe(200);
  expect(response.body).toMatchObject({ observed_at: "2026-11-03T22:15:00.000Z", is_day: false,
    cloud_cover_percent: 88, wind_direction_degrees: 270, condition: "Nublado" });
  const requested = new URL(fetchMock.mock.calls[0][0]).searchParams.get("current").split(",");
  expect(requested).toEqual(expect.arrayContaining(["is_day", "cloud_cover", "wind_direction_10m"]));
  delete body.current.is_day; delete body.current.cloud_cover; delete body.current.wind_direction_10m;
  const legacy = await request(app).get(`/api/trails/${trailId}/weather`);
  expect(legacy.body).toMatchObject({ is_day: null, cloud_cover_percent: null, wind_direction_degrees: null });
});

test("incomplete weather does not become zero degrees or a fictitious clear forecast", async () => {
  jest.spyOn(global, "fetch").mockResolvedValue({ ok: true, json: async () => ({ current: {}, daily: {} }) });
  const response = await request(app).get(`/api/trails/${trailId}/weather`);
  expect(response.status).toBe(503); expect(response.body.temperature_c).toBeUndefined();
});
test("health, missing routes and the public privacy page preserve their HTTP contract", async () => {
  expect((await request(app).get("/api/health")).body).toEqual({ ok: true, service: "misendero-backend" }); expect((await request(app).get("/not-a-route")).status).toBe(404);
  const page = await request(app).get("/account-deletion"); expect(page.status).toBe(200); expect(page.headers["cache-control"]).toContain("no-store"); expect(page.text).toContain('id="confirm"');
  process.env.PRIVACY_CONTACT_URL = "http://insecure.example.test"; expect((await request(app).get("/api/privacy-contact")).body).toEqual({ url: null }); process.env.PRIVACY_CONTACT_URL = "mailto:privacy@example.test"; expect((await request(app).get("/api/privacy-contact")).body).toEqual({ url: process.env.PRIVACY_CONTACT_URL });
});
