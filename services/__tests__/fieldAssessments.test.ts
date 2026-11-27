jest.mock("../nativeWearableBridge", () => ({ readNativeFieldSamples: jest.fn() }));
jest.mock("../routeSession", () => ({ getRouteSession: jest.fn(), getActiveRouteSession: jest.fn() }));
import { db, initDB } from "../../database/database";
import { saveAuthSession, clearAuthSession } from "../authSession";
import { savePrivacyPreferences } from "../privacyConsent";
import { saveWearableConnection } from "../wearableMetrics";
import { readNativeFieldSamples } from "../nativeWearableBridge";
import { getRouteSession, getActiveRouteSession } from "../routeSession";
import { getFieldSnapshot, saveBorgCheckin, evaluateMorningAms } from "../fieldAssessments";
import { applyLocalRetention } from "../../database/dataRetention";
import { eraseLocalAccountData } from "../accountLifecycle";
const now = new Date(2026, 10, 27, 8, 0).getTime(), start = now-600000;
const session = { user_id: 501, trail_id: 7, started_at: start, state: "paused", simulated: 0 };
const login = (id = 501) => saveAuthSession({ token: `field-${id}`, user: { id, name: "Field", email: `${id}@example.test` } });
const allow = () => savePrivacyPreferences({ sensitiveDataConsent: true, analyticsTrainingConsent: false });
const native = () => ({ provider: "apple_healthkit", heartRate: [0,15000,30000,45000,60000].map(offset => ({ value: 112, recordedAt: now-60000+offset })), oxygen: [{ value: 95, recordedAt: now }] });
const morning = (overrides = {}) => evaluateMorningAms({ trailId: 7, startedAt: start, restedOvernight: true, restingNow: true, beforeAscent: true, location: { coordinate: [0,0], accuracy: 5, timestamp: now, altitudeM: 3000, altitudeAccuracyM: 10 }, now, ...overrides });

beforeEach(async () => {
  jest.spyOn(Date, "now").mockReturnValue(now);
  await initDB();
  await login(); await allow(); await saveWearableConnection("apple_healthkit", true, true);
  await db.execAsync("DELETE FROM fatigue_checkins; DELETE FROM field_model_assessments; DELETE FROM account_deletion_state;");
  (getRouteSession as jest.Mock).mockResolvedValue(session);
  (getActiveRouteSession as jest.Mock).mockResolvedValue(session);
  (readNativeFieldSamples as jest.Mock).mockResolvedValue(native());
});
afterEach(() => { jest.restoreAllMocks(); jest.clearAllMocks(); });

test("self reports remain exact, causal and isolated by owner and session", async () => {
  expect((await getFieldSnapshot(7,start)).reminderDue).toBe(true);
  await saveBorgCheckin(7,start,3.5,now-300000);
  const result = await getFieldSnapshot(7,start);
  expect(result.checkins).toEqual([{ borg: 3.5, recordedAt: now-300000 }]);
  expect(result.fatigue.status).toBe("available");
  expect(result.reminderDue).toBe(false);
  await getFieldSnapshot(7,start);
  expect(await db.getAllAsync("SELECT id FROM field_model_assessments")).toHaveLength(1);
  await saveBorgCheckin(7,start,10);
  expect((await getFieldSnapshot(7,start)).fatigue).toEqual(result.fatigue);
  await login(502); await allow();
  expect((await getFieldSnapshot(7,0)).checkins).toEqual([]);
  expect((await getFieldSnapshot(8,start)).checkins).toEqual([]);
  await expect(saveBorgCheckin(7,start,11)).rejects.toThrow("entre 0 y 10");
  await expect(saveBorgCheckin(7,start,3,now+60000)).rejects.toThrow();
  await expect(saveBorgCheckin(7,0,3)).rejects.toThrow();
});

