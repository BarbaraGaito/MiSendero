import "../../../testing/mobileSetup";
jest.mock("../../../database/database", () => ({ initDB: jest.fn().mockResolvedValue(undefined) }));
jest.mock("../../../services/trailRepository", () => ({ getTrails: jest.fn(), getTrailById: jest.fn(), getTrailReports: jest.fn(), getTrailWeather: jest.fn() }));
jest.mock("../../../services/offlineMaps", () => ({ getOfflineMaps: jest.fn(), deleteOfflineMap: jest.fn(), getVerifiedOfflineMapByTrailId: jest.fn(), saveOfflineTrailMap: jest.fn() }));
jest.mock("../../../database/sessionsRepository", () => ({ getRecentSessions: jest.fn(), getSessions: jest.fn(), getSessionsSummary: jest.fn(), getTrailRatingSummary: jest.fn(), getTrailReviews: jest.fn() }));
jest.mock("../../../services/favoriteTrails", () => ({ getFavoriteTrailIds: jest.fn(), isTrailFavorite: jest.fn(), setTrailFavorite: jest.fn() }));
jest.mock("../../../services/authSession", () => ({ getAuthSession: jest.fn() }));
jest.mock("../../../services/api", () => ({ getProfile: jest.fn() }));
jest.mock("../../../services/experienceProfile", () => ({ ...jest.requireActual("../../../services/experienceProfile"), getExperienceProfile: jest.fn() }));
jest.mock("../../../services/routeSession", () => ({ getActiveRouteSession: jest.fn().mockResolvedValue(null), subscribeRouteSession: jest.fn(() => jest.fn()) }));
jest.mock("../../../services/nationalParks", () => ({ ...jest.requireActual("../../../services/nationalParks"), getNationalParks: jest.fn(), getNationalPark: jest.fn() }));
jest.mock("expo-network", () => ({ getNetworkStateAsync: jest.fn().mockResolvedValue({ isConnected: false, isInternetReachable: false }) }));
import { router, useLocalSearchParams } from "expo-router";
import { TextInput, Image, Linking } from "react-native";
import { mount, text, press, act } from "../../../testing/mobileHarness";
import { trail, completed } from "../../../testing/fixtures";
import * as trails from "../../../services/trailRepository";
import * as maps from "../../../services/offlineMaps";
import * as history from "../../../database/sessionsRepository";
import * as favorites from "../../../services/favoriteTrails";
import * as auth from "../../../services/authSession";
import * as experience from "../../../services/experienceProfile";
import * as parks from "../../../services/nationalParks";
import Home from "../HomeScreen";
import Explore from "../ExploreRoutesScreen";
import Activities from "../ActivitiesScreen";
import History from "../HistoryScreen";
import Reviews from "../TrailReviewsScreen";
import Detail from "../TrailDetail";
import Attributions from "../AttributionsScreen";
import Offline from "../OfflineMapsScreen";
import Search from "../OfflineMapsSearchScreen";
import Parks from "../NationalParksScreen";
import Park from "../NationalParkDetailScreen";
const park = { ...require("../../../backend/src/data/nationalParks")[0], trails: [trail], live_status: { notices_url: "https://www.argentina.gob.ar/parquesnacionales", weather_url: "https://www.smn.gob.ar/alertas" } };
const savedMap = { id: 3, trailId: 7, trail, name: trail.name, sizeMb: 5, status: "disponible", downloadedTiles: 2, totalTiles: 2, verifiedAt: 1791626400000, updatedAt: 1791626400000, downloadedAt: 1791626400000, reports: [] };
beforeEach(() => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "7", slug: park.slug, trailId: "7" });
  (trails.getTrails as jest.Mock).mockResolvedValue([trail, { ...trail, id: 8, name: "Ruta exigente", difficulty: "Alta", distance_km: 12 }]);
  (trails.getTrailById as jest.Mock).mockResolvedValue(trail); (trails.getTrailReports as jest.Mock).mockResolvedValue([]); (trails.getTrailWeather as jest.Mock).mockResolvedValue(null);
  (maps.getOfflineMaps as jest.Mock).mockResolvedValue([savedMap]); (maps.deleteOfflineMap as jest.Mock).mockResolvedValue(true); (maps.getVerifiedOfflineMapByTrailId as jest.Mock).mockResolvedValue(null); (maps.saveOfflineTrailMap as jest.Mock).mockResolvedValue(savedMap);
  (history.getSessions as jest.Mock).mockResolvedValue([completed]); (history.getRecentSessions as jest.Mock).mockResolvedValue([completed, { ...completed, id: 2, ended_at: null, completion_status: "paused" }, { ...completed, id: 3, completion_status: "ended_early", route_progress_meters: 1500 }]);
  (history.getSessionsSummary as jest.Mock).mockResolvedValue({ totalDistance: 3000, completedCount: 1, currentMonthCount: 1 });
  (history.getTrailRatingSummary as jest.Mock).mockResolvedValue({ averageRating: 4.5, reviewCount: 2 }); (history.getTrailReviews as jest.Mock).mockResolvedValue([{ id: 1, rating: 4, reviewText: "Recorrido medido", reviewedAt: completed.started_at, startedAt: completed.started_at }]);
  (favorites.getFavoriteTrailIds as jest.Mock).mockResolvedValue([7]); (favorites.isTrailFavorite as jest.Mock).mockResolvedValue(false); (favorites.setTrailFavorite as jest.Mock).mockImplementation(async (_id, enabled) => enabled);
  (auth.getAuthSession as jest.Mock).mockResolvedValue({ token: "session", user: { id: 31, name: "Ana" } });
  (experience.getExperienceProfile as jest.Mock).mockResolvedValue({ completed: true, level: "principiante", answers: {} });
  (parks.getNationalParks as jest.Mock).mockResolvedValue({ data: [park], fromCache: true }); (parks.getNationalPark as jest.Mock).mockResolvedValue({ data: park, fromCache: true });
});
test("offline home uses the local account and recommendations, and opens the selected trail", async () => {
  const tree = await mount(Home); expect(text(tree)).toContain("Ana"); expect(text(tree)).toContain(trail.name);
  await press(tree, `Ver detalle de ${trail.name}`); expect(router.push).toHaveBeenCalledWith({ pathname: "/trail-detail", params: { id: "7" } });
});
test("home redirects a missing session and presents recoverable loading failures", async () => {
  (auth.getAuthSession as jest.Mock).mockResolvedValueOnce(null); await mount(Home); expect(router.replace).toHaveBeenCalledWith("/");
  (trails.getTrails as jest.Mock).mockRejectedValueOnce(new Error("cache unavailable")); const tree = await mount(Home);
  expect(text(tree)).toContain("No pudimos actualizar"); await press(tree, "Reintentar"); expect(text(tree)).toContain(trail.name);
});
test("exploration filters actual loaded routes by query and difficulty", async () => {
  const tree = await mount(Explore); expect(text(tree)).toContain(trail.name);
  const input = tree.root.findByType(TextInput);
  await act(async () => input.props.onChangeText("exigente")); expect(text(tree)).not.toContain(trail.name); expect(text(tree)).toContain("Ruta exigente");
  await act(async () => input.props.onChangeText("inexistente")); expect(text(tree)).toContain("Sin resultados");
});
test("activity cards distinguish pending, interrupted and completed outings and offer the local history", async () => {
  const tree = await mount(Activities); const content = text(tree);
  for (const status of ["Pendiente", "Interrumpida", "Completada"]) expect(content).toContain(status);
  await press(tree, "Ver historial local"); expect(router.push).toHaveBeenCalledWith("/history");
});
test("activity and history errors remain visible instead of fabricating saved outings", async () => {
  (history.getRecentSessions as jest.Mock).mockRejectedValue(new Error("sqlite")); expect(text(await mount(Activities))).toContain("No pudimos cargar tus actividades");
  (history.getSessions as jest.Mock).mockRejectedValue(new Error("sqlite")); expect(text(await mount(History))).toContain("No pudimos cargar el historial local");
});
test("local history and reviews display persisted facts and their absence explicitly", async () => {
  (history.getSessions as jest.Mock).mockResolvedValue([completed, { ...completed, id: 2, duration: 65, completion_status: "ended_early", route_progress_meters: 1500 }]);
  const tree = await mount(History); expect(text(tree)).toContain("50"); expect(text(tree)).toContain("Interrumpida");
  expect(text(await mount(Reviews))).toContain("Recorrido medido");
  (history.getSessions as jest.Mock).mockResolvedValue([]); expect(text(await mount(History))).toContain("Todavia no hay recorridos");
  (history.getTrailReviews as jest.Mock).mockResolvedValue([]); (history.getTrailRatingSummary as jest.Mock).mockResolvedValue(null); expect(text(await mount(Reviews))).toContain("Todavia no hay opiniones");
});
test("trail details toggle a favorite and download a verified local copy", async () => {
  const tree = await mount(Detail); expect(text(tree)).toContain(trail.name);
  const favorite = tree.root.findAll((node: any) => typeof node.props.onPress === "function" && /favorit/i.test(node.props.accessibilityLabel || ""))[0];
  expect(favorite).toBeDefined(); await act(async () => favorite.props.onPress()); expect(favorites.setTrailFavorite).toHaveBeenCalledWith(7, true);
  const download = tree.root.findAll((node: any) => typeof node.props.onPress === "function" && /Descargar mapa/i.test(node.props.label || ""))[0];
  expect(download).toBeDefined(); await act(async () => download.props.onPress()); expect(maps.saveOfflineTrailMap).toHaveBeenCalled(); expect(text(tree)).toContain("Mapa básico y recorrido descargados");
});
test("a documented circuit without GPS shows its facts and source without offering a map download", async () => {
  const entry = require("../../../backend/src/data/catalogExpansion20261017").trails.find((item: any) => item.provenance.catalog_key === "moreno-belgrano-chico");
  (trails.getTrailById as jest.Mock).mockResolvedValue({ ...trail, ...entry, id: 7, elevation: null, route_coordinates: null });
  const tree = await mount(Detail);
  const content = text(tree);
  expect(content).toContain("Circuito completo");
  expect(content).toContain("Consultá el recorrido");
  expect(content).toContain("Fuentes del recorrido");
  expect(content).not.toContain("Solo ida; coordinar el regreso");
  expect(tree.root.findAll((node: any) => ["Ver ruta", "Descargar mapa"].includes(node.props.label))).toHaveLength(0);
});
test("the enriched circuit displays its real image, source and map actions without the pending-GPS notice", async () => {
  const entry = require("../../../backend/src/data/catalogExpansion20261017").trails.find((item: any) => item.provenance.catalog_key === "moreno-belgrano-chico");
  (trails.getTrailById as jest.Mock).mockResolvedValue({ ...trail, ...entry, id: 7, elevation: null, route_coordinates: JSON.stringify(entry.route_coordinates) });
  const tree = await mount(Detail);
  expect(text(tree)).not.toContain("Traza GPS pendiente");
  expect(text(tree)).toContain("Créditos cartográficos");
  expect(text(tree)).not.toContain(entry.provenance.photo.context);
  expect(text(tree)).not.toContain(entry.provenance.mapping.license);
  await press(tree, "Créditos cartográficos");
  expect(router.push).toHaveBeenCalledWith({ pathname: "/atribuciones", params: { trailId: "7" } });
  const credits = await mount(Attributions);
  expect(text(credits)).toContain(entry.provenance.mapping.license);
  expect(text(credits)).toContain(entry.provenance.photo.author);
  expect(text(credits)).toContain(entry.provenance.photo.context);
  expect(tree.root.findAll((node: any) => node.props.label === "Ver ruta").length).toBeGreaterThan(0);
  expect(tree.root.findAll((node: any) => node.props.source?.uri === entry.image_url).length).toBeGreaterThan(0);
});
test("a reference map keeps the normal trail card without an incomplete-route banner", async () => {
  const entry = require("../../../backend/src/data/catalogExpansion20261017").trails.find((item: any) => item.provenance.catalog_key === "quijadas-farallones");
  (trails.getTrailById as jest.Mock).mockResolvedValue({ ...trail, ...entry, id: 7, elevation: null, route_coordinates: JSON.stringify(entry.route_coordinates) });
  const tree = await mount(Detail);
  expect(text(tree)).not.toContain("Mapa de referencia parcial");
  expect(text(tree)).not.toContain("Traza GPS pendiente");
  expect(tree.root.findAll((node: any) => node.props.label === "Ver ruta").length).toBeGreaterThan(0);
});
test("a missing trail and a failed download never claim offline availability", async () => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "invalid" }); expect(text(await mount(Detail))).toContain("No se encontro");
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "7" }); (maps.saveOfflineTrailMap as jest.Mock).mockRejectedValue(new Error("provider-not-configured"));
  const tree = await mount(Detail); const download = tree.root.findAll((node: any) => typeof node.props.onPress === "function" && /Descargar mapa/i.test(node.props.label || ""))[0];
  await act(async () => download.props.onPress()); expect(text(tree)).not.toContain("Mapa descargado");
});
test("deleting a local map reloads actual storage and surfaces a failed deletion", async () => {
  const tree = await mount(Offline); expect(text(tree)).toContain(trail.name);
  (maps.getOfflineMaps as jest.Mock).mockResolvedValue([]); await press(tree, "Eliminar"); expect(maps.deleteOfflineMap).toHaveBeenCalledWith(3); expect(text(tree)).toContain("No hay mapas descargados");
  (maps.getOfflineMaps as jest.Mock).mockResolvedValue([savedMap]); const failing = await mount(Offline);
  (maps.deleteOfflineMap as jest.Mock).mockRejectedValue(new Error("filesystem")); await press(failing, "Eliminar"); expect(text(failing)).toContain("No pudimos eliminar");
});
test("offline search filters loaded zones and keeps an empty-result state", async () => {
  const tree = await mount(Search); const input = tree.root.findByType(TextInput);
  expect(text(tree)).toContain(trail.name); await act(async () => input.props.onChangeText("inexistente")); expect(text(tree)).toContain("No hay rutas disponibles");
});
test("park list and detail identify cached information and open the selected institutional profile", async () => {
  const tree = await mount(Parks); expect(text(tree)).toContain("Informacion guardada");
  await press(tree, `Ver ${park.name}`); expect(router.push).toHaveBeenCalledWith({ pathname: "/parque-nacional", params: { slug: park.slug } });
  const detail = await mount(Park); expect(text(detail)).toContain(park.name); expect(text(detail)).toContain("Conectate para consultar");
  await press(detail, `Ver ${trail.name}`); expect(router.push).toHaveBeenCalledWith({ pathname: "/trail-detail", params: { id: "7" } });
});
test("a park loading failure can be retried without presenting it as current official advice", async () => {
  (parks.getNationalParks as jest.Mock).mockRejectedValueOnce(new Error("Sin conexión")); const tree = await mount(Parks); expect(text(tree)).toContain("Sin conexión");
  await press(tree, "Reintentar"); expect(text(tree)).toContain(park.name);
});
