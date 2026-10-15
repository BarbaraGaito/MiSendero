import { db, initDB } from "../../database/database";
import { saveAuthSession } from "../authSession";
import { getPrivacyPreferences, savePrivacyPreferences } from "../privacyConsent";
import { getExperienceProfile, saveExperienceProfile } from "../experienceProfile";
import { getAppPreferences, saveAppPreferences } from "../appPreferences";
import { saveWearableConnection, saveWearableMetricSample, getLatestWearableMetricSample } from "../wearableMetrics";
const login = (id: number) => saveAuthSession({ token: `test-${id}`, user: { id, name: "Test", email: `${id}@example.test` } });
beforeAll(() => initDB());

test("consent and profiles do not carry over to another account, and revocation only erases its owner", async () => {
  await login(201);
  await savePrivacyPreferences({ sensitiveDataConsent: true, analyticsTrainingConsent: true });
  await saveExperienceProfile({ experience: "alta", duration: "larga", trail: "tecnico" });
  await saveAppPreferences({ distanceUnit: "mi", notificationsEnabled: false, batterySaverEnabled: true, externalSensorLinked: false });
  await saveWearableConnection("android_health_connect", true, true);
  await saveWearableMetricSample({ provider: "android_health_connect", heartRateBpm: 100, steps: null, activeEnergyKcal: null, speedKmh: 3, oxygenSaturation: 97, recordedAt: Date.now() });
  await login(202);
  expect((await getPrivacyPreferences()).sensitiveDataConsent).toBe(false);
  expect((await getExperienceProfile()).completed).toBe(false);
  expect((await getAppPreferences()).distanceUnit).toBe("km");
  await savePrivacyPreferences({ sensitiveDataConsent: false, analyticsTrainingConsent: false });
  await login(201);
  expect((await getPrivacyPreferences()).sensitiveDataConsent).toBe(true);
  expect((await getAppPreferences()).distanceUnit).toBe("mi");
  expect((await getLatestWearableMetricSample())?.heartRateBpm).toBe(100);
  await savePrivacyPreferences({ sensitiveDataConsent: false, analyticsTrainingConsent: false });
  expect(await getLatestWearableMetricSample()).toBeNull();
});
