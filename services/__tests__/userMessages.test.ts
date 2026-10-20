import { userMessage } from "../userMessages";

test.each([
  new Error("SQLITE_ERROR: no such table: route_sessions"),
  new TypeError("Failed to fetch"),
  new Error("Failed to open native composer"),
  { message: "El proveedor offline no está configurado" },
  { message: "Falta EXPO_PUBLIC_OFFLINE_STANDARD_TILE_URL" },
  { message: "Invalid input: expected number, received undefined" },
  null,
  { message: 42 },
  "",
  "x".repeat(601),
  "AB_C",
  "ab_c",
  "A__B",
  "AB__",
  "__AB_CD",
  `${"A".repeat(300)}_${"B".repeat(299)}`,
  "El canal no está configurado",
  `${"proveedor ".repeat(40)}sin configurar`,
])("internal or unusable errors receive an actionable fallback: %p", (error) => {
  expect(userMessage(error, "No pudimos guardar. Intentá nuevamente.")).toBe("No pudimos guardar. Intentá nuevamente.");
});

test.each([
  "Credenciales inválidas",
  "Iniciá sesión para activar el aviso por demora.",
  "El regreso debe estar dentro de las próximas 72 horas.",
  "El cierre del plan sigue pendiente.",
  "A_B",
  "AB_",
  "configuración del proveedor pendiente",
  "proveedor\nconfigurado",
  "canal\rconfigurado",
  "proveedor\u2028configurado",
  "A".repeat(600),
])("actionable user messages remain available: %s", (message) => {
  expect(userMessage(new Error(message), "Reintentá.")).toBe(message);
});
