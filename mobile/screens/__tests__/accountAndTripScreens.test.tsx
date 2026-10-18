import "../../../testing/mobileSetup";
jest.mock("../../../services/api", () => ({ loginUser: jest.fn(), registerUser: jest.fn(), createTripPlan: jest.fn() }));
jest.mock("../../../services/authSession", () => ({ getAuthSession: jest.fn(), saveAuthSession: jest.fn().mockResolvedValue(undefined) }));
jest.mock("../../../services/accountLifecycle", () => ({ isAccountDeletionPending: jest.fn().mockResolvedValue(false) }));
jest.mock("../../../services/emergencyContact", () => ({ getEmergencyContact: jest.fn(), saveEmergencyContact: jest.fn().mockResolvedValue(undefined) }));
jest.mock("../../../services/experienceProfile", () => ({ ...jest.requireActual("../../../services/experienceProfile"), getExperienceProfile: jest.fn(), saveExperienceProfile: jest.fn().mockResolvedValue(undefined), skipExperienceProfile: jest.fn().mockResolvedValue(undefined) }));
jest.mock("../../../services/tripPlans", () => ({ getSavedTripPlans: jest.fn(), refreshTripPlans: jest.fn(), saveTripPlanLocally: jest.fn().mockResolvedValue(undefined) }));
jest.mock("../../../services/departureMessages", () => ({ ...jest.requireActual("../../../services/departureMessages"), getDepartureMessage: jest.fn(), invalidateDepartureMessage: jest.fn().mockResolvedValue(undefined), sendDeparturePlanSms: jest.fn() }));
jest.mock("../../../services/testingMode", () => ({ isTestingLocationActive: jest.fn().mockResolvedValue(false) }));
jest.mock("../../../services/trailRepository", () => ({ getTrailById: jest.fn() }));
jest.mock("../../../services/syncQueue", () => ({ enqueueUnique: jest.fn().mockResolvedValue(1), runSync: jest.fn().mockResolvedValue({ processed: 1 }) }));
jest.mock("expo-network", () => ({ getNetworkStateAsync: jest.fn().mockResolvedValue({ isConnected: false }) }));
import { TextInput } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { mount, act, press, text } from "../../../testing/mobileHarness";
import { trail } from "../../../testing/fixtures";
import * as api from "../../../services/api";
import * as auth from "../../../services/authSession";
import * as contact from "../../../services/emergencyContact";
import * as experience from "../../../services/experienceProfile";
import * as plans from "../../../services/tripPlans";
import * as departure from "../../../services/departureMessages";
import { isTestingLocationActive } from "../../../services/testingMode";
import { isAccountDeletionPending } from "../../../services/accountLifecycle";
import { getTrailById } from "../../../services/trailRepository";
import { enqueueUnique } from "../../../services/syncQueue";
import Login from "../LoginScreen";
import Contact from "../SafetyContactScreen";
import Experience from "../ExperienceOnboardingScreen";
import Trip from "../TripPlanScreen";
const user = { id: 31, name: "Ana", email: "ana@example.test" }, session = { token: "session", user };
const person = { name: "Contacto", phone: "+5491112345678", relationship: "Familia" };
const plan = { id: 3, user_id: 31, trail_id: 7, status: "active", expected_return_at: "2026-10-17T20:00:00Z", grace_minutes: 30, contact_name: person.name, contact_phone: person.phone };
const fill = async (tree: any, label: string, value: string) => act(async () => tree.root.findAllByType(TextInput).find((node: any) => node.props.accessibilityLabel === label).props.onChangeText(value));
beforeEach(() => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "7", mode: "edit", returnTo: "trail-start" }); (router.canGoBack as jest.Mock).mockReturnValue(true);
  (api.loginUser as jest.Mock).mockResolvedValue(session); (api.registerUser as jest.Mock).mockResolvedValue(session); (auth.getAuthSession as jest.Mock).mockResolvedValue(session);
  (isAccountDeletionPending as jest.Mock).mockResolvedValue(false); (isTestingLocationActive as jest.Mock).mockResolvedValue(false);
  (contact.getEmergencyContact as jest.Mock).mockResolvedValue(person); (contact.saveEmergencyContact as jest.Mock).mockResolvedValue(undefined);
  (experience.getExperienceProfile as jest.Mock).mockResolvedValue({ completed: false });
  (plans.getSavedTripPlans as jest.Mock).mockResolvedValue([]); (plans.refreshTripPlans as jest.Mock).mockResolvedValue([]);
  (departure.getDepartureMessage as jest.Mock).mockResolvedValue(null); (departure.sendDeparturePlanSms as jest.Mock).mockResolvedValue({ status: "confirmed" });
  (getTrailById as jest.Mock).mockResolvedValue(trail); (api.createTripPlan as jest.Mock).mockResolvedValue(plan);
});
test("login validates required fields, preserves a failed attempt and authenticates the entered account", async () => {
  const tree = await mount(Login);
  await expect(press(tree, "Iniciar sesion")).rejects.toThrow("disabled"); expect(api.loginUser).not.toHaveBeenCalled();
  await fill(tree, "Email", user.email); await fill(tree, "Contrasena", "password-test");
  await press(tree, "Mostrar contrasena"); expect(tree.root.findAllByType(TextInput).find((node: any) => node.props.accessibilityLabel === "Contrasena").props.secureTextEntry).toBe(false);
  (api.loginUser as jest.Mock).mockRejectedValueOnce(new Error("Credenciales inválidas")); await press(tree, "Iniciar sesion"); expect(text(tree)).toContain("Credenciales inválidas");
  await press(tree, "Iniciar sesion"); expect(api.loginUser).toHaveBeenLastCalledWith(user.email, "password-test"); expect(auth.saveAuthSession).toHaveBeenCalledWith(session, { deletionRetryLogin: true }); expect(router.replace).toHaveBeenCalledWith("/inicio");
});
test("registration requires terms acceptance independently of physiological or analytics choices", async () => {
  const tree = await mount(Login); await press(tree, "Crear una cuenta nueva");
  await fill(tree, "Nombre", "Ana"); await fill(tree, "Email", user.email); await fill(tree, "Contrasena", "password-test");
  await expect(press(tree, "Crear cuenta")).rejects.toThrow("disabled");
  const checkbox = tree.root.findAll((node: any) => node.props.accessibilityRole === "checkbox" && typeof node.props.onPress === "function")[0];
  await act(async () => checkbox.props.onPress()); await press(tree, "Crear cuenta");
  expect(api.registerUser).toHaveBeenCalledWith("Ana", user.email, "password-test", "2026-10-16"); expect(router.replace).toHaveBeenCalledWith("/onboarding-experiencia");
});
test("a fresh login for pending deletion returns to the profile instead of resuming uploads", async () => {
  (isAccountDeletionPending as jest.Mock).mockResolvedValue(true); const tree = await mount(Login);
  await fill(tree, "Email", user.email); await fill(tree, "Contrasena", "password-test"); await press(tree, "Iniciar sesion"); expect(router.replace).toHaveBeenCalledWith("/perfil");
});
test("emergency contact can be edited offline and is saved with all entered values", async () => {
  const tree = await mount(Contact); expect(text(tree)).toContain("localmente");
  const inputs = tree.root.findAllByType(TextInput); await act(async () => inputs[0].props.onChangeText("Contacto actualizado"));
  await press(tree, "Guardar contacto"); expect(contact.saveEmergencyContact).toHaveBeenCalledWith({ ...person, name: "Contacto actualizado" }); expect(router.back).toHaveBeenCalled();
});
test("an incomplete or failed contact save never returns as though it succeeded", async () => {
  (contact.getEmergencyContact as jest.Mock).mockResolvedValue(null); const tree = await mount(Contact);
  await press(tree, "Guardar contacto"); expect(text(tree)).toContain("Completa nombre"); expect(contact.saveEmergencyContact).not.toHaveBeenCalled();
  const inputs = tree.root.findAllByType(TextInput); await act(async () => { inputs[0].props.onChangeText(person.name); inputs[1].props.onChangeText(person.phone); inputs[2].props.onChangeText(person.relationship); });
  (contact.saveEmergencyContact as jest.Mock).mockRejectedValueOnce(new Error("storage")); await press(tree, "Guardar contacto"); expect(text(tree)).toContain("No pudimos guardar"); expect(router.back).not.toHaveBeenCalled();
});
test("experience answers must be selected before advancing and are saved only at the last step", async () => {
  const tree = await mount(Experience); await press(tree, "Continuar"); expect(text(tree)).toContain("Que experiencia");
  for (const answer of ["Estoy empezando", "Moderada", "Hasta 5 km", "Simple y senalizado"]) { await press(tree, answer); await press(tree, "Continuar"); }
  expect(experience.saveExperienceProfile).not.toHaveBeenCalled(); await press(tree, "Prefiero poco desnivel"); await press(tree, "Guardar perfil");
  expect(experience.saveExperienceProfile).toHaveBeenCalledWith(expect.objectContaining({ experience: "baja_experiencia", altitude: "baja_altitud" })); expect(router.replace).toHaveBeenCalledWith("/inicio");
});
test("experience setup can be postponed without saving invented answers", async () => {
  const tree = await mount(Experience); await press(tree, "Omitir y hacerlo mas tarde"); expect(experience.skipExperienceProfile).toHaveBeenCalled(); expect(experience.saveExperienceProfile).not.toHaveBeenCalled();
});

