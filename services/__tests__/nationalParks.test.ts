jest.mock("../api", () => ({ getNationalParks: jest.fn(), getNationalPark: jest.fn() }));
jest.mock("../offlineMaps", () => ({ getOfflineMaps: jest.fn().mockResolvedValue([]) }));
jest.mock("expo-network", () => ({ getNetworkStateAsync: jest.fn() }));
jest.mock("../../database/database", () => ({ initDB: jest.fn() }));
jest.mock("../../database/connection", () => {
  const { DatabaseSync } = jest.requireActual("node:sqlite");
  const store = new DatabaseSync(":memory:");
  return { db: {
    execAsync: async (sql: string) => store.exec(sql),
    getFirstAsync: async (sql: string, args: unknown[] = []) => store.prepare(sql).get(...args),
    runAsync: async (sql: string, args: unknown[] = []) => store.prepare(sql).run(...args),
  } };
});

import * as api from "../api";
import * as Network from "expo-network";
import { db } from "../../database/connection";
import { getOfflineMaps } from "../offlineMaps";
import { getNationalPark, getNationalParks, getParkRegistration, getRegistrationLabel, parkProfileNeedsReview } from "../nationalParks";
import { NationalPark } from "../../types";

const profiles = require("../../backend/src/data/nationalParks");
const park: NationalPark = {
  ...profiles.find((item: { slug: string }) => item.slug === "los-glaciares"),
  trails: [{ id: 81, name: "Mirador de los Condores", image_url: null }],
  live_status: { closures: "not_integrated", weather_alerts: "not_integrated", weather_url: "https://www.smn.gob.ar/alertas" },
};

beforeEach(async () => {
  jest.clearAllMocks();
  await db.execAsync("DROP TABLE IF EXISTS national_park_cache");
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: true });
  (api.getNationalParks as jest.Mock).mockResolvedValue([park]);
  (api.getNationalPark as jest.Mock).mockResolvedValue(park);
  (getOfflineMaps as jest.Mock).mockResolvedValue([]);
});

test("real API profiles persist for offline list and detail, without claiming live status", async () => {
  expect((await getNationalParks()).fromCache).toBe(false);
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: false });
  const result = await getNationalPark(park.slug);
  expect(result.data).toEqual(park);
  expect(result.fromCache).toBe(true);
  expect(result.cachedAt).toEqual(expect.any(Number));
  expect((await getNationalParks()).data).toEqual([park]);
  expect(api.getNationalPark).not.toHaveBeenCalled();
  expect(result.data.live_status.closures).toBe("not_integrated");
});

test("an API failure can use a labelled saved copy even with device connectivity", async () => {
  await getNationalPark(park.slug);
  (api.getNationalPark as jest.Mock).mockRejectedValue(new Error("timeout"));
  expect((await getNationalPark(park.slug)).fromCache).toBe(true);
});

test("a downloaded trail supplies the park profile without prior visiting the park screen", async () => {
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: false });
  (getOfflineMaps as jest.Mock).mockResolvedValue([
    { updatedAt: 123, trail: { ...park.trails[0], national_park: park } },
    { updatedAt: 123, trail: { ...park.trails[0], national_park: park } },
    { updatedAt: 123, trail: { id: 1, name: "Parque provincial", national_park: null } },
  ]);
  const saved = await getNationalPark(park.slug);
  expect(saved.fromCache).toBe(true);
  expect(saved.data.trails).toHaveLength(1);
  expect((await getNationalParks()).data).toHaveLength(1);
  expect(api.getNationalParks).not.toHaveBeenCalled();
});

test("no data is fabricated for an unknown park or an offline empty cache", async () => {
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: false });
  await expect(getNationalPark("aconcagua")).rejects.toThrow("No hay una ficha");
  await expect(getNationalParks()).rejects.toThrow("Sin fichas guardadas");
});

test("Los Glaciares registration follows the activity season", () => {
  expect(getRegistrationLabel(park, new Date(2026, 4, 1))).toMatch("obligatorio");
  expect(getRegistrationLabel(park, new Date(2026, 8, 30))).toMatch("obligatorio");
  expect(getRegistrationLabel(park, new Date(2026, 9, 1))).toMatch("sujeto a temporada");
  expect(getRegistrationLabel({ ...park, registration: { ...park.registration, requirement: "always" } }, new Date(2026, 9, 1))).toMatch("obligatorio");
});

test("fetching a profile never resets its source review date", async () => {
  const result = await getNationalPark(park.slug);
  expect(result.data.checked_at).toBe("2026-10-11");
  expect(parkProfileNeedsReview(park, Date.parse("2026-12-01"))).toBe(true);
  expect(parkProfileNeedsReview(park, Date.parse("2026-10-12"))).toBe(false);
  expect(parkProfileNeedsReview({ ...park, checked_at: "invalid" })).toBe(true);
});

test("the selected route determines registration requirements, including presential ones", () => {
  const quijadas: NationalPark = profiles.find((item: NationalPark) => item.slug === "sierra-de-las-quijadas");
  const guanacos = "Sendero Guanacos - Sierra de las Quijadas";
  const miradores = "Miradores de Sierra de las Quijadas";
  expect(getParkRegistration(quijadas, guanacos)).toMatchObject({ mode: "in_person", form_url: null });
  expect(getRegistrationLabel(quijadas, new Date(), guanacos)).toMatch("presencial obligatorio");
  expect(getRegistrationLabel(quijadas, new Date(), miradores)).toBe("Consultar requisitos del recorrido");
  expect(getParkRegistration(quijadas)).toEqual(quijadas.registration);
  expect(getParkRegistration(quijadas, "unknown")).toEqual(quijadas.registration);
  const lihue: NationalPark = profiles.find((item: NationalPark) => item.slug === "lihue-calel");
  expect(getRegistrationLabel(lihue)).toMatch("presencial obligatorio");
});

test("new park profiles and per-route registration persist through a real SQLite round trip", async () => {
  const allParks = profiles.map((profile: NationalPark) => ({ ...profile, trails: [], live_status: park.live_status }));
  (api.getNationalParks as jest.Mock).mockResolvedValue(allParks);
  await getNationalParks();
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: false });
  expect((await getNationalParks()).data).toHaveLength(11);
  for (const profile of allParks) expect((await getNationalPark(profile.slug)).data).toEqual(profile);
  const saved = (await getNationalPark("sierra-de-las-quijadas")).data;
  expect(getRegistrationLabel(saved, new Date(), "Sendero Guanacos - Sierra de las Quijadas")).toMatch("presencial obligatorio");
});
