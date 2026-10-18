jest.mock("../authSession", () => ({ getAuthSession: jest.fn().mockResolvedValue({ token: "session-token", user: { id: 1 } }), clearAuthSession: jest.fn() }));
jest.mock("../accountLifecycle", () => ({ isAccountDeletionPending: jest.fn().mockResolvedValue(false), eraseLocalAccountData: jest.fn() }));
import * as api from "../api";
import { isAccountDeletionPending } from "../accountLifecycle";
beforeEach(() => { jest.clearAllMocks(); jest.spyOn(global, "fetch").mockResolvedValue({ ok: true, json: async () => ({ id: 7 }) } as Response); });
afterEach(() => { jest.restoreAllMocks(); jest.useRealTimers(); });
const body = { issue_summary: "Barro", severity: "Alta", trail_state: "Precaución" };
const plan = { client_plan_id: "plan", trail_id: 7, expected_return_at: "2026-10-16T20:00:00Z", grace_minutes: 30, contact_name: "Contacto", contact_phone: "+54111111111" };
test.each([
  ["login", () => api.loginUser("a@example.test", "test-password"), "/auth/login", "POST", undefined],
  ["registration", () => api.registerUser("Ana", "a@example.test", "test-password", "2026-10-16"), "/auth/register", "POST", undefined],
  ["catalogue", api.getTrails, "/trails", "GET", undefined],
  ["trail", () => api.getTrailById(7), "/trails/7", "GET", undefined],
  ["weather", () => api.getTrailWeather(7), "/trails/7/weather", "GET", undefined],
  ["parks", api.getNationalParks, "/national-parks", "GET", undefined],
  ["park slug", () => api.getNationalPark("área/test"), "/national-parks/%C3%A1rea%2Ftest", "GET", undefined],
  ["reports", () => api.getTrailReports(7), "/trails/7/reports", "GET", "session-token"],
  ["create report", () => api.createTrailReport(7, body, "session-token"), "/trails/7/reports", "POST", "session-token"],
  ["flag", () => api.flagReport(7, "Abuso", "session-token"), "/reports/7/flag", "POST", "session-token"],
  ["block", () => api.blockReportAuthor(7, "session-token"), "/reports/7/block-author", "POST", "session-token"],
  ["withdraw", () => api.withdrawReport(7, "session-token"), "/reports/7", "DELETE", "session-token"],
  ["correct", () => api.correctReport(7, "Corregido", "Detalles", "session-token"), "/reports/7", "PATCH", "session-token"],
  ["trip list", () => api.getTripPlans("session-token"), "/trip-plans", "GET", "session-token"],
  ["trip creation", () => api.createTripPlan(plan, "session-token"), "/trip-plans", "POST", "session-token"],
  ["check in", () => api.closeTripPlan(7, "checked_in", "session-token"), "/trip-plans/7/close", "POST", "session-token"],
  ["profile", () => api.getProfile("session-token"), "/auth/me", "GET", "session-token"],
  ["export", () => api.exportAccountData("session-token"), "/auth/me/data", "GET", "session-token"],
  ["consent", () => api.recordPrivacyDecision({ purpose: "sensitiveDataConsent" }, "session-token"), "/auth/me/privacy-decisions", "POST", "session-token"],
  ["activity", () => api.createActivity({ started_at: "2026-10-16T12:00:00Z" }, "session-token"), "/activities", "POST", "session-token"],
  ["SOS without GPS", () => api.createEmergencyAlert({ client_event_id: "sos", latitude: null, longitude: null }, "session-token"), "/emergency-alerts", "POST", "session-token"],
] as const)("%s preserves the API method, resource and authentication contract", async (_label, call, suffix, method, token) => {
  expect(await call()).toEqual({ id: 7 });
  const [url, request] = (fetch as jest.Mock).mock.calls[0];
  expect(url.endsWith(suffix)).toBe(true); expect(request.method).toBe(method);
  expect(request.headers.Authorization).toBe(token ? `Bearer ${token}` : undefined);
  if (request.body) { expect(request.headers["Content-Type"]).toBe("application/json"); expect(() => JSON.parse(request.body)).not.toThrow(); }
});
test("validation issues, non-JSON errors and network failures stay distinguishable", async () => {
  (fetch as jest.Mock).mockResolvedValueOnce({ ok: false, status: 400, json: async () => ({ issues: [{ path: "name", message: "required" }, { message: "invalid" }] }) });
  await expect(api.getTrails()).rejects.toMatchObject({ status: 400, message: "Revisá los datos ingresados e intentá nuevamente." });
  (fetch as jest.Mock).mockResolvedValueOnce({ ok: false, status: 503, json: async () => { throw new Error("HTML response"); } });
  await expect(api.getTrails()).rejects.toMatchObject({ status: 503 });
  (fetch as jest.Mock).mockRejectedValueOnce(new Error("offline"));
  await expect(api.getTrails()).rejects.toThrow("No pudimos conectar");
});
test("timeout aborts a hung transport and clears its timer", async () => {
  jest.useFakeTimers();
  (fetch as jest.Mock).mockImplementation((_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener("abort", () => reject(new Error("aborted")))));
  const result = expect(api.getTrails()).rejects.toThrow("No pudimos conectar");
  await jest.advanceTimersByTimeAsync(10000); await result;
  expect(jest.getTimerCount()).toBe(0);
});
test("a deletion marker blocks new writes before any request is sent", async () => {
  (isAccountDeletionPending as jest.Mock).mockResolvedValueOnce(true);
  await expect(api.createTrailReport(7, body, "session-token")).rejects.toThrow("baja está pendiente");
  expect(fetch).not.toHaveBeenCalled();
});

test("server diagnostics stay out of the UI while status and error codes remain available", async () => {
  (fetch as jest.Mock).mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({ message: "relation trails does not exist", code: "DATABASE_FAILURE" }) });
  await expect(api.getTrails()).rejects.toMatchObject({ status: 500, code: "DATABASE_FAILURE", message: "No pudimos completar la solicitud. Intentá nuevamente más tarde." });
});

test("an unavailable automatic notice offers SMS without claiming the plan was activated", async () => {
  (fetch as jest.Mock).mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({ message: "El canal no está configurado." }) });
  await expect(api.createTripPlan(plan, "session-token")).rejects.toMatchObject({ status: 503, message: "No pudimos activar el aviso automático. Compartí el plan por SMS con tu contacto." });
});
