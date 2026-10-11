import * as Network from "expo-network";
import { db } from "../database/connection";
import { initDB } from "../database/database";
import { NationalPark, NationalParkProfile } from "../types";
import * as api from "./api";
import { getOfflineMaps } from "./offlineMaps";

export interface ParkResult<T> { data: T; fromCache: boolean; cachedAt: number | null }

const initCache = async () => {
  await initDB();
  await db.execAsync(`CREATE TABLE IF NOT EXISTS national_park_cache (
    cache_key TEXT PRIMARY KEY, data_json TEXT NOT NULL, saved_at INTEGER NOT NULL
  )`);
};

const readCache = async <T>(key: string): Promise<ParkResult<T> | null> => {
  await initCache();
  const row = await db.getFirstAsync<{ data_json: string; saved_at: number }>(
    "SELECT data_json, saved_at FROM national_park_cache WHERE cache_key = ?", [key]
  );
  if (!row) return null;
  try { return { data: JSON.parse(row.data_json), fromCache: true, cachedAt: row.saved_at }; }
  catch { return null; }
};

const writeCache = async (key: string, data: unknown, savedAt: number) => {
  await initCache();
  await db.runAsync(`INSERT INTO national_park_cache (cache_key, data_json, saved_at) VALUES (?, ?, ?)
    ON CONFLICT(cache_key) DO UPDATE SET data_json = excluded.data_json, saved_at = excluded.saved_at`,
  [key, JSON.stringify(data), savedAt]);
};

const canConnect = async () => {
  const state = await Network.getNetworkStateAsync().catch(() => null);
  return state?.isConnected !== false && state?.isInternetReachable !== false;
};

// A downloaded trail contains its institutional profile as well as its trace.
// Offline notices remain unverified even when the profile is available.
const downloadedParks = async (): Promise<ParkResult<NationalPark[]>> => {
  const maps = await getOfflineMaps();
  const parks = new Map<string, NationalPark>();
  let cachedAt: number | null = null;
  for (const map of maps) {
    const trail = map.trail;
    if (!trail?.national_park) continue;
    const profile = trail.national_park;
    const park = parks.get(profile.slug) || { ...profile, trails: [] };
    if (!park.trails.some((item) => item.id === trail.id)) park.trails.push(trail);
    parks.set(profile.slug, park);
    cachedAt = Math.min(cachedAt ?? map.updatedAt, map.updatedAt);
  }
  return { data: [...parks.values()], fromCache: true, cachedAt };
};

export const getNationalParks = async (): Promise<ParkResult<NationalPark[]>> => {
  if (await canConnect()) {
    try {
      const data = await api.getNationalParks();
      const cachedAt = Date.now();
      await writeCache("list", data, cachedAt).catch(() => undefined);
      for (const park of data) await writeCache(park.slug, park, cachedAt).catch(() => undefined);
      return { data, fromCache: false, cachedAt };
    } catch { /* Fall back to explicitly labelled institutional copies. */ }
  }
  const cached = await readCache<NationalPark[]>("list");
  if (cached) return cached;
  const saved = await downloadedParks();
  if (saved.data.length) return saved;
  throw new Error("Sin fichas guardadas. Conectate para consultar los parques.");
};

export const getNationalPark = async (slug: string): Promise<ParkResult<NationalPark>> => {
  if (await canConnect()) {
    try {
      const data = await api.getNationalPark(slug);
      const cachedAt = Date.now();
      await writeCache(slug, data, cachedAt).catch(() => undefined);
      return { data, fromCache: false, cachedAt };
    } catch { /* Saved rules are not a current opening or weather status. */ }
  }
  const cached = await readCache<NationalPark>(slug);
  if (cached) return cached;
  const saved = await downloadedParks();
  const park = saved.data.find((item) => item.slug === slug);
  if (park) return { ...saved, data: park };
  throw new Error("No hay una ficha oficial disponible para este parque.");
};

export const getParkRegistration = (park: NationalParkProfile, trailName?: string) =>
  (trailName && park.registration_by_trail?.[trailName]) || park.registration;

export const getRegistrationLabel = (park: NationalParkProfile, date = new Date(), trailName?: string) => {
  const registration = getParkRegistration(park, trailName);
  if (registration.requirement === "always" ||
      (registration.requirement === "seasonal" && registration.required_months.includes(date.getMonth() + 1))) {
    return registration.mode === "in_person" ? "Registro presencial obligatorio antes de salir" : "Registro obligatorio antes de salir";
  }
  if (registration.requirement === "consult") return "Consultar requisitos del recorrido";
  return "Registro sujeto a temporada y actividad";
};

export const parkProfileNeedsReview = (park: NationalParkProfile, now = Date.now()) => {
  const reviewed = Date.parse(`${park.checked_at}T00:00:00-03:00`);
  return !Number.isFinite(reviewed) || now - reviewed > 30 * 24 * 60 * 60 * 1000;
};