test("native gaps and disconnected or simulated providers abstain without inventing measurements", async () => {
  await saveBorgCheckin(7,start,3,now-300000);
  (readNativeFieldSamples as jest.Mock).mockResolvedValue(null);
  expect((await getFieldSnapshot(7,start)).fatigue.status).toBe("missing_inputs");
  await saveWearableConnection("apple_healthkit", false, false);
  (readNativeFieldSamples as jest.Mock).mockClear();
  expect((await getFieldSnapshot(7,start)).fatigue.status).toBe("missing_inputs");
  expect(readNativeFieldSamples).not.toHaveBeenCalled();
  (getRouteSession as jest.Mock).mockResolvedValue({ ...session, simulated: 1 });
  await expect(saveBorgCheckin(7,start,3)).rejects.toThrow("prueba");
  (getRouteSession as jest.Mock).mockResolvedValue(null);
  await expect(getFieldSnapshot(7,start)).rejects.toThrow();
});

test("morning control requires rest, pre-ascent context, measured absolute altitude and simultaneous native readings", async () => {
  expect(await morning()).toMatchObject({ status: "available", label: null, value: null, score: expect.any(Number) });
  expect(await morning({ beforeAscent: false })).toMatchObject({ status: "outside_scope" });
  expect(await morning({ now: now+8*3600000 })).toMatchObject({ status: "outside_scope" });
  expect(await morning({ location: null })).toMatchObject({ status: "missing_inputs" });
  expect(await morning({ location: { timestamp: now, altitudeM: 3000, altitudeAccuracyM: 60 } })).toMatchObject({ status: "missing_inputs" });
  (getActiveRouteSession as jest.Mock).mockResolvedValue({ ...session, state: "running" });
  expect(await morning()).toMatchObject({ status: "outside_scope" });
  (getActiveRouteSession as jest.Mock).mockResolvedValue({ ...session, simulated: 1 });
  expect(await morning()).toMatchObject({ status: "outside_scope" });
  (getActiveRouteSession as jest.Mock).mockResolvedValue(null);
  (readNativeFieldSamples as jest.Mock).mockResolvedValue({ ...native(), oxygen: [] });
  expect(await morning({ startedAt: 0 })).toMatchObject({ status: "missing_inputs" });
});

test("revocation removes only the owner's sensitive rows; seven-day retention and erasure cover both new stores", async () => {
  for (const owner of [501,502]) for (const timestamp of [now-8*86400000,now]) {
    await db.runAsync("INSERT INTO fatigue_checkins VALUES(?,?,7,?,3,?,?)",[`${owner}-${timestamp}`,owner,start,timestamp,timestamp]);
    await db.runAsync("INSERT INTO field_model_assessments VALUES(?,?,7,?,'fatigue','fixture',?,'{}',?)",[`${owner}-${timestamp}`,owner,start,`${timestamp}`,timestamp]);
  }
  await applyLocalRetention(now);
  expect(await db.getAllAsync("SELECT id FROM fatigue_checkins")).toHaveLength(2);
  expect(await db.getAllAsync("SELECT id FROM field_model_assessments")).toHaveLength(2);
  await savePrivacyPreferences({ sensitiveDataConsent: false, analyticsTrainingConsent: false });
  expect(await db.getAllAsync("SELECT user_id FROM fatigue_checkins")).toEqual([{ user_id: 502 }]);
  expect((await getFieldSnapshot(7,start)).enabled).toBe(false);
  await expect(saveBorgCheckin(7,start,3)).rejects.toThrow("consentimiento");
  await eraseLocalAccountData(502);
  expect(await db.getAllAsync("SELECT id FROM fatigue_checkins")).toEqual([]);
  expect(await db.getAllAsync("SELECT id FROM field_model_assessments")).toEqual([]);
});

test("account switches and consent revocation during sensor reads cannot commit health data", async () => {
  await saveBorgCheckin(7,start,3,now-300000);
  (readNativeFieldSamples as jest.Mock).mockImplementationOnce(async () => { await login(502); return native(); });
  await expect(getFieldSnapshot(7,start)).rejects.toThrow("sesión cambió");
  expect(await db.getAllAsync("SELECT id FROM field_model_assessments")).toEqual([]);
  await login();
  (readNativeFieldSamples as jest.Mock).mockImplementationOnce(async () => { await savePrivacyPreferences({ sensitiveDataConsent: false, analyticsTrainingConsent: false }); return native(); });
  await expect(getFieldSnapshot(7,start)).rejects.toThrow("permiso");
  expect(await db.getAllAsync("SELECT id FROM field_model_assessments")).toEqual([]);
  await clearAuthSession();
  expect((await getFieldSnapshot(7,start)).enabled).toBe(false);
});
