import "../../../testing/mobileSetup";
jest.mock("../../../services/trailAssistant", () => ({
  findRecommendedTrail: jest.fn(), getRecommendationExperience: jest.fn(),
  ExperienceProfileRequiredError: class extends Error {},
}));
jest.mock("expo-network", () => ({ useNetworkState: jest.fn() }));
import { useNetworkState } from "expo-network";
import { TextInput, Image } from "react-native";
import { router } from "expo-router";
import { mount, press, text, act } from "../../../testing/mobileHarness";
import { ExperienceProfileRequiredError, findRecommendedTrail, getRecommendationExperience } from "../../../services/trailAssistant";
import Discover from "../DiscoverTrailScreen";
jest.setTimeout(15000);
const recommendation = {
  trailId: 22, name: "Mirador de las Aguilas - El Chalten", location: "Santa Cruz", imageUrl: "https://example.com/trail.jpg",
  trailTypes: ["lagos", "miradores"], difficulty: "facil", duration: "2 h", durationMinutes: 120,
  routeType: "out_and_back", distanceKm: 4, description: "Vista al lago Viedma.",
  explanation: "Combina lagos y miradores en el destino que elegiste.", sources: [], checkedAt: "2026-10-11",
};
const success = { status: "ok", message: "¡Encontramos un sendero para vos!", recommendation };
beforeEach(() => {
  (getRecommendationExperience as jest.Mock).mockResolvedValue("principiante");
  (findRecommendedTrail as jest.Mock).mockResolvedValue(success);
  (useNetworkState as jest.Mock).mockReturnValue({ isConnected: true, isInternetReachable: true });
});
async function fill(tree: any) {
  await act(async () => tree.root.findByType(TextInput).props.onChangeText("El Chaltén"));
  await press(tree, "Continuar"); await press(tree, "🏞️ Lagos o lagunas");
  await press(tree, "Continuar"); await press(tree, "Entre 1 y 2 horas");
  await press(tree, "Continuar"); await press(tree, "Fácil");
}
test("one question per stage, retained answers and one final recommendation with no free chat", async () => {
  const tree = await mount(Discover);
  expect(text(tree)).toContain("¿A dónde querés ir?"); expect(text(tree)).not.toContain("¿Qué dificultad preferís?");
  const next = tree.root.findAll((n: any) => n.props.label === "Continuar")[0]; expect(next.props.disabled).toBe(true);
  await fill(tree);
  await press(tree, "Anterior"); expect(text(tree)).toContain("¿Cuánto tiempo querés caminar?");
  const duration = tree.root.findAll((n: any) => n.props.accessibilityLabel === "Entre 1 y 2 horas")[0]; expect(duration.props.accessibilityState.checked).toBe(true);
  await press(tree, "Continuar"); await press(tree, "Encontrar mi sendero");
  expect(findRecommendedTrail).toHaveBeenCalledWith({ destination: "El Chaltén", trailTypes: ["lagos"], duration: "1-2", difficulty: "facil" });
  expect(text(tree)).toContain("¡Encontramos un sendero para vos!"); expect(text(tree)).toContain(recommendation.name);
  expect(tree.root.findAllByType(TextInput)).toHaveLength(0);
  await press(tree, "Ver sendero"); expect(router.push).toHaveBeenCalledWith({ pathname: "/trail-detail", params: { id: "22" } });
  await press(tree, "Buscar otro sendero"); expect(tree.root.findByType(TextInput).props.value).toBe("El Chaltén");
});
test("any experience is exclusive and multiple specific experiences are retained", async () => {
  const tree = await mount(Discover);
  await act(async () => tree.root.findByType(TextInput).props.onChangeText("Córdoba"));
  await press(tree, "Continuar"); await press(tree, "🌲 Bosques"); await press(tree, "⛰️ Montaña");
  await press(tree, "🥾 Cualquiera"); await press(tree, "💧 Cascadas");
  await press(tree, "Continuar"); await press(tree, "No tengo preferencia");
  await press(tree, "Continuar"); await press(tree, "Cualquiera"); await press(tree, "Encontrar mi sendero");
  expect(findRecommendedTrail).toHaveBeenCalledWith(expect.objectContaining({ trailTypes: ["cascadas"] }));
});
test("no results permits editing preferences and never offers a fabricated trail detail", async () => {
  (findRecommendedTrail as jest.Mock).mockResolvedValue({ status: "no_results", message: "No encontramos un sendero verificado", recommendation: null });
  const tree = await mount(Discover); await fill(tree); await press(tree, "Encontrar mi sendero");
  expect(text(tree)).toContain("No encontramos"); expect(text(tree)).not.toContain("Ver sendero");
  await press(tree, "Modificar respuestas"); expect(text(tree)).toContain("Paso 1 de 4");
});
test("loading blocks repeat submissions, then an offline error preserves answers for retry", async () => {
  let rejectRequest: (error: Error) => void = () => {};
  (findRecommendedTrail as jest.Mock).mockReturnValue(new Promise((_resolve, reject) => { rejectRequest = reject; }));
  const tree = await mount(Discover); await fill(tree); await press(tree, "Encontrar mi sendero");
  expect(text(tree)).toContain("Buscando el sendero ideal para vos...");
  expect(text(tree)).not.toContain("Encontrar mi sendero");
  await act(async () => rejectRequest(new Error("Necesitás Internet")));
  expect(text(tree)).toContain("Necesitás Internet"); expect(text(tree)).toContain("Paso 4 de 4");
  (findRecommendedTrail as jest.Mock).mockResolvedValue(success); await press(tree, "Encontrar mi sendero");
  expect(text(tree)).toContain(recommendation.name);
});
test("a broken representative image is hidden and point-to-point duration includes the return notice", async () => {
  (findRecommendedTrail as jest.Mock).mockResolvedValue({ ...success, recommendation: { ...recommendation, routeType: "point_to_point" } });
  const tree = await mount(Discover); await fill(tree); await press(tree, "Encontrar mi sendero");
  expect(text(tree)).toContain("solo ida"); expect(text(tree)).toContain("transporte de regreso");
  const photo = tree.root.findByType(Image); await act(async () => photo.props.onError());
  expect(tree.root.findAllByType(Image)).toHaveLength(0);
});

