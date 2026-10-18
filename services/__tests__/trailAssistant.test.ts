jest.mock("expo-network", () => ({ getNetworkStateAsync: jest.fn() }));
jest.mock("../authSession", () => ({ getAuthSession: jest.fn() }));
jest.mock("../experienceProfile", () => ({ getExperienceProfile: jest.fn() }));
jest.mock("../api", () => ({ recommendTrail: jest.fn(), getTrailRecommendationDestinations: jest.fn() }));
import * as Network from "expo-network";
import { getAuthSession } from "../authSession";
import { getExperienceProfile } from "../experienceProfile";
import { recommendTrail, getTrailRecommendationDestinations } from "../api";
import { ExperienceProfileRequiredError, findRecommendedTrail, getCoveredDestinations, TrailPreferences } from "../trailAssistant";
const preferences: TrailPreferences = { destination: "El Chaltén", trailTypes: ["lagos"], duration: "1-2", difficulty: "facil" };
const empty = { status: "no_results", message: "Sin resultados", recommendation: null };
test("catalog-only records are accepted only when the response discloses missing verification and time scope", async () => {
  const recommendation = { trailId: 1, name: "Sendero a Confluencia", location: "Mendoza", imageUrl: null, trailTypes: ["montaña"], difficulty: "moderada",
    duration: "4 a 5 h", durationMinutes: 300, routeType: "unknown", distanceKm: 14, description: "Datos de la ficha del catálogo.",
    explanation: "Sendero del destino elegido.", sources: [], checkedAt: null, catalogVerification: "catalog_only", durationScopeVerified: false,
    dataWarnings: ["Fuente y alcance del tiempo pendientes de documentación."] };
  (recommendTrail as jest.Mock).mockResolvedValue({ status: "ok", message: "Alternativa del destino", recommendation });
  expect((await findRecommendedTrail(preferences)).recommendation).toMatchObject({ checkedAt: null, routeType: "unknown" });
  for (const change of [{ dataWarnings: [] }, { dataWarnings: undefined }, { catalogVerification: "verified" }, { durationScopeVerified: true }]) {
    (recommendTrail as jest.Mock).mockResolvedValue({ status: "ok", message: "Alternativa", recommendation: { ...recommendation, ...change } });
    await expect(findRecommendedTrail(preferences)).rejects.toThrow("no es válida");
  }
});
beforeEach(() => {
  jest.clearAllMocks();
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: true, isInternetReachable: true });
  (getAuthSession as jest.Mock).mockResolvedValue({ token: "session", user: { id: 31 } });
  (getExperienceProfile as jest.Mock).mockResolvedValue({ completed: true, skipped: false, level: "principiante" });
  (recommendTrail as jest.Mock).mockResolvedValue(empty);
});
test("sends the survey with the authenticated account's saved profile and session", async () => {
  expect(await findRecommendedTrail(preferences)).toEqual(empty);
  expect(getExperienceProfile).toHaveBeenCalledWith(31);
  expect(recommendTrail).toHaveBeenCalledWith({ ...preferences, experience: "principiante" }, "session");
});

test.each(["principiante", "intermedio", "avanzado"])("uses the saved %s level, overriding caller-provided experience", async (level) => {
  (getExperienceProfile as jest.Mock).mockResolvedValue({ completed: true, skipped: false, level });
  await findRecommendedTrail({ ...preferences, experience: "avanzado" } as TrailPreferences);
  expect(recommendTrail).toHaveBeenCalledWith({ ...preferences, experience: level }, "session");
});

test("each search reloads the profile so edits and account changes take effect", async () => {
  await findRecommendedTrail(preferences);
  (getAuthSession as jest.Mock).mockResolvedValue({ token: "other", user: { id: 32 } });
  (getExperienceProfile as jest.Mock).mockResolvedValue({ completed: true, skipped: false, level: "intermedio" });
  await findRecommendedTrail(preferences);
  expect(getExperienceProfile).toHaveBeenLastCalledWith(32);
  expect(recommendTrail).toHaveBeenLastCalledWith({ ...preferences, experience: "intermedio" }, "other");
});

test.each([
  { completed: false, skipped: false, level: null },
  { completed: false, skipped: true, level: null },
  { completed: true, skipped: false, level: null },
  { completed: true, skipped: true, level: "avanzado" },
  { completed: true, skipped: false, level: "invalid" },
])("incomplete, skipped or invalid profiles require setup before calling the backend", async (profile) => {
  (getExperienceProfile as jest.Mock).mockResolvedValue(profile);
  await expect(findRecommendedTrail(preferences)).rejects.toBeInstanceOf(ExperienceProfileRequiredError);
  expect(recommendTrail).not.toHaveBeenCalled();
});

