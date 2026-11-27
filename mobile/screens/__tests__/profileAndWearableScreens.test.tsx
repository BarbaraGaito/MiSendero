import "../../../testing/mobileSetup";
jest.mock("../../../services/logoutSession", () => ({ logoutSession: async () => { await require("../../../services/authSession").clearAuthSession(); return { remoteRevoked: true }; } }));
jest.mock("../../../services/api", () => ({ getProfile: jest.fn(), accountDataPageUrl: "https://example.test/account" }));
jest.mock("../../../services/authSession", () => ({ getAuthSession: jest.fn(), saveAuthSession: jest.fn().mockResolvedValue(undefined), clearAuthSession: jest.fn().mockResolvedValue(undefined) }));
jest.mock("../../../services/deleteAccount", () => ({ deleteCurrentAccount: jest.fn() }));
jest.mock("../../../services/accountLifecycle", () => ({ isAccountDeletionPending: jest.fn() }));
jest.mock("../../../services/privacyConsent", () => ({ privacyNotices: { sensitiveDataConsent: "Datos fisiológicos", analyticsTrainingConsent: "Analítica" }, getPrivacyPreferences: jest.fn(), savePrivacyPreferences: jest.fn() }));
jest.mock("../../../services/appPreferences", () => ({ getAppPreferences: jest.fn(), saveAppPreferences: jest.fn() }));
jest.mock("../../../services/testingMode", () => ({ getTestingLocationMode: jest.fn(), saveTestingLocationMode: jest.fn() }));
jest.mock("../../../services/experienceProfile", () => ({ getExperienceProfile: jest.fn() }));
jest.mock("../../../services/emergencyContact", () => ({ getEmergencyContact: jest.fn() }));
jest.mock("../../../services/offlineMaps", () => ({ getOfflineMapsSummary: jest.fn() }));
jest.mock("../../../database/sessionsRepository", () => ({ getSessionsSummary: jest.fn() }));
jest.mock("../../../services/syncQueue", () => ({ getSyncSummary: jest.fn(), runSync: jest.fn(), discardExhaustedOperations: jest.fn() }));
jest.mock("../../../services/wearableMetrics", () => ({ getWearableProviderName: (provider: string) => provider, getWearableRuntimeStatus: jest.fn(), getRecentWearableMetricSamples: jest.fn(), getSimulatedWearableMetricSamples: jest.fn(), createDevelopmentMetricSequence: jest.fn(), createDevelopmentMetricSample: jest.fn(), linkNativeWearable: jest.fn(), linkNativeWearableProvider: jest.fn(), syncNativeWearableSampleWithStatus: jest.fn(), unlinkWearableConnection: jest.fn() }));
import { Alert, TextInput, Platform } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { mount, text, press, act } from "../../../testing/mobileHarness";
import { getProfile } from "../../../services/api";
import * as auth from "../../../services/authSession";
import { deleteCurrentAccount } from "../../../services/deleteAccount";
import { isAccountDeletionPending } from "../../../services/accountLifecycle";
import * as privacy from "../../../services/privacyConsent";
import * as preferences from "../../../services/appPreferences";
import * as testing from "../../../services/testingMode";
import { getExperienceProfile } from "../../../services/experienceProfile";
import { getEmergencyContact } from "../../../services/emergencyContact";
import { getOfflineMapsSummary } from "../../../services/offlineMaps";
import { getSessionsSummary } from "../../../database/sessionsRepository";
import * as queue from "../../../services/syncQueue";
import * as wearable from "../../../services/wearableMetrics";
import Profile from "../ProfileScreen";
import Wearable from "../WearableSettingsScreen";
const user = { id: 31, name: "Ana", email: "ana@example.test", role: "user" }, session = { token: "token", user };
const prefs = { notificationsEnabled: true, distanceUnit: "km", batterySaverEnabled: true, externalSensorLinked: false, updatedAt: null };
const choices = { sensitiveDataConsent: true, analyticsTrainingConsent: true, updatedAt: null };
const status = { status: "linked", displayName: "Sensor", connection: { linked: true, provider: "apple_healthkit" }, latestSample: null, prediction: null };
const sync = { pending: 1, syncing: 0, synced: 2, failed: 1, exhausted: 1, abandoned: 0 };
const sample = { id: 9, provider: "apple_healthkit", heartRateBpm: 95, speedKmh: 4, oxygenSaturation: 98, steps: 200, recordedAt: Date.UTC(2026, 9, 16, 10) };
beforeEach(() => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({});
  (router.canGoBack as jest.Mock).mockReturnValue(true);
  (auth.getAuthSession as jest.Mock).mockResolvedValue(session); (getProfile as jest.Mock).mockResolvedValue({ user }); (isAccountDeletionPending as jest.Mock).mockResolvedValue(false);
  (deleteCurrentAccount as jest.Mock).mockResolvedValue(undefined);
  (privacy.getPrivacyPreferences as jest.Mock).mockResolvedValue(choices); (privacy.savePrivacyPreferences as jest.Mock).mockResolvedValue(undefined);
  (preferences.getAppPreferences as jest.Mock).mockResolvedValue(prefs); (preferences.saveAppPreferences as jest.Mock).mockResolvedValue(undefined);
  (testing.getTestingLocationMode as jest.Mock).mockResolvedValue({ enabled: false, updatedAt: null }); (testing.saveTestingLocationMode as jest.Mock).mockResolvedValue(undefined);
  (getExperienceProfile as jest.Mock).mockResolvedValue({ completed: true, level: "Intermedio" }); (getEmergencyContact as jest.Mock).mockResolvedValue({ name: "Contacto" });
  (getSessionsSummary as jest.Mock).mockResolvedValue({ completedCount: 2, currentMonthCount: 1, totalDistance: 3000 }); (getOfflineMapsSummary as jest.Mock).mockResolvedValue({ count: 2, totalSizeMb: 1500 });
  (queue.getSyncSummary as jest.Mock).mockResolvedValue(sync); (queue.runSync as jest.Mock).mockResolvedValue({ processed: 1 }); (queue.discardExhaustedOperations as jest.Mock).mockResolvedValue(1);
  (wearable.getWearableRuntimeStatus as jest.Mock).mockResolvedValue(status); (wearable.getRecentWearableMetricSamples as jest.Mock).mockResolvedValue([]); (wearable.getSimulatedWearableMetricSamples as jest.Mock).mockResolvedValue([]);
  for (const method of [wearable.createDevelopmentMetricSequence, wearable.createDevelopmentMetricSample, wearable.unlinkWearableConnection]) (method as jest.Mock).mockResolvedValue(undefined);
  (wearable.linkNativeWearable as jest.Mock).mockResolvedValue(true); (wearable.linkNativeWearableProvider as jest.Mock).mockResolvedValue(true); (wearable.syncNativeWearableSampleWithStatus as jest.Mock).mockResolvedValue("saved");
});
const confirm = async (label: string) => {
  const buttons = (Alert.alert as jest.Mock).mock.calls.slice(-1)[0][2];
  await act(async () => { await buttons.find((button: any) => button.text === label).onPress(); });
};
test("profile displays account-scoped persistence, retries sync, and confirms discarded work explicitly", async () => {
  jest.spyOn(Alert, "alert").mockImplementation(() => {}); const tree = await mount(Profile); expect(text(tree)).toContain("Ana"); expect(text(tree)).toContain("1,5 GB"); expect(text(tree)).toContain("Con error");
  await press(tree, "Con error, reintentar"); expect(queue.runSync).toHaveBeenCalledTimes(2);
  await press(tree, "Descartar pendientes con error"); expect(queue.discardExhaustedOperations).not.toHaveBeenCalled(); await confirm("Descartar"); expect(queue.discardExhaustedOperations).toHaveBeenCalledTimes(1);
  await press(tree, "Mapas descargados"); expect(router.push).toHaveBeenLastCalledWith("/offline-mapas-descargados"); await press(tree, "Contacto de emergencia"); expect(router.push).toHaveBeenLastCalledWith("/contacto-seguridad");
}, 15000);
test("privacy controls revoke each purpose independently and report rejected persistence", async () => {
  const tree = await mount(Profile); await press(tree, "Usar datos sensibles"); expect(privacy.savePrivacyPreferences).toHaveBeenLastCalledWith({ sensitiveDataConsent: false, analyticsTrainingConsent: true });
  await press(tree, "Mejorar recomendaciones"); expect(privacy.savePrivacyPreferences).toHaveBeenLastCalledWith({ sensitiveDataConsent: true, analyticsTrainingConsent: false });
  (privacy.savePrivacyPreferences as jest.Mock).mockRejectedValueOnce(new Error("Decisión no confirmada")); await press(tree, "Usar datos sensibles"); expect(text(tree)).toContain("Decisión no confirmada");
});
test("preferences retain unrelated values, and testing location is available only to administrators", async () => {
  (testing.getTestingLocationMode as jest.Mock).mockResolvedValue({ enabled: true, updatedAt: null }); const regular = await mount(Profile); expect(testing.saveTestingLocationMode).toHaveBeenCalledWith(false); expect(text(regular)).not.toContain("Simular ubicacion en ruta");
  for (const [label, change] of [["Unidades", { distanceUnit: "mi" }], ["Notificaciones", { notificationsEnabled: false }], ["Modo ahorro de bateria", { batterySaverEnabled: false }]] as const) {
    await press(regular, label); const { updatedAt, ...rest } = prefs; expect(preferences.saveAppPreferences).toHaveBeenLastCalledWith({ ...rest, ...change });
  }
  (getProfile as jest.Mock).mockResolvedValue({ user: { ...user, role: "admin" } }); const admin = await mount(Profile);
  expect(text(admin)).not.toContain("Simular ubicacion en ruta");
  await press(admin, "Herramientas de administración");
  expect(text(admin)).toContain("Simular ubicacion en ruta"); await press(admin, "Simular ubicacion en ruta"); expect(testing.saveTestingLocationMode).toHaveBeenLastCalledWith(false);
});

