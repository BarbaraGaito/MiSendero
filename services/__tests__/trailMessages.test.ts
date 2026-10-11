jest.mock("../trailRepository", () => ({ getTrailById: jest.fn() }));
import { Trail } from "../../types";
import { getTrailById } from "../trailRepository";
import { buildTripPlanMessage, formatTrailMessageContext, getTrailForMessage } from "../trailMessages";

const trail: Trail = {
  id: 10, name: "Laguna del Tesoro - Aconquija", location: "Parque Nacional Aconquija, Tucuman",
  duration: null, distance_km: null, difficulty: "Alta", description: null, image_url: null,
  center_lat: -27.31, center_lng: -65.81, map_zoom: 13, created_at: "2026-10-11",
  route_coordinates: "[[-27.3,-65.8],[-27.31,-65.81]]",
};
beforeEach(() => jest.clearAllMocks());

test("shares the route name, zone and mapped starting point instead of the route ID or map center", () => {
  const message = buildTripPlanMessage({ trail, expectedReturnAt: "2026-10-11T18:00:00Z", graceMinutes: 30 });
  expect(message).toContain("Sendero: Laguna del Tesoro - Aconquija");
  expect(message).toContain("Zona: Parque Nacional Aconquija, Tucuman");
  expect(message).toContain("Inicio del recorrido: -27.30000, -65.80000");
  expect(message).toContain("https://maps.google.com/?q=-27.3,-65.8");
  expect(message).not.toContain("sendero 10");
  expect(message).not.toContain("?q=-27.31,-65.81");
  expect(message).toContain("Regreso previsto:");
  expect(message).toContain("Margen: 30 min");
});

test("each route uses its own name and coordinates", () => {
  const other = { ...trail, id: 1, name: "Sendero a Confluencia", location: "Parque Provincial Aconcagua, Mendoza",
    route_coordinates: "[[-32.823914,-69.940673],[-32.824238,-69.941973]]" };
  const message = formatTrailMessageContext(other);
  expect(message).toContain(other.name);
  expect(message).toContain(other.location);
  expect(message).toContain("?q=-32.823914,-69.940673");
  expect(message).not.toContain(trail.name);
});

test.each([null, "bad JSON", "[]", "[[120,200]]"])("missing or invalid geometry does not invent a starting point (%s)", (route_coordinates) => {
  const message = formatTrailMessageContext({ ...trail, route_coordinates });
  expect(message).toContain(trail.name);
  expect(message).not.toContain("Inicio del recorrido");
  expect(message).not.toContain("maps.google.com");
});

test("offline or unavailable metadata does not prevent preparing the message", async () => {
  (getTrailById as jest.Mock).mockRejectedValue(new Error("offline"));
  expect(await getTrailForMessage(10)).toBeNull();
  expect(formatTrailMessageContext(null)).toBe("Sendero: nombre no disponible.");
});

test("reads downloaded route metadata and rejects a different route", async () => {
  (getTrailById as jest.Mock).mockResolvedValue(trail);
  expect(await getTrailForMessage(10)).toEqual(trail);
  expect(await getTrailForMessage(1)).toBeNull();
});

test("a stalled route lookup cannot indefinitely delay an SOS", async () => {
  jest.useFakeTimers();
  try {
    (getTrailById as jest.Mock).mockImplementation(() => new Promise(() => undefined));
    const result = getTrailForMessage(10);
    jest.advanceTimersByTime(2000);
    expect(await result).toBeNull();
  } finally {
    jest.useRealTimers();
  }
});
