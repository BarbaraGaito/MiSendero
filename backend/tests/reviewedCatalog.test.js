const { applyReviewedFacts, review } = require("../src/data/reviewedTrailFacts");
const legacy = require("../src/data/legacyTrails");
const { trails } = require("../src/data/catalogExpansion20261017");
const { cachedElevation } = require("../src/trailElevation");
const { eligibleTrails } = require("../scripts/refreshRecommendationElevation");
const { runValidation, validateElevationEvidence } = require("../scripts/validateCatalogRecommendations");

test("reviewed official records confirm only their documented fields, without modifying input records", () => {
  expect(review.entries).toHaveLength(10);
  const originals = JSON.stringify(legacy);
  const rows = legacy.map(applyReviewedFacts);
  expect(JSON.stringify(legacy)).toBe(originals);
  const tesoro = rows.find(t => t.name.includes("Tesoro"));
  expect(tesoro.difficulty).toBe("Media");
  expect(tesoro.provenance.duration_basis).toBe("official_one_way_only");
  expect(tesoro.provenance.review.unconfirmed_fields).toContain("duration");
  const confluencia = rows.find(t => t.name.includes("Confluencia"));
  expect(confluencia.provenance.duration_basis).toBe("conflicting_sources");
  expect(confluencia.provenance.sources).toHaveLength(2);
  const mollar = rows.find(t => t.name.includes("Mollar"));
  expect(mollar.provenance.review.confirmed_fields).toContain("distance_km");
  expect(mollar.provenance.review.unconfirmed_fields).toContain("difficulty");
  const unrelated = { name: "Not reviewed", difficulty: "Alta" };
  expect(applyReviewedFacts(unrelated)).toBe(unrelated);
});

test("stored DEM observations reproduce their trace, sample locations and accumulated ascent", () => {
  expect(validateElevationEvidence()).toBe(11);
  expect(eligibleTrails()).toHaveLength(11);
  const che = trails.find(t => t.provenance.catalog_key === "mburucuya-che-roga");
  expect(cachedElevation(che)).toMatchObject({ ascent_m: 27, source: "Copernicus DEM GLO-90 / Open-Meteo" });
  expect(cachedElevation({ ...che, name: "Different route" })).toBeNull();
  expect(cachedElevation({ ...che, route_coordinates: che.route_coordinates.slice(1) })).toBeNull();
  const partial = trails.filter(t => t.provenance.mapping.navigation_ready === false);
  expect(partial).toHaveLength(8);
  partial.forEach(t => expect(cachedElevation(t)).toBeNull());
});

test("independent published-fact scenarios pass without network, labels or database reads", async () => {
  const network = jest.spyOn(global, "fetch").mockRejectedValue(new Error("Network forbidden"));
  try {
    const report = await runValidation();
    expect(report.scenariosPassed).toBe(12);
    expect(report.catalog).toEqual({ records: 51, withoutSources: 0, partiallyVerified: 9,
      unconfirmedTotalDuration: 9, newRecomputableDemProfiles: 11, missingAscentReferences: 8, historicalAscentReferences: 32 });
    expect(report.evaluationType).toBe("functional_conformance_with_documented_catalog");
    expect(network).not.toHaveBeenCalled();
  } finally { network.mockRestore(); }
});