test("admin evaluation compares macro F1 with its baseline and discloses missing held-out classes", async () => {
  (getProfile as jest.Mock).mockResolvedValue({ user: { ...user, role: "admin" } });
  const tree = await mount(Profile);
  await press(tree, "Herramientas de administración");
  const content = text(tree);
  expect(content).toContain("F1 de referencia");
  expect(content).toContain("Accuracy balanceada");
  expect(content).toContain("Clases evaluadas");
  expect(content).toContain("Fatiga Borg con calibración previa");
  expect(content).toContain("Prototipo Borg · fatigue-v1");
  expect(content).toContain("Prototipo altura · ams-v1");
  expect(content).toContain("Clasificación binaria deshabilitada");
  expect(content).toContain("test histórico reutilizado");
  expect(content).toContain("Accuracy de Borg previa");
  expect(content).toContain("F1 de Borg previa");
  expect(content).toContain("Requiere Borg previa y contexto de actividad");
  expect(content).toContain("Benchmark reutilizado");
  expect(content).toContain("Sin observaciones en test");
  expect(content).toContain("El test contiene un solo grupo");
  expect(content).toContain("no acredita validación para uso en campo");
});
test("profile redirects missing authentication and does not resurrect a pending deletion", async () => {
  (auth.getAuthSession as jest.Mock).mockResolvedValue(null); await mount(Profile); expect(router.replace).toHaveBeenCalledWith("/");
  (auth.getAuthSession as jest.Mock).mockResolvedValue(session); (isAccountDeletionPending as jest.Mock).mockResolvedValue(true); await mount(Profile); expect(auth.saveAuthSession).not.toHaveBeenCalled();
});
test("profile failure can be retried; account deletion requires confirmation and preserves uncertain errors", async () => {
  jest.spyOn(Alert, "alert").mockImplementation(() => {}); (getProfile as jest.Mock).mockRejectedValueOnce(new Error("offline")); const tree = await mount(Profile); expect(text(tree)).toContain("No pudimos cargar tu perfil"); await press(tree, "Reintentar"); expect(text(tree)).toContain("Ana");
  await expect(press(tree, "Eliminar cuenta")).rejects.toThrow("disabled"); await act(async () => tree.root.findByType(TextInput).props.onChangeText("clave"));
  await press(tree, "Eliminar cuenta"); expect(deleteCurrentAccount).not.toHaveBeenCalled(); (deleteCurrentAccount as jest.Mock).mockRejectedValueOnce(new Error("Respuesta perdida")); await confirm("Eliminar definitivamente"); expect(text(tree)).toContain("envíos quedan suspendidos"); expect(router.replace).not.toHaveBeenCalled();
  await press(tree, "Eliminar cuenta"); await confirm("Eliminar definitivamente"); expect(deleteCurrentAccount).toHaveBeenLastCalledWith("clave"); expect(router.replace).toHaveBeenLastCalledWith("/");
});
test("logout requires a separate confirmation before clearing the authenticated account", async () => {
  jest.spyOn(Alert, "alert").mockImplementation(() => {}); const tree = await mount(Profile); await press(tree, "Cerrar sesion"); expect(auth.clearAuthSession).not.toHaveBeenCalled(); await confirm("Cerrar sesion"); expect(auth.clearAuthSession).toHaveBeenCalledTimes(1); expect(router.replace).toHaveBeenCalledWith("/");
});
const providerButton = async (tree: any, name: string) => {
  const button = tree.root.findAll((node: any) => typeof node.props.onPress === "function" && node.findAllByType("Text").some((child: any) => child.children.join("") === name))[0];
  if (!button) throw new Error(`Provider ${name} missing`); await act(async () => { await button.props.onPress(); });
};
test("regular accounts see device controls without simulator or developer tools", async () => {
  const tree = await mount(Wearable);
  expect(text(tree)).toContain("Conectá tu reloj");
  expect(text(tree)).not.toContain("Pruebas del dispositivo");
  expect(text(tree)).not.toContain("Generar ventana simulada");
  expect(text(tree)).not.toContain("Simulador (pruebas)");
});
test("wearable linking checks consent before invoking any native bridge or simulator", async () => {
  (auth.getAuthSession as jest.Mock).mockResolvedValue({ ...session, user: { ...user, role: "admin" } });
  (wearable.getWearableRuntimeStatus as jest.Mock).mockResolvedValue({ ...status, status: "requires_consent" }); const tree = await mount(Wearable);
  await press(tree, "Pruebas del dispositivo");
  await providerButton(tree, "Apple Watch"); await press(tree, "Generar ventana simulada"); await press(tree, "Generar muestra simulada"); expect(text(tree)).toContain("Primero activa"); expect(wearable.linkNativeWearable).not.toHaveBeenCalled(); expect(wearable.createDevelopmentMetricSequence).not.toHaveBeenCalled(); expect(wearable.createDevelopmentMetricSample).not.toHaveBeenCalled();
  expect(router.push).toHaveBeenCalledWith({ pathname: "/perfil", params: { section: "privacy", returnTo: "wearable" } });
});

