jest.mock("expo-network", () => ({ getNetworkStateAsync: jest.fn() }));
jest.mock("../authSession", () => ({ getAuthSession: jest.fn() }));
jest.mock("../api", () => ({ recommendTrail: jest.fn(), getTrailRecommendationDestinations: jest.fn() }));
import * as Network from "expo-network";
import { getAuthSession } from "../authSession";
import { recommendTrail, getTrailRecommendationDestinations } from "../api";
import { findRecommendedTrail, getCoveredDestinations, TrailPreferences } from "../trailAssistant";
const preferences: TrailPreferences = { destination: "El Chaltén", trailTypes: ["lagos"], duration: "1-2", difficulty: "facil" };
const empty = { status: "no_results", message: "Sin resultados", recommendation: null };
beforeEach(() => {
  jest.clearAllMocks();
  (Network.getNetworkStateAsync as jest.Mock).mockResolvedValue({ isConnected: true, isInternetReachable: true });
  (getAuthSession as jest.Mock).mockResolvedValue({ token: "session" });
  (recommendTrail as jest.Mock).mockResolvedValue(empty);
});
test("sends exactly the survey and existing session to the backend", async () => {
  expect(await findRecommendedTrail(preferences)).toEqual(empty);
  expect(recommendTrail).toHaveBeenCalledWith(preferences, "session");
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
  for (const change of [{ distanceKm: null }, { trailTypes: null }, { imageUrl: "javascript:alert(1)" }, { sources: [] }, { routeType: "invented" }]) {
    (recommendTrail as jest.Mock).mockResolvedValue({ status: "ok", message: "Encontramos", recommendation: { ...trail, ...change } });
    await expect(findRecommendedTrail(preferences)).rejects.toThrow("no es válida");
  }
});
