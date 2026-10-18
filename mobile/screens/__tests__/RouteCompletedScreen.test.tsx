import "../../../testing/mobileSetup";
jest.mock("../../../services/routeSession", () => ({ finishRouteSession: jest.fn(), activeRouteSeconds: () => 3600, getSimulatedRouteTrackingSummary: jest.fn() }));
jest.mock("../../../database/database", () => ({ initDB: jest.fn().mockResolvedValue(undefined) }));
jest.mock("../../../database/sessionsRepository", () => ({ attachTrailToSession: jest.fn(), getLatestCompletedSession: jest.fn(), getOrCreateCompletedSession: jest.fn(), saveSessionReview: jest.fn() }));
jest.mock("../../../services/routeTracking", () => ({ getRouteTrackingSummary: jest.fn() }));
jest.mock("../../../services/syncQueue", () => ({ enqueueUnique: jest.fn().mockResolvedValue(1) }));
jest.mock("../../../services/completionMessages", () => ({
  CompletionContactRequiredError: class CompletionContactRequiredError extends Error {},
  sendRouteCompletionSms: jest.fn(),
}));
import { useLocalSearchParams, router } from "expo-router";
import { mount, press, text, act, flush } from "../../../testing/mobileHarness";
import { completed } from "../../../testing/fixtures";
import { finishRouteSession, getSimulatedRouteTrackingSummary } from "../../../services/routeSession";
import { getLatestCompletedSession, getOrCreateCompletedSession } from "../../../database/sessionsRepository";
import { getRouteTrackingSummary } from "../../../services/routeTracking";
import { CompletionContactRequiredError, sendRouteCompletionSms } from "../../../services/completionMessages";
import RouteCompleted from "../RouteCompletedScreen";

const label = "Informar a mi contacto de emergencia";
beforeEach(() => {
  (useLocalSearchParams as jest.Mock).mockReturnValue({ id: "7", startedAt: String(completed.started_at), totalMeters: "3000", routeProgressMeters: "3000", traveledMeters: "3000" });
  (finishRouteSession as jest.Mock).mockResolvedValue({ simulated: false, ended_at: completed.ended_at });
  (getOrCreateCompletedSession as jest.Mock).mockResolvedValue({ session: completed });
  (getLatestCompletedSession as jest.Mock).mockResolvedValue(null);
  (getRouteTrackingSummary as jest.Mock).mockResolvedValue({ distanceMeters: 3000, points: 5, lastPoint: null });
  (getSimulatedRouteTrackingSummary as jest.Mock).mockReturnValue({ distanceMeters: 3000, points: 5, lastPoint: null });
  (sendRouteCompletionSms as jest.Mock).mockResolvedValue({ result: "sent", message: "Terminé el recorrido" });
});

test("the completion notice opens SMS only after tapping and has no separate trip-plan action", async () => {
  const tree = await mount(RouteCompleted);
  expect(text(tree)).toContain(label);
  expect(sendRouteCompletionSms).not.toHaveBeenCalled();
  await press(tree, label);
  expect(sendRouteCompletionSms).toHaveBeenCalledWith({ trailId: 7, startedAt: completed.started_at, simulated: false });
  expect(text(tree)).toContain("Esto no confirma que tu contacto lo recibió");
  expect(router.push).not.toHaveBeenCalled();
  expect(text(tree)).not.toContain("Revisar y cerrar mi plan de regreso");
  expect(text(tree)).not.toContain("aviso por demora");
});

test.each([["cancelled", "SMS cancelado"], ["unknown", "Revisá allí el estado del SMS"]])("the %s outcome does not appear as a sent SMS", async (result, expected) => {
  (sendRouteCompletionSms as jest.Mock).mockResolvedValue({ result });
  const tree = await mount(RouteCompleted); await press(tree, label);
  expect(text(tree)).toContain(expected);
  expect(text(tree)).not.toContain("El teléfono indicó que enviaste");
});

test("a missing contact leads to contact settings", async () => {
  (sendRouteCompletionSms as jest.Mock).mockRejectedValue(new CompletionContactRequiredError());
  const tree = await mount(RouteCompleted); await press(tree, label);
  expect(router.push).toHaveBeenCalledWith("/contacto-seguridad");
});

test("a native failure can be retried without losing the saved activity", async () => {
  (sendRouteCompletionSms as jest.Mock).mockRejectedValueOnce(new Error("Failed to open native composer"));
  const tree = await mount(RouteCompleted); await press(tree, label);
  expect(text(tree)).toContain("No pudimos preparar el SMS");
  expect(text(tree)).toContain("Sendero completado");
  await press(tree, label);
  expect(sendRouteCompletionSms).toHaveBeenCalledTimes(2);
});

test("simulated completions never offer a real notice", async () => {
  (finishRouteSession as jest.Mock).mockResolvedValue({ simulated: true, ended_at: completed.ended_at });
  const tree = await mount(RouteCompleted);
  expect(text(tree)).toContain("Recorrido simulado");
  expect(text(tree)).not.toContain(label);
  expect(sendRouteCompletionSms).not.toHaveBeenCalled();
});

test("ending early can inform the contact without claiming the full trail was completed", async () => {
  (getOrCreateCompletedSession as jest.Mock).mockResolvedValue({ session: { ...completed, completion_status: "ended_early", route_progress_meters: 1000 } });
  const tree = await mount(RouteCompleted);
  expect(text(tree)).toContain(label);
  expect(text(tree)).not.toContain("Sendero completado");
  await press(tree, label);
  expect(sendRouteCompletionSms).toHaveBeenCalledTimes(1);
});

test("rapid taps prepare only one SMS", async () => {
  let finish!: (result: { result: string }) => void;
  (sendRouteCompletionSms as jest.Mock).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const tree = await mount(RouteCompleted);
  const button = tree.root.findAll((node: any) => node.props.label === label)[0];
  await act(async () => { void button.props.onPress(); void button.props.onPress(); await flush(); });
  expect(sendRouteCompletionSms).toHaveBeenCalledTimes(1);
  await act(async () => { finish({ result: "sent" }); await flush(); });
});
