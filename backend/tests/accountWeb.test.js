// Unit contract for the served browser script. DOM events and HTTP are controlled;
// this is deliberately not a browser end-to-end or visual-accessibility test.
const fs = require("node:fs");
class Element {
  constructor(tag = "div") { this.tag = tag; this.listeners = {}; this.children = []; this.value = ""; this.checked = false; this.hidden = true; this.disabled = false; this.textContent = ""; }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren() { this.children = []; }
  reset() { this.value = ""; }
  click() { this.clicked = true; return this.listeners.click?.({ preventDefault() {} }); }
}
let elements, created, fetchMock;
const tick = async () => { for (let i = 0; i < 15; i++) await Promise.resolve(); };
const fire = async (id, type = "click") => { await elements[id].listeners[type]({ preventDefault() {} }); await tick(); };
const ok = (body) => ({ ok: true, json: async () => body });
const login = async (role = "user") => { fetchMock.mockResolvedValueOnce(ok({ token: "session-only", user: { name: "Ana", role } })); elements.email.value = "ana@example.test"; elements.password.value = "secret-test"; await fire("account-form", "submit"); };
beforeEach(async () => {
  jest.useFakeTimers(); created = [];
  const html = fs.readFileSync(require.resolve("../src/public/account-deletion.html"), "utf8");
  elements = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map((match) => [match[1], new Element()]));
  global.document = { getElementById: (id) => elements[id], createElement: (tag) => { const node = new Element(tag); created.push(node); return node; } };
  fetchMock = jest.spyOn(global, "fetch").mockResolvedValue(ok({ url: "mailto:privacy@example.test" }));
  jest.spyOn(URL, "createObjectURL").mockReturnValue("blob:export-test"); jest.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  jest.isolateModules(() => require("../src/public/account.js")); await tick();
});
afterEach(() => { delete global.document; jest.restoreAllMocks(); jest.useRealTimers(); });
test("authentication keeps credentials out of the input and scopes subsequent requests to the current visit", async () => {
  expect(elements.contact.href).toBe("mailto:privacy@example.test"); await login(); expect(elements.password.value).toBe(""); expect(elements.actions.hidden).toBe(false); expect(elements.moderation.hidden).toBe(true);
  elements.name.value = "Nombre nuevo"; fetchMock.mockResolvedValueOnce(ok({})); await fire("name-form", "submit");
  expect(fetchMock).toHaveBeenLastCalledWith("/api/auth/me", expect.objectContaining({ method: "PATCH", headers: expect.objectContaining({ Authorization: "Bearer session-only" }), body: JSON.stringify({ name: "Nombre nuevo" }), cache: "no-store" }));
  await fire("sign-out"); expect(elements.actions.hidden).toBe(true); expect(elements.confirm.checked).toBe(false); expect(elements.status.textContent).toContain("cerrada");
  fetchMock.mockResolvedValueOnce(ok({})); await fire("name-form", "submit"); expect(fetchMock.mock.calls.at(-1)[1].headers.Authorization).toBeUndefined();
});
test("failed login clears an older session and server validation errors remain visible", async () => {
  await login("admin"); expect(elements.moderation.hidden).toBe(false); fetchMock.mockResolvedValueOnce({ ok: false, json: async () => ({ message: "Credenciales inválidas" }) }); await fire("account-form", "submit");
  expect(elements.actions.hidden).toBe(true); expect(elements.moderation.hidden).toBe(true); expect(elements.status.textContent).toBe("Credenciales inválidas");
  fetchMock.mockResolvedValueOnce({ ok: false, json: async () => ({}) }); await fire("name-form", "submit"); expect(elements.status.textContent).toContain("No se pudo completar");
});
test("export downloads the returned data and revokes the temporary object URL", async () => {
  await login(); fetchMock.mockResolvedValueOnce(ok({ user: { id: 31 }, activities: [] })); await fire("export"); const link = created.find((node) => node.tag === "a"); expect(link.download).toBe("misendero-mis-datos.json"); expect(link.href).toBe("blob:export-test"); expect(link.clicked).toBe(true);
  jest.advanceTimersByTime(1000); expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:export-test");
  fetchMock.mockRejectedValueOnce(new Error("offline")); await fire("export"); expect(elements.status.textContent).toBe("offline");
});
test("deletion is gated by explicit confirmation, reports uncertainty, and clears the session only on success", async () => {
  await login(); const calls = fetchMock.mock.calls.length; await fire("delete"); expect(fetchMock).toHaveBeenCalledTimes(calls); expect(elements.status.textContent).toContain("confirmación");
  elements.confirm.checked = true; elements["delete-password"].value = "secret-test"; fetchMock.mockRejectedValueOnce(new Error("response lost")); await fire("delete"); expect(elements.status.textContent).toBe("response lost"); expect(elements.actions.hidden).toBe(false); expect(elements.delete.disabled).toBe(false);
  expect(elements["delete-password"].value).toBe(""); elements["delete-password"].value = "secret-test";
  fetchMock.mockResolvedValueOnce(ok({})); await fire("delete"); expect(fetchMock).toHaveBeenLastCalledWith("/api/auth/me", expect.objectContaining({ method: "DELETE", body: JSON.stringify({ password: "secret-test" }) })); expect(elements.actions.hidden).toBe(true); expect(elements.status.textContent).toContain("remotos eliminados");
});
test("moderation renders untrusted text as text and applies hide/restore through the protected API", async () => {
  await login("admin"); fetchMock.mockResolvedValueOnce(ok([{ report_id: 8, issue_summary: "<img onerror=alert(1)>", details: "Texto", reason: "Datos personales", moderation_status: "visible" }, { report_id: 9, issue_summary: "Otro", reason: "Abuso", moderation_status: "hidden" }])); await fire("refresh-moderation");
  expect(elements.flags.children).toHaveLength(2); const first = elements.flags.children[0]; expect(first.children[0].textContent).toContain("<img onerror=alert(1)>"); expect(first.children[0].innerHTML).toBeUndefined();
  fetchMock.mockResolvedValueOnce(ok({})); await first.children[1].click(); expect(fetchMock).toHaveBeenLastCalledWith("/api/reports/8/moderate", expect.objectContaining({ body: JSON.stringify({ status: "hidden" }) }));
  const restore = elements.flags.children[1].children[1]; expect(restore.textContent).toContain("Restaurar"); fetchMock.mockRejectedValueOnce(new Error("offline")); await restore.click(); expect(restore.disabled).toBe(false); expect(elements.status.textContent).toBe("offline");
  fetchMock.mockResolvedValueOnce(ok([])); await fire("refresh-moderation"); expect(elements.flags.children).toHaveLength(0); expect(elements.status.textContent).toContain("No hay denuncias");
  fetchMock.mockRejectedValueOnce(new Error("forbidden")); await fire("refresh-moderation"); expect(elements.status.textContent).toBe("forbidden");
});
