import { filterTrails, isNationalParkTrail } from "../trailFilters";
import { Trail } from "../../types";

const makeTrail = (id: number, name: string, location: string, difficulty = "Baja", distance_km: number | null = 3): Trail => ({
  id, name, location, difficulty, distance_km, duration: null, description: null,
  image_url: null, center_lat: null, center_lng: null, map_zoom: null,
  route_coordinates: null, created_at: "2026-10-11", national_park: null,
});
const trails = [
  makeTrail(1, "Sendero a Confluencia", "Parque Provincial Aconcagua, Mendoza", "Media", 14),
  makeTrail(2, "Volcan Lanin", "Parque Nacional Lanin, Neuquen", "Alta", 13),
  makeTrail(3, "Sendero Macuco", "Parque Nacional Iguazu, Misiones", "Media", 7),
  makeTrail(4, "Laguna Esmeralda", "Valle de Tierra Mayor, Tierra del Fuego", "Media", 9),
  makeTrail(5, "Mirador de los Condores", "Parque Nacional Los Glaciares, Santa Cruz"),
  makeTrail(6, "Cerro Morado", "Parque Provincial Ischigualasto, San Juan", "Alta", null),
];

test("distinguishes national from provincial and other trails without institutional profiles", () => {
  expect(filterTrails(trails, [], "", "Todas", "Todas", "national_parks").map((trail) => trail.id)).toEqual([2, 3, 5]);
  expect(filterTrails(trails, [], "", "Todas", "Todas", "other_trails").map((trail) => trail.id)).toEqual([1, 4, 6]);
  expect(filterTrails(trails, [], "", "Todas", "Todas", "all")).toEqual(trails);
});

test("includes all national parks in the expanded catalog, even without a verified institutional profile", () => {
  const definitions = require("../../backend/src/data/additionalTrailDefinitions");
  const catalog: Trail[] = definitions.map((item: { name: string; location: string }, index: number) => makeTrail(index, item.name, item.location));
  const national = filterTrails(catalog, [], "", "Todas", "Todas", "national_parks");
  expect(national).toHaveLength(11);
  const other = filterTrails(catalog, [], "", "Todas", "Todas", "other_trails");
  expect(other).toHaveLength(11);
  expect(other.map((trail) => trail.name)).toEqual([
    "Laguna Esmeralda",
    ...definitions.filter((item: { national_park?: boolean }) => item.national_park === false).map((item: { name: string }) => item.name),
  ]);
});

test("combines area, distance, difficulty, search and favorites", () => {
  expect(filterTrails(trails, [], "IGUAZÚ", "Media", "Media", "national_parks").map((trail) => trail.id)).toEqual([3]);
  expect(filterTrails(trails, [1, 2, 5], "", "Favoritas", "Corta", "national_parks").map((trail) => trail.id)).toEqual([5]);
  expect(filterTrails(trails, [], "", "Alta", "Sin dato", "other_trails").map((trail) => trail.id)).toEqual([6]);
  expect(filterTrails(trails, [], "Esmeralda", "Todas", "Todas", "national_parks")).toEqual([]);
});

test("clearing the filters returns all trails without changing data or order", () => {
  filterTrails(trails, [], "", "Todas", "Todas", "national_parks");
  expect(filterTrails(trails, [], "", "Todas", "Todas")).toEqual(trails);
});

test("handles normalized catalog locations and does not infer membership from a nearby park", () => {
  expect(isNationalParkTrail({ location: " PARQUE NACIONAL LANÍN, Neuquén " })).toBe(true);
  expect(isNationalParkTrail({ location: "Cerca del Parque Nacional Tierra del Fuego" })).toBe(false);
  expect(isNationalParkTrail({ location: "El Chalten", national_park_slug: "los-glaciares" })).toBe(true);
});