test("nearby alternatives disclose changed preferences on the single result card", async () => {
  (findRecommendedTrail as jest.Mock).mockResolvedValue({ ...success, message: "Encontramos una alternativa cercana a tus preferencias",
    recommendation: { ...recommendation, preferenceAdjustments: ["Dura aproximadamente 3 h, fuera del rango elegido.", "Su dificultad es menor que la seleccionada."] } });
  const tree = await mount(Discover); await fill(tree); await press(tree, "Encontrar mi sendero");
  expect(text(tree)).toContain("Te sugerimos una alternativa en este destino");
  expect(text(tree)).toContain("No encontramos un sendero que coincida con todo lo que elegiste");
  expect(tree.root.findAll((node: any) => node.props.accessibilityRole === "alert").length).toBeGreaterThan(0);
  expect(text(tree)).toContain("fuera del rango elegido");
  expect(text(tree)).toContain("menor que la seleccionada");
  expect(tree.root.findAllByType(TextInput)).toHaveLength(0);
  await press(tree, "Buscar otro sendero");
  expect(tree.root.findByType(TextInput).props.value).toBe("El Chaltén");
});
test("a catalog-only result never invents a verification date or return-trip duration", async () => {
  (findRecommendedTrail as jest.Mock).mockResolvedValue({ ...success, recommendation: { ...recommendation,
    checkedAt: null, sources: [], routeType: "unknown", catalogVerification: "catalog_only", durationScopeVerified: false,
    dataWarnings: ["No se documentó si el tiempo incluye el regreso."],
    preferenceAdjustments: ["La duración total debe confirmarse."] } });
  const tree = await mount(Discover); await fill(tree); await press(tree, "Encontrar mi sendero");
  expect(text(tree)).not.toContain("verificación externa pendiente");
  expect(text(tree)).not.toContain("Datos registrados en el catálogo de MiSendero");
  expect(text(tree)).not.toContain("Información de la ficha");
  expect(text(tree)).toContain("confirmar si incluye el regreso");
  expect(text(tree)).not.toContain("Datos del catálogo revisados el");
  expect(text(tree)).not.toContain("(ida y vuelta)");
});