test("the consent notice links directly to the decision screen without granting permission", async () => {
  (wearable.getWearableRuntimeStatus as jest.Mock).mockResolvedValue({ ...status, status: "requires_consent" });
  const tree = await mount(Wearable);
  await press(tree, "Revisar consentimiento del reloj");
  expect(router.push).toHaveBeenCalledWith({ pathname: "/perfil", params: { section: "privacy", returnTo: "wearable" } });
  expect(privacy.savePrivacyPreferences).not.toHaveBeenCalled();
  expect(wearable.linkNativeWearable).not.toHaveBeenCalled();
});

test("the watch consent screen uses local preferences and returns to linking after an explicit independent grant", async () => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ section: "privacy", returnTo: "wearable" });
  (getProfile as jest.Mock).mockRejectedValue(new Error("sin conexión"));
  (privacy.getPrivacyPreferences as jest.Mock).mockResolvedValue({ sensitiveDataConsent: false, analyticsTrainingConsent: false, updatedAt: null });
  const tree = await mount(Profile);
  expect(text(tree)).toContain("Consentimiento del reloj");
  expect(text(tree)).toContain("Datos fisiológicos");
  expect(text(tree)).not.toContain("Mapas descargados");
  expect(getProfile).not.toHaveBeenCalled();
  expect(privacy.savePrivacyPreferences).not.toHaveBeenCalled();
  (privacy.getPrivacyPreferences as jest.Mock).mockResolvedValue({ sensitiveDataConsent: true, analyticsTrainingConsent: false, updatedAt: 1 });
  (wearable.getWearableRuntimeStatus as jest.Mock).mockResolvedValue({ ...status, status: "not_linked" });
  await press(tree, "Usar datos sensibles");
  expect(privacy.savePrivacyPreferences).toHaveBeenCalledWith({ sensitiveDataConsent: true, analyticsTrainingConsent: false });
  expect(text(tree)).toContain("Consentimiento activado");
  await press(tree, "Volver al reloj");
  expect(router.back).toHaveBeenCalled();
  const watch = await mount(Wearable);
  expect(text(watch)).not.toContain("Revisar consentimiento del reloj");
  await providerButton(watch, "Apple Watch");
  expect(wearable.linkNativeWearable).toHaveBeenCalledTimes(1);
});