test("failed profile reads never default to an invented level or call the backend", async () => {
  (getExperienceProfile as jest.Mock).mockRejectedValue(new Error("storage"));
  await expect(findRecommendedTrail(preferences)).rejects.toThrow("storage");
  expect(recommendTrail).not.toHaveBeenCalled();
});
test.each([{ isConnected: false }, { isConnected: true, isInternetReachable: false }])("offline survey never queues or fabricates a recommendation", async (network) => {
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue(network);
  await expect(findRecommendedTrail(preferences)).rejects.toThrow("Necesitás Internet");
  expect(recommendTrail).not.toHaveBeenCalled();
});
test("missing login requires a session without calling the ranking service", async () => {
  (getAuthSession as jest.Mock).mockResolvedValue(null);
  await expect(findRecommendedTrail(preferences)).rejects.toThrow("Iniciá sesión");
  expect(recommendTrail).not.toHaveBeenCalled();
});

test("covered destinations use the existing session and never fabricate offline coverage", async () => {
  (getTrailRecommendationDestinations as jest.Mock).mockResolvedValue({ destinations: ["Córdoba", "Córdoba", "Bariloche"] });
  expect(await getCoveredDestinations()).toEqual(["Córdoba", "Bariloche"]);
  expect(getTrailRecommendationDestinations).toHaveBeenCalledWith("session");
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: false });
  expect(await getCoveredDestinations()).toEqual([]);
});

test("a malformed destination catalog cannot become selectable options", async () => {
  for (const value of [{ destinations: [1] }, { destinations: ["x".repeat(201)] }, null]) {
    (getTrailRecommendationDestinations as jest.Mock).mockResolvedValue(value);
    await expect(getCoveredDestinations()).rejects.toThrow("catálogo de destinos");
  }
});
test("a failed connectivity probe still allows an actual request", async () => {
  (Network.getNetworkStateAsync as jest.Mock).mockRejectedValue(new Error("probe"));
  expect(await findRecommendedTrail(preferences)).toEqual(empty);
});
test("an outdated server's 404 is not presented as a missing trekking route", async () => {
  (recommendTrail as jest.Mock).mockRejectedValue(Object.assign(new Error("Ruta no encontrada"), { status: 404 }));
  await expect(findRecommendedTrail(preferences)).rejects.toThrow("No pudimos acceder al servicio de recomendaciones");
});
test.each([null, {}, { ...empty, status: "chat" }, { ...empty, status: "ok" }, { ...empty, status: "ok", recommendation: { trailId: -1 } }, { ...empty, status: "ok", recommendation: { trailId: 22 } }])("invalid response never becomes a navigable recommendation", async (value) => {
  (recommendTrail as jest.Mock).mockResolvedValue(value);
  await expect(findRecommendedTrail(preferences)).rejects.toThrow("no es válida");
});
test("a fully validated trail can be displayed, while incomplete facts are rejected", async () => {
  const trail = { trailId: 22, name: "Mirador", location: "El Chaltén", imageUrl: null, trailTypes: ["lagos"],
    difficulty: "facil", duration: "2 h", durationMinutes: 120, routeType: "out_and_back", distanceKm: 4,
    description: "Vista al lago", explanation: "Coincide con tus preferencias.",
    sources: [{ title: "Ficha", url: "https://www.argentina.gob.ar/parquesnacionales" }], checkedAt: "2026-10-11" };
  (recommendTrail as jest.Mock).mockResolvedValue({ status: "ok", message: "Encontramos", recommendation: trail });
  expect((await findRecommendedTrail(preferences)).recommendation).toEqual(trail);
  (recommendTrail as jest.Mock).mockResolvedValue({ status: "ok", message: "Alternativa", recommendation: { ...trail, preferenceAdjustments: ["Duración fuera del rango elegido."] } });
  expect((await findRecommendedTrail(preferences)).recommendation?.preferenceAdjustments).toEqual(["Duración fuera del rango elegido."]);
  for (const change of [{ distanceKm: null }, { trailTypes: null }, { imageUrl: "javascript:alert(1)" }, { sources: [] }, { routeType: "invented" },
    { preferenceAdjustments: [] }, { preferenceAdjustments: [42] }, { preferenceAdjustments: ["x".repeat(301)] }, { preferenceAdjustments: Array(5).fill("Too many") }]) {
    (recommendTrail as jest.Mock).mockResolvedValue({ status: "ok", message: "Encontramos", recommendation: { ...trail, ...change } });
    await expect(findRecommendedTrail(preferences)).rejects.toThrow("no es válida");
  }
});
