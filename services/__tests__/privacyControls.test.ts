import * as SecureStore from "expo-secure-store";
import { db, initDB } from "../../database/database";
import { clearAuthSession, getAuthSession, saveAuthSession } from "../authSession";
import { getPrivacyPreferences, savePrivacyPreferences, privacyNotices } from "../privacyConsent";
import { eraseLocalAccountData, markAccountDeletion, isAccountDeletionPending } from "../accountLifecycle";
import { resolveApiUrl } from "../apiConfig";
import { sanitizeReports } from "../reportPrivacy";
import { enqueue, runSync } from "../syncQueue";
import { saveWearableMetricSample } from "../wearableMetrics";
import { deleteCurrentAccount } from "../deleteAccount";
import * as api from "../api";
jest.mock("expo-network", () => ({ getNetworkStateAsync: jest.fn().mockResolvedValue({ isConnected: true, isInternetReachable: true }) }));
const login = (id: number) => saveAuthSession({ token: `privacy-${id}`, user: { id, name: "Test", email: `${id}@example.test` } });
beforeAll(() => initDB());
afterEach(() => jest.restoreAllMocks());

test("release configuration rejects HTTP, missing endpoint and credentials", () => {
  expect(() => resolveApiUrl(undefined, false)).toThrow("HTTPS");
  expect(() => resolveApiUrl("http://api.example.test/api", false)).toThrow("HTTPS");
  expect(() => resolveApiUrl("https://secret:token@api.example.test/api", false)).toThrow("credenciales");
  expect(resolveApiUrl("https://api.example.test/api/", false)).toBe("https://api.example.test/api");
  expect(resolveApiUrl(undefined, true)).toBe("http://localhost:3001/api");
});

test("distribution build configuration fails before building without an HTTPS API", () => {
  const config = require("../../app.config.js");
  const profile = process.env.EAS_BUILD_PROFILE, endpoint = process.env.EXPO_PUBLIC_API_URL;
  try {
    process.env.EAS_BUILD_PROFILE = "production";
    delete process.env.EXPO_PUBLIC_API_URL;
    expect(() => config({ config: { plugins: [] } })).toThrow("HTTPS");
    process.env.EXPO_PUBLIC_API_URL = "https://api.example.test/api";
    const result = config({ config: { plugins: [["expo-build-properties", { android: {} }]] } });
    expect(result.android.allowBackup).toBe(false);
    expect(result.plugins[0][1].android.usesCleartextTraffic).toBe(false);
  } finally {
    if (profile === undefined) delete process.env.EAS_BUILD_PROFILE; else process.env.EAS_BUILD_PROFILE = profile;
    if (endpoint === undefined) delete process.env.EXPO_PUBLIC_API_URL; else process.env.EXPO_PUBLIC_API_URL = endpoint;
  }
});

test("unavailable keystore holds credentials only in memory; legacy plaintext is discarded", async () => {
  await clearAuthSession();
  jest.spyOn(SecureStore, "isAvailableAsync").mockResolvedValue(false);
  await login(810);
  expect((await getAuthSession())?.token).toBe("privacy-810");
  expect(await db.getFirstAsync("SELECT token FROM auth_session")).toBeNull();
  await clearAuthSession();
  expect(await getAuthSession()).toBeNull();
  await db.runAsync("INSERT INTO auth_session (id, token, user_json) VALUES (1, ?, ?)", ["legacy-secret", JSON.stringify({ id: 810 })]);
  expect(await getAuthSession()).toBeNull();
  expect(await db.getFirstAsync("SELECT token FROM auth_session")).toBeNull();
});

test("secure persistence writes a sentinel, never the token, and fails closed on write failure", async () => {
  await login(811);
  expect((await db.getFirstAsync<{ token: string }>("SELECT token FROM auth_session"))?.token).toBe("__secure_store__");
  jest.spyOn(SecureStore, "setItemAsync").mockRejectedValue(new Error("keystore failure"));
  await expect(login(812)).rejects.toThrow("keystore failure");
  expect((await getAuthSession())?.user.id).toBe(811);
});

test("each privacy decision is independent; denial and withdrawal keep an exact audit and erase samples", async () => {
  await login(813);
  await savePrivacyPreferences({ sensitiveDataConsent: false, analyticsTrainingConsent: true });
  expect(await getPrivacyPreferences()).toMatchObject({ sensitiveDataConsent: false, analyticsTrainingConsent: true });
  await savePrivacyPreferences({ sensitiveDataConsent: true, analyticsTrainingConsent: true });
  const sample = { provider: "apple_healthkit" as const, heartRateBpm: 100, steps: null, activeEnergyKcal: null, speedKmh: null, oxygenSaturation: null, recordedAt: Date.now() };
  await saveWearableMetricSample(sample);
  await savePrivacyPreferences({ sensitiveDataConsent: false, analyticsTrainingConsent: true });
  expect(await getPrivacyPreferences()).toMatchObject({ sensitiveDataConsent: false, analyticsTrainingConsent: true });
  expect((await db.getAllAsync("SELECT * FROM wearable_metric_samples WHERE user_id = 813"))).toEqual([]);
  await expect(saveWearableMetricSample(sample)).rejects.toThrow("autorización");
  const events = await db.getAllAsync<{ purpose: string; notice_version: string; notice_text: string; granted: number }>("SELECT * FROM privacy_decision_events WHERE user_id = 813 ORDER BY decided_at, rowid");
  expect(events).toHaveLength(4);
  expect(events.filter((event) => event.purpose === "sensitiveDataConsent").map((event) => event.granted)).toEqual([0, 1, 0]);
  expect(events.every((event) => event.notice_version === privacyNotices.version && !!event.notice_text)).toBe(true);
  expect((await db.getAllAsync("SELECT * FROM pending_operations WHERE user_id = 813 AND entity_type = 'privacy_decision'"))).toHaveLength(4);
});

