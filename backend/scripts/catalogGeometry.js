const fs = require("node:fs/promises");
const path = require("node:path");
const { sampleRoute } = require("../src/trailElevation");

const regions = {
  iguazu: [-54.48, -25.72, -54.42, -25.65],
  fueguino: [-68.64, -54.89, -68.48, -54.79],
  esmeralda: [-68.15, -54.76, -68.09, -54.66],
  frey: [-71.51, -41.23, -71.42, -41.15],
  condorito: [-64.85, -31.70, -64.67, -31.59],
  chalten: [-72.92, -49.38, -72.86, -49.30],
  lihue: [-65.65, -38.04, -65.53, -37.94],
  quijadas: [-67.02, -32.54, -66.91, -32.44],
};
const cacheDir = path.resolve(__dirname, "../../tmp/catalog-osm");
const fetchJson = async (url) => {
  const response = await fetch(url, {
    headers: { "User-Agent": "MiSendero/1.0 (university hiking catalog; cartographic data import)", Accept: "application/json" },
    signal: AbortSignal.timeout(60000),
  });
  if (!response.ok) throw new Error(`OSM HTTP ${response.status}`);
  const data = await response.json();
  if (data.error || !Array.isArray(data.elements)) throw new Error("Incomplete OSM response");
  return data;
};
const readRegion = async (region) => JSON.parse(await fs.readFile(path.join(cacheDir, `${region}.json`), "utf8"));
const coordinates = (ids, nodes) => ids.map((id) => {
  const node = nodes.get(id);
  if (!node) throw new Error(`Missing OSM node ${id}`);
  return [node.lat, node.lon];
});
const lengthKm = (points) => {
  if (points.length < 2 || points.every((point) => point[0] === points[0][0] && point[1] === points[0][1])) return 0;
  try {
    return sampleRoute(points).samples.at(-1).distance_m / 1000;
  } catch (error) {
    if (error.message === "elevation-no-geometry") return 0;
    throw error;
  }
};

// Only concatenate reviewed ways at shared OSM nodes. Never bridge missing paths.
const assemble = (specs, elements) => {
  const nodes = new Map(elements.filter((item) => item.type === "node").map((item) => [item.id, item]));
  const ways = new Map(elements.filter((item) => item.type === "way").map((item) => [item.id, item]));
  let ids = [];
  const sources = [];
  for (const spec of specs) {
    const way = ways.get(spec.id);
    if (!way || !["path", "footway", "steps", "track", "pedestrian"].includes(way.tags?.highway) ||
      way.tags?.access === "no" || way.tags?.foot === "no") throw new Error(`Not a usable mapped walking way: ${spec.id}`);
    let next = [...way.nodes];
    if (spec.reverse) next.reverse();
    if (spec.from) next = next.slice(next.indexOf(spec.from));
    if (spec.to) next = next.slice(0, next.indexOf(spec.to) + 1);
    if (next.length < 2 || (spec.from && next[0] !== spec.from) || (spec.to && next.at(-1) !== spec.to)) {
      throw new Error(`Invalid way clipping: ${spec.id}`);
    }
    if (ids.length && ids.at(-1) !== next[0]) throw new Error(`Disconnected OSM ways at ${spec.id}`);
    ids = ids.concat(ids.length ? next.slice(1) : next);
    sources.push({ id: way.id, version: way.version, timestamp: way.timestamp, from_node: next[0], to_node: next.at(-1), reverse: !!spec.reverse });
  }
  return { points: coordinates(ids, nodes), ways: sources };
};

const main = async () => {
  const [command, region, filter = ""] = process.argv.slice(2);
  if (command === "--discover") {
    await fs.mkdir(cacheDir, { recursive: true });
    for (const [name, bbox] of Object.entries(regions)) {
      if (region && region !== name) continue;
      const data = await fetchJson(`https://api.openstreetmap.org/api/0.6/map.json?bbox=${bbox.join(",")}`);
      await fs.writeFile(path.join(cacheDir, `${name}.json`), JSON.stringify(data));
      console.log(`${name}: ${data.elements.length} mapped elements`);
    }
  } else if (command === "--inspect") {
    const data = await readRegion(region);
    const nodes = new Map(data.elements.filter((item) => item.type === "node").map((item) => [item.id, item]));
    for (const way of data.elements.filter((item) => item.type === "way" &&
      ["path", "footway", "steps", "track", "pedestrian"].includes(item.tags?.highway) &&
      new RegExp(filter, "i").test(item.tags?.name || ""))) {
      const points = coordinates(way.nodes, nodes);
      console.log(JSON.stringify({ id: way.id, name: way.tags?.name, highway: way.tags.highway,
        access: way.tags.access, km: Number(lengthKm(points).toFixed(3)),
        from: { id: way.nodes[0], point: points[0] }, to: { id: way.nodes.at(-1), point: points.at(-1) } }));
    }
    for (const relation of data.elements.filter((item) => item.type === "relation" && item.tags?.route === "hiking")) {
      console.log(JSON.stringify(relation));
    }
  } else if (command === "--build") {
    const definitions = require("../src/data/additionalTrailDefinitions");
    const output = {};
    for (const trail of definitions) {
      const data = await readRegion(trail.region);
      const route = assemble(trail.ways, data.elements);
      if (trail.route_type === "out_and_back") route.points = route.points.concat(route.points.slice(0, -1).reverse());
      output[trail.key] = { ...route, distance_km: Number(lengthKm(route.points).toFixed(3)),
        retrieved_at: new Date().toISOString(), source: "OpenStreetMap contributors", license: "ODbL-1.0",
        source_url: `https://www.openstreetmap.org/way/${route.ways[0].id}` };
      console.log(`${trail.key}: ${route.points.length} points, ${output[trail.key].distance_km} km`);
    }
    await fs.writeFile(path.resolve(__dirname, "../src/data/additionalTrailRoutes.json"), JSON.stringify(output, null, 2) + "\n");
  } else throw new Error("Use --discover [region], --inspect region [name filter], or --build");
};

if (require.main === module) main().catch((error) => { console.error(error.message); process.exitCode = 1; });
module.exports = { assemble };