test("recommendation entry requires completing the profile and returns to the recommendation survey after saving", async () => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ returnTo: "recommendation" });
  const tree = await mount(Experience);
  expect(text(tree)).not.toContain("Omitir y hacerlo mas tarde");
  expect(router.replace).not.toHaveBeenCalled();
  for (const answer of ["Estoy empezando", "Moderada", "Hasta 5 km", "Simple y senalizado"]) { await press(tree, answer); await press(tree, "Continuar"); }
  expect(router.replace).not.toHaveBeenCalled();
  await press(tree, "Prefiero poco desnivel"); await press(tree, "Guardar perfil");
  expect(experience.saveExperienceProfile).toHaveBeenCalled();
  expect(experience.skipExperienceProfile).not.toHaveBeenCalled();
  expect(router.replace).toHaveBeenCalledWith("/descubri-tu-sendero");
});

test("an already completed profile returns immediately to the requested recommendation screen", async () => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ returnTo: "recommendation" });
  (experience.getExperienceProfile as jest.Mock).mockResolvedValue({ completed: true, skipped: false, level: "intermedio" });
  await mount(Experience);
  expect(router.replace).toHaveBeenCalledWith("/descubri-tu-sendero");
});

test("cancelling required profile setup returns home without marking it completed or skipped", async () => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ returnTo: "recommendation" });
  const tree = await mount(Experience); await press(tree, "Volver al inicio");
  expect(router.replace).toHaveBeenCalledWith("/inicio");
  expect(experience.saveExperienceProfile).not.toHaveBeenCalled();
  expect(experience.skipExperienceProfile).not.toHaveBeenCalled();
});
test("trip registration validates deadlines and stores the same idempotent request when retrying", async () => {
  const tree = await mount(Trip); await fill(tree, "Horas hasta el regreso", "0"); await press(tree, "Registrar aviso por atraso"); expect(text(tree)).toContain("72 horas"); expect(api.createTripPlan).not.toHaveBeenCalled();
  await fill(tree, "Horas hasta el regreso", "2"); (api.createTripPlan as jest.Mock).mockRejectedValueOnce(new Error("respuesta perdida"));
  await press(tree, "Registrar aviso por atraso"); expect(text(tree)).toContain("respuesta perdida"); await press(tree, "Registrar aviso por atraso");
  expect((api.createTripPlan as jest.Mock).mock.calls[0][0]).toEqual((api.createTripPlan as jest.Mock).mock.calls[1][0]); expect(plans.saveTripPlanLocally).toHaveBeenCalledWith(plan); expect(text(tree)).toContain("Plan registrado");
});
test("sharing a plan confirms only the SMS action, and testing mode disables external actions", async () => {
  const tree = await mount(Trip); await press(tree, "Enviar plan por SMS"); expect(departure.sendDeparturePlanSms).toHaveBeenCalledWith(expect.objectContaining({ trailId: 7, contactPhone: person.phone }), expect.any(Function)); expect(text(tree)).toContain("no confirma");
  (isTestingLocationActive as jest.Mock).mockResolvedValue(true); const testing = await mount(Trip); await expect(press(testing, "Registrar aviso por atraso")).rejects.toThrow("disabled");
});
test("an offline check-in stays pending until the server acknowledges it", async () => {
  (plans.getSavedTripPlans as jest.Mock).mockResolvedValue([plan]); (plans.refreshTripPlans as jest.Mock).mockRejectedValue(new Error("offline"));
  const tree = await mount(Trip); await press(tree, "Ya regresé: confirmar"); expect(enqueueUnique).toHaveBeenCalledWith("trip_check_in", { planId: 3, status: "checked_in" }, "trip-close:3"); expect(text(tree)).toContain("Cierre pendiente de confirmar");
});
test("a successful server cancellation is shown separately from pending or delivered notifications", async () => {
  (plans.getSavedTripPlans as jest.Mock).mockResolvedValue([plan]); (plans.refreshTripPlans as jest.Mock).mockResolvedValueOnce([plan]).mockResolvedValue([{ ...plan, status: "cancelled" }]);
  const tree = await mount(Trip); await press(tree, "Cancelar plan de salida"); expect(text(tree)).toContain("Plan cancelado"); expect(text(tree)).toContain("servidor confirmó");
});