test("the destination is free text and the survey ends at difficulty without repeating the profile", async () => {
  const tree = await mount(Discover);
  await act(async () => tree.root.findByType(TextInput).props.onChangeText("Atlantis"));
  expect(tree.root.findAll((n: any) => n.props.label === "Continuar")[0].props.disabled).toBe(false);
  expect(tree.root.findAll((n: any) => n.props.accessibilityRole === "radio")).toHaveLength(0);
  await fill(tree);
  expect(text(tree)).toContain("Paso 4 de 4");
  expect(text(tree)).not.toContain("Principiante");
  expect(text(tree)).not.toContain("¿Qué experiencia tenés");
  await press(tree, "Encontrar mi sendero");
  expect(findRecommendedTrail).toHaveBeenCalledWith(expect.not.objectContaining({ experience: expect.anything() }));
});

test("a missing profile redirects to profile setup before showing any survey inputs", async () => {
  (getRecommendationExperience as jest.Mock).mockRejectedValue(new ExperienceProfileRequiredError());
  const tree = await mount(Discover);
  expect(router.replace).toHaveBeenCalledWith({ pathname: "/onboarding-experiencia", params: { returnTo: "recommendation" } });
  expect(tree.root.findAllByType(TextInput)).toHaveLength(0);
  expect(findRecommendedTrail).not.toHaveBeenCalled();
});

test("profile storage errors can be retried without inventing an experience level", async () => {
  (getRecommendationExperience as jest.Mock).mockRejectedValueOnce(new Error("storage"));
  const tree = await mount(Discover);
  expect(text(tree)).toContain("No pudimos leer tu perfil");
  expect(router.replace).not.toHaveBeenCalled();
  expect(tree.root.findAllByType(TextInput)).toHaveLength(0);
  await press(tree, "Reintentar");
  expect(tree.root.findAllByType(TextInput)).toHaveLength(1);
});

test("clearing the profile after entering the survey redirects to setup on submission", async () => {
  (findRecommendedTrail as jest.Mock).mockRejectedValue(new ExperienceProfileRequiredError());
  const tree = await mount(Discover); await fill(tree); await press(tree, "Encontrar mi sendero");
  expect(router.replace).toHaveBeenCalledWith({ pathname: "/onboarding-experiencia", params: { returnTo: "recommendation" } });
  expect(text(tree)).not.toContain("¡Encontramos un sendero para vos!");
});

test("the Internet notice appears only offline and disappears on reconnection without losing answers", async () => {
  const tree = await mount(Discover);
  expect(text(tree)).not.toContain("Necesitás Internet para generar");
  await act(async () => tree.root.findByType(TextInput).props.onChangeText("El Chaltén"));
  (useNetworkState as jest.Mock).mockReturnValue({ isConnected: false, isInternetReachable: false });
  await act(async () => tree.update(require("react").createElement(Discover)));
  expect(text(tree)).toContain("Necesitás Internet para generar");
  (useNetworkState as jest.Mock).mockReturnValue({ isConnected: true, isInternetReachable: true });
  await act(async () => tree.update(require("react").createElement(Discover)));
  expect(text(tree)).not.toContain("Necesitás Internet para generar");
  expect(tree.root.findByType(TextInput).props.value).toBe("El Chaltén");
});
