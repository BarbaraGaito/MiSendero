const definitions = require("../src/data/additionalTrailDefinitions");
const trails = require("../src/data/additionalTrails");
const routes = require("../src/data/additionalTrailRoutes.json");
const { assemble } = require("../scripts/catalogGeometry");
const { sampleRoute } = require("../src/trailElevation");

describe("verified additional catalog", () => {
  test("adds twelve distinct trails across seven additional provinces", () => {
    expect(trails).toHaveLength(12);
    expect(new Set(trails.map((trail) => trail.name)).size).toBe(12);
    expect(new Set(trails.map((trail) => trail.location.split(", ").at(-1))).size).toBe(7);
  });

  test.each(definitions)("$key has complete, attributed real-world data", (definition) => {
    const trail = trails.find((item) => item.name === definition.name);
    const route = routes[definition.key];
    expect(trail.duration).toBeTruthy();
    expect(trail.provenance.access).toBeTruthy();
    expect(trail.provenance.precautions).toBeTruthy();
    expect(trail.provenance.sources[0].url).toBe(definition.source_url);
    expect(trail.provenance.photo.author).toBeTruthy();
    expect(trail.provenance.photo.license_url).toMatch(/^https:\/\//);
    expect(trail.image_url).toMatch(/^https:\/\/(upload|thumb)\.wikimedia\.org\//);
    expect(route.ways.map((way) => way.id)).toEqual(definition.ways.map((way) => way.id));
    route.ways.slice(1).forEach((way, index) => expect(way.from_node).toBe(route.ways[index].to_node));
    expect(sampleRoute(route.points).samples.at(-1).distance_m / 1000).toBeCloseTo(trail.distance_km, 3);
    if (definition.route_type === "out_and_back") {
      expect(route.points.at(-1)).toEqual(route.points[0]);
      expect(route.points).toEqual([...route.points].reverse());
    } else {
      expect(route.points.at(-1)).not.toEqual(route.points[0]);
    }
    for (const point of route.points) {
      expect(point[0]).toBeGreaterThan(-56);
      expect(point[0]).toBeLessThan(-21);
      expect(point[1]).toBeGreaterThan(-74);
      expect(point[1]).toBeLessThan(-53);
    }
  });

  test("does not present Cerro Alto's planning time as an official duration", () => {
    const trail = trails.find((item) => item.name === "Cerro Alto desde Namuncura");
    expect(trail.provenance.duration_basis).toBe("planning_estimate");
    expect(trail.provenance.precautions).toContain("no un tiempo publicado");
  });

  test("refuses disconnected, forbidden or incorrectly clipped ways", () => {
    const elements = [
      { type: "node", id: 1, lat: -40, lon: -70 },
      { type: "node", id: 2, lat: -40.001, lon: -70 },
      { type: "node", id: 3, lat: -40.002, lon: -70 },
      { type: "node", id: 4, lat: -40.003, lon: -70 },
      { type: "way", id: 10, nodes: [1, 2], tags: { highway: "path" } },
      { type: "way", id: 11, nodes: [3, 4], tags: { highway: "path" } },
      { type: "way", id: 12, nodes: [2, 3], tags: { highway: "path", access: "no" } },
    ];
    expect(() => assemble([{ id: 10 }, { id: 11 }], elements)).toThrow("Disconnected");
    expect(() => assemble([{ id: 12 }], elements)).toThrow("Not a usable");
    expect(() => assemble([{ id: 10, from: 99 }], elements)).toThrow("Invalid way clipping");
    expect(assemble([{ id: 10, reverse: true }], elements).points).toEqual([[-40.001, -70], [-40, -70]]);
  });
});