test("failed consent is not shown as active and the return action supports a direct link without history", async () => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ section: "privacy", returnTo: "wearable" });
  (privacy.getPrivacyPreferences as jest.Mock).mockResolvedValue({ sensitiveDataConsent: false, analyticsTrainingConsent: false, updatedAt: null });
  const tree = await mount(Profile);
  (privacy.savePrivacyPreferences as jest.Mock).mockRejectedValueOnce(new Error("No se pudo guardar la decisión."));
  await press(tree, "Usar datos sensibles");
  expect(text(tree)).toContain("No se pudo guardar la decisión");
  expect(text(tree)).not.toContain("Consentimiento activado");
  (router.canGoBack as jest.Mock).mockReturnValue(false);
  await press(tree, "Volver al reloj");
  expect(router.replace).toHaveBeenCalledWith("/reloj-salud");
});

test("a sensor refresh failure does not hide a successfully saved consent", async () => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ section: "privacy", returnTo: "wearable" });
  (privacy.getPrivacyPreferences as jest.Mock).mockResolvedValue({ sensitiveDataConsent: false, analyticsTrainingConsent: false, updatedAt: null });
  const tree = await mount(Profile);
  (privacy.getPrivacyPreferences as jest.Mock).mockResolvedValue({ sensitiveDataConsent: true, analyticsTrainingConsent: false, updatedAt: 1 });
  (wearable.getWearableRuntimeStatus as jest.Mock).mockRejectedValueOnce(new Error("sensor unavailable"));
  await press(tree, "Usar datos sensibles");
  expect(text(tree)).toContain("Consentimiento activado");
  expect(text(tree)).not.toContain("No se pudo guardar");
});
test("each native provider is linked through its bridge; disconnect and unavailable builds stay explicit", async () => {
  const tree = await mount(Wearable); await providerButton(tree, "Apple Watch"); expect(wearable.linkNativeWearable).toHaveBeenCalled();
  await providerButton(tree, "Android"); expect(wearable.linkNativeWearableProvider).toHaveBeenLastCalledWith("android_health_connect"); await providerButton(tree, "Wear OS"); expect(wearable.linkNativeWearableProvider).toHaveBeenLastCalledWith("wear_os_health_services");
  (wearable.linkNativeWearable as jest.Mock).mockResolvedValue(false); await providerButton(tree, "Apple Watch"); expect(text(tree)).toContain("permisos de Salud");
  (wearable.linkNativeWearableProvider as jest.Mock).mockResolvedValue(false); await providerButton(tree, "Android"); expect(text(tree)).toContain(Platform.OS === "android" ? "Health Connect" : "teléfono Android");
  await press(tree, "Desvincular"); expect(wearable.unlinkWearableConnection).toHaveBeenCalledTimes(1);
});
test("simulations remain clearly separated from stored device history and handle failed generation", async () => {
  (auth.getAuthSession as jest.Mock).mockResolvedValue({ ...session, user: { ...user, role: "admin" } });
  (wearable.getRecentWearableMetricSamples as jest.Mock).mockResolvedValue([sample]); (wearable.getSimulatedWearableMetricSamples as jest.Mock).mockResolvedValue([{ ...sample, simulated: true }]);
  (wearable.getWearableRuntimeStatus as jest.Mock).mockResolvedValue({ ...status, latestSample: sample, prediction: { title: "Orientativo", level: "caution", method: "sensor_rules", coverage: "pulse_and_oxygen", readingAlert: "Revisar lectura", cardiacLoad: "media", factors: ["Pulso"], recommendedAction: "Descansar" } });
  const tree = await mount(Wearable); expect(text(tree)).toContain("Últimas lecturas");
  expect(text(tree)).not.toContain("Lecturas simuladas de esta sesion");
  await press(tree, "Pruebas del dispositivo");
  expect(text(tree)).toContain("Lecturas simuladas de esta sesion"); await press(tree, "Generar ventana simulada"); expect(wearable.createDevelopmentMetricSequence).toHaveBeenCalledWith("normal"); expect(text(tree)).toContain("solo en memoria");
  (wearable.createDevelopmentMetricSequence as jest.Mock).mockRejectedValueOnce(new Error("generation")); await press(tree, "Generar ventana simulada"); expect(text(tree)).toContain("No pudimos generar la ventana");
  await press(tree, "Generar muestra simulada"); expect(wearable.createDevelopmentMetricSample).toHaveBeenCalledWith("normal"); (wearable.createDevelopmentMetricSample as jest.Mock).mockRejectedValueOnce(new Error("generation")); await press(tree, "Generar muestra simulada"); expect(text(tree)).toContain("No pudimos generar la muestra");
});
test.each([["saved", "Metricas sincronizadas"], ["duplicate", "No hay lecturas nuevas"], ["permission_denied", "permisos de Salud"], ["not_linked", "Primero vincula"], ["unavailable", "Revisá sus permisos"], ["no_data", "lectura autorizada disponible"]])("native sync response %s is not confused with a saved sample", async (outcome, message) => {
  (wearable.syncNativeWearableSampleWithStatus as jest.Mock).mockResolvedValue(outcome); const tree = await mount(Wearable); await press(tree, "Sincronizar dispositivo"); expect(text(tree)).toContain(message);
});

test.each([150, null])("the wearable screen uses the actual sensor assessment with pulse %s and never shows Sin datos", async heartRateBpm => {
  const latestSample = { ...sample, heartRateBpm, oxygenSaturation: 92, recordedAt: Date.now() };
  const prediction = jest.requireActual("../../../services/wearableMetrics").predictWearableHealth(latestSample, 30);
  (wearable.getWearableRuntimeStatus as jest.Mock).mockResolvedValue({ ...status, latestSample, prediction });
  const tree = await mount(Wearable);
  expect(text(tree)).toContain("Avisos de lectura");
  expect(text(tree)).toContain("Revisar lectura");
  expect(text(tree)).not.toMatch(/Sin datos|sin_datos|falta un modelo validado/);
  expect(text(tree)).toContain("No mide fatiga");
  if (heartRateBpm === null) expect(text(tree)).not.toContain("Carga por pulso");
  else { expect(text(tree)).toContain("Carga por pulso"); expect(text(tree)).toContain("media"); }
});