test("old coupled grants without an independent notice need new authorization", async () => {
  await login(814);
  await getPrivacyPreferences();
  await db.runAsync("INSERT INTO user_privacy_preferences (id, sensitive_data_consent, analytics_training_consent, updated_at) VALUES (814, 1, 1, ?)", [Date.now()]);
  expect(await getPrivacyPreferences()).toMatchObject({ sensitiveDataConsent: false, analyticsTrainingConsent: false });
});

test("a lost deletion response suspends all queue writes and retries; successful retry cleans only that owner", async () => {
  await login(815);
  await enqueue("activity", { started_at: new Date().toISOString() });
  await db.runAsync("INSERT INTO sessions (user_id, started_at) VALUES (815, 1), (816, 1)");
  const remove = jest.spyOn(api, "deleteAccount").mockRejectedValueOnce(new Error("sin conexión")).mockResolvedValueOnce({ deleted: true });
  await expect(deleteCurrentAccount("test-password")).rejects.toThrow("sin conexión");
  expect(await isAccountDeletionPending(815)).toBe(true);
  await expect(enqueue("activity", {})).rejects.toThrow("baja pendiente");
  expect(await runSync()).toEqual({ processed: 0, failed: 0 });
  await deleteCurrentAccount("test-password");
  expect(remove).toHaveBeenCalledTimes(2);
  expect(await getAuthSession()).toBeNull();
  expect(await db.getAllAsync("SELECT * FROM sessions WHERE user_id = 815")).toEqual([]);
  expect(await db.getAllAsync("SELECT * FROM sessions WHERE user_id = 816")).toHaveLength(1);
  expect(await db.getAllAsync("SELECT * FROM pending_operations WHERE user_id = 815")).toEqual([]);
  await expect(login(815)).rejects.toThrow("baja pendiente");
  await saveAuthSession({ token: "fresh-login", user: { id: 815, name: "Test", email: "815@example.test" } }, { deletionRetryLogin: true });
  expect(await isAccountDeletionPending(815)).toBe(true);
  await expect(enqueue("activity", {})).rejects.toThrow("baja pendiente");
  await clearAuthSession();
});

test("cleanup removes contacts, health and optional stores without requiring all screens to have run", async () => {
  await login(817);
  await savePrivacyPreferences({ sensitiveDataConsent: true, analyticsTrainingConsent: false });
  await db.runAsync("INSERT INTO emergency_contacts (user_id, name, phone, relationship, updated_at) VALUES (817, 'Contacto', '123456', 'Amigo', 1)");
  await markAccountDeletion(817);
  await eraseLocalAccountData(817);
  expect(await db.getFirstAsync("SELECT * FROM emergency_contacts WHERE user_id = 817")).toBeNull();
  expect(await db.getFirstAsync("SELECT * FROM user_privacy_preferences WHERE id = 817")).toBeNull();
});

test("an explicit password rejection leaves the active account usable", async () => {
  await login(818);
  jest.spyOn(api, "deleteAccount").mockRejectedValue(new api.ApiError("Contraseña incorrecta", 401, "INVALID_PASSWORD"));
  await expect(deleteCurrentAccount("incorrecta")).rejects.toThrow("incorrecta");
  expect(await isAccountDeletionPending(818)).toBe(false);
  expect((await getAuthSession())?.user.id).toBe(818);
});

test("a remote deletion response erases an idle installation even without queued operations", async () => {
  await login(819);
  await db.runAsync("INSERT INTO sessions (user_id, started_at) VALUES (819, 1)");
  jest.spyOn(global, "fetch").mockResolvedValue({ ok: false, status: 401, json: async () => ({ code: "ACCOUNT_DELETED", message: "Cuenta eliminada" }) } as Response);
  await expect(api.getProfile("privacy-819")).rejects.toThrow("eliminada");
  expect(await getAuthSession()).toBeNull();
  expect(await db.getAllAsync("SELECT * FROM sessions WHERE user_id = 819")).toEqual([]);
});

test("offline contract strips personal fields and rejects expired and undated reports", () => {
  const now = Date.now();
  const report = { id: 1, created_at: new Date(now).toISOString(), reporter_name: "Nombre", reporter_user_id: 99, accuracy_meters: 3 };
  const clean = sanitizeReports([report as never, { ...report, id: 2, expires_at: new Date(now - 1).toISOString() } as never, { id: 3 } as never], now);
  expect(clean).toHaveLength(1);
  expect(clean[0]).not.toHaveProperty("reporter_name");
  expect(clean[0]).not.toHaveProperty("reporter_user_id");
  expect(clean[0]).not.toHaveProperty("accuracy_meters");
});
