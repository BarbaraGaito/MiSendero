// Export only locations already backed by the reviewed catalog definitions.
const fs = require("node:fs");
const path = require("node:path");
const { createHash } = require("node:crypto");
const { geometryCanonical } = require("../src/contracts/environmental");
const definitions = [
  ["backend/src/data/legacyTrails.js", require("../src/data/legacyTrails")],
  ["backend/src/data/additionalTrails.js", require("../src/data/additionalTrails")],
  ["backend/src/data/catalogExpansion20261017.js", require("../src/data/catalogExpansion20261017").trails],
];
const selected = new Set(["Refugio Frey desde Villa Catedral", "Mirador de los Condores - El Chalten", "Pampa Alta - Tierra del Fuego"]);
const fireSelected = new Set(["Refugio Frey desde Villa Catedral", "Bosque Tallado desde la plataforma del Piltriquitron",
  "Quebrada del Condorito - Balcon Norte", "Sendero Macuco - Salto Arrechea", "Sendero Che Roga - Mburucuyá",
  "Sendero La Chuña - El Rey", "Sendero Namuncura", "Cerro Ventana - Hueco de la Ventana"]);
const regions = definitions.flatMap(([source, trails]) => trails.filter((t) => selected.has(t.name)).map((trail) => ({
  name: trail.name, location: trail.location, latitude: trail.center_lat, longitude: trail.center_lng,
  definition: source, geometry_sha256: createHash("sha256").update(geometryCanonical(trail)).digest("hex"),
  sources: trail.provenance?.sources || [],
})));
if (regions.length !== 3 || regions.some((r) => !Number.isFinite(r.latitude) || !Number.isFinite(r.longitude))) throw new Error("Missing reviewed region geography");
const target = path.resolve(__dirname, "../../training/data/environmental/geography.json");
fs.mkdirSync(path.dirname(target), { recursive: true });
const fire_regions = definitions.flatMap(([source, trails]) => trails.filter((t) => fireSelected.has(t.name)).map((trail) => ({
  name: trail.name, location: trail.location, latitude: trail.center_lat, longitude: trail.center_lng,
  definition: source, geometry_sha256: createHash("sha256").update(geometryCanonical(trail)).digest("hex"),
  sources: trail.provenance?.sources || [],
})));
if (fire_regions.length !== 8 || fire_regions.some((r) => !r.sources.length)) throw new Error("Fire regions require existing documented catalog geography");
fs.writeFileSync(target, JSON.stringify({ schema_version: 1, regions, fire_regions }, null, 2) + "\n");
const routeGeometryTarget = path.resolve(__dirname, "../../training/data/environmental/private/fire-route-geometries.json");
const fire_route_geometries = definitions.flatMap(([source, trails]) => trails
  .filter((t) => fireSelected.has(t.name) && Array.isArray(t.route_coordinates) && t.route_coordinates.length >= 2)
  .map((trail) => ({
    name: trail.name, definition: source,
    geometry_sha256: createHash("sha256").update(geometryCanonical(trail)).digest("hex"),
    coordinate_order: "latitude,longitude",
    route_coordinates: trail.route_coordinates,
    sources: trail.provenance?.sources || [],
  })));
if (fire_route_geometries.length < 6 || fire_route_geometries.some((r) => !r.sources.length)) {
  throw new Error("Expected reviewed route geometries for the available fire sectors");
}
fs.mkdirSync(path.dirname(routeGeometryTarget), { recursive: true });
fs.writeFileSync(routeGeometryTarget, JSON.stringify({
  schema_version: 1, source_geography_sha256: createHash("sha256").update(fs.readFileSync(target)).digest("hex"),
  fire_route_geometries,
}, null, 2) + "\n");
console.log(`Exported ${regions.length} reviewed locations and ${fire_route_geometries.length} full fire-route geometries`);
