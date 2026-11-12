// Reproducible functional validation against real repository records and reviewed sources.
// This is not a satisfaction study, a trained model evaluation or a production DB audit.
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const { recommendTrail } = require("../dist/ai/assistant");
const { verifiedCatalog } = require("../dist/ai/catalog");
const legacy = require("../src/data/legacyTrails");
const additional = require("../src/data/additionalTrails");
const { trails } = require("../src/data/catalogExpansion20261017");
const { applyReviewedFacts } = require("../src/data/reviewedTrailFacts");
const { trails: beginnerTrails, reviewCerroLeoncito } = require("../src/data/beginnerCatalog20261112");
const { cachedElevation, geometryHash, sampleRoute, accumulatedElevation } = require("../src/trailElevation");
const references = require("../src/data/recommendationElevation20261021.json");
const snapshot = require("../../training/data/trail-ranking/catalog.json");

function repositoryRows({ includeBeginner = true } = {}) {
  const baseline = [...legacy.map(applyReviewedFacts), ...additional, ...trails].map(t => {
    const previous = snapshot.candidates.find(c => c.name === t.name);
    assert.ok(previous, `No real snapshot ID for ${t.name}`);
    return { ...t, id: previous.trailId,
      verified_ascent_m: cachedElevation(t)?.ascent_m ?? previous.ascentM ?? null };
  });
  if (!includeBeginner) return baseline;
  // The old export predates this batch. Preview IDs are only used by the local audit;
  // the real database assigns IDs itself and preserves the earlier ones.
  const maxId = Math.max(...snapshot.candidates.map(c => c.trailId));
  return [...baseline.map(reviewCerroLeoncito), ...beginnerTrails.map((trail, i) => ({ ...trail, id: maxId + i + 1 }))];
}

function validateElevationEvidence() {
  for (const [key, record] of Object.entries(references.entries)) {
    const trail = trails.find(t => t.provenance.catalog_key === key);
    assert.ok(trail?.provenance.mapping.navigation_ready, `Incomplete trace: ${key}`);
    assert.equal(record.name, trail.name);
    assert.equal(record.geometrySource, trail.provenance.mapping.source_url);
    assert.equal(record.basis, "dem_estimate");
    const e = record.elevation;
    assert.equal(e.geometry_hash, geometryHash(trail));
    assert.equal(e.source_url, "https://open-meteo.com/en/docs/elevation-api");
    assert.ok(Number.isFinite(Date.parse(e.fetched_at)));
    assert.equal(e.resolution_m, 90);
    assert.equal(e.noise_threshold_m, 5);
    const { samples } = sampleRoute(trail.route_coordinates);
    assert.equal(e.points.length, samples.length);
    samples.forEach((sample, index) => {
      const actual = e.points[index];
      assert.equal(actual.latitude, sample.latitude);
      assert.equal(actual.longitude, sample.longitude);
      assert.equal(actual.distance_m, Math.round(sample.distance_m * 10) / 10);
      assert.ok(Number.isFinite(actual.elevation_m));
    });
    assert.deepEqual(accumulatedElevation(e.points.map(p => p.elevation_m)), { ascent_m: e.ascent_m, descent_m: e.descent_m });
  }
  const expected = trails.filter(t => t.provenance.mapping.navigation_ready === true);
  assert.equal(Object.keys(references.entries).length, expected.length);
  return expected.length;
}

async function runValidation() {
  // Reproduce the original documented source-conformance suite on its original catalog.
  const rows = repositoryRows({ includeBeginner: false });
  const catalog = verifiedCatalog(rows);
  assert.equal(catalog.length, rows.length);
  const results = [];
  const p = { destination: "Corrientes", trailTypes: ["cualquiera"], duration: "cualquiera", difficulty: "cualquiera", experience: "avanzado" };
  async function check(id, expected, sourceUrls, preferences, subset, verify) {
    const actual = await recommendTrail({ ...p, ...preferences }, subset || rows);
    verify(actual);
    results.push({ id, expected, sourceUrls, preferences: { ...p, ...preferences },
      actual: { status: actual.status, trailId: actual.recommendation?.trailId ?? null, name: actual.recommendation?.name ?? null }, passed: true });
  }
  const source = key => trails.find(t => t.provenance.catalog_key === key).provenance.sources.map(s => s.url);
  await check("published-time-and-grade", "Che Roga: 4.4 km, 150 min, media; exact requested window and difficulty", source("mburucuya-che-roga"),
    { duration: "2-4", difficulty: "moderada", experience: "intermedio" }, null, r => {
      assert.equal(r.recommendation.name, "Sendero Che Roga - Mburucuyá");
      assert.equal(r.recommendation.distanceKm, 4.4); assert.equal(r.recommendation.durationMinutes, 150);
      assert.equal(r.recommendation.difficulty, "moderada"); assert.equal(r.recommendation.preferenceAdjustments, undefined);
    });
  await check("essential-time-before-landscape", "Tapé Porá fits 1–2 h and beginner; requested lakes and media must be disclosed as mismatches", source("mburucuya-tape-pora"),
    { trailTypes: ["lagos"], duration: "1-2", difficulty: "moderada", experience: "principiante" }, null, r => {
      assert.equal(r.recommendation.name, "Histórico Tapé Porá - Mburucuyá"); assert.equal(r.recommendation.durationMinutes, 60);
      assert.equal(r.recommendation.difficulty, "facil"); assert.ok(r.recommendation.preferenceAdjustments.length >= 2);
    });
  const lah = rows.filter(t => t.name === "Lahuan Solitario - Puerto Chucao");
  await check("published-round-trip", "Lahuán: APN 90 min round trip, low difficulty, 1.5 km one way = 3 km return itinerary", lah[0].provenance.sources.map(s => s.url),
    { destination: "Chubut", duration: "1-2", difficulty: "facil", experience: "principiante" }, lah, r => {
      assert.equal(r.recommendation.durationMinutes, 90); assert.equal(r.recommendation.distanceKm, 3);
      assert.equal(r.recommendation.durationScopeVerified, true); assert.equal(r.recommendation.routeType, "out_and_back");
    });
  const morado = rows.filter(t => t.name === "Caminata al Cerro Morado");
  await check("total-time-with-unknown-route-shape", "Cerro Morado: 3 h for full itinerary, 5.73 km, alta; do not infer a loop", morado[0].provenance.sources.map(s => s.url),
    { destination: "San Juan", duration: "2-4", difficulty: "dificil" }, morado, r => {
      assert.equal(r.recommendation.durationScopeVerified, true); assert.equal(r.recommendation.durationMinutes, 180);
      assert.equal(r.recommendation.distanceKm, 5.73); assert.equal(r.recommendation.routeType, "unknown");
      assert.ok(r.recommendation.explanation.includes("recorrido completo"));
    });
  const confluencia = rows.filter(t => t.name === "Sendero a Confluencia");
  await check("conflicting-official-times", "Conflicting official 4–5 h and 6–8 h cannot become an exact 4–6 h match", confluencia[0].provenance.sources.map(s => s.url),
    { destination: "Mendoza", duration: "4-6", difficulty: "moderada", experience: "intermedio" }, confluencia, r => {
      assert.equal(r.recommendation.durationScopeVerified, false);
      assert.equal(r.recommendation.catalogVerification, "partial");
      assert.ok(r.recommendation.dataWarnings.some(w => w.includes("difieren")));
      assert.ok(r.recommendation.preferenceAdjustments.length);
    });
  const tesoro = rows.filter(t => t.name === "Laguna del Tesoro - Aconquija");
  await check("one-way-source-is-not-total-time", "Tesoro: intermediate difficulty; 6 h one way does not verify the old total duration", tesoro[0].provenance.sources.map(s => s.url),
    { destination: "Tucumán", duration: "mas-6", difficulty: "moderada", experience: "intermedio" }, tesoro, r => {
      assert.equal(r.recommendation.difficulty, "moderada"); assert.equal(r.recommendation.durationScopeVerified, false);
      assert.ok(r.recommendation.dataWarnings.some(w => w.includes("6 h hasta la laguna")));
    });
  await check("geography-preserved", "A short forest request in Bariloche must not silently move to El Bolsón", [],
    { destination: "Bariloche", trailTypes: ["bosques"], duration: "menos-1" }, null, r => {
      assert.ok(r.recommendation.location.includes("Bariloche") || r.recommendation.name.includes("Frey"));
      assert.ok(!r.recommendation.location.includes("Bolsón"));
    });
  await check("typo-needs-confirmation", "Barilcohe asks to clarify; no automatic change to Bariloche", [],
    { destination: "Barilcohe" }, null, r => { assert.equal(r.status, "clarification"); assert.equal(r.recommendation, null); });
  await check("absent-place", "An absent destination returns no fabricated trail", [],
    { destination: "Atlantis" }, null, r => { assert.equal(r.status, "no_results"); assert.equal(r.recommendation, null); });
  await check("ambiguous-destination", "Argentina requires a more precise destination", [],
    { destination: "Argentina" }, null, r => { assert.equal(r.status, "clarification"); });
  const demanding = rows.filter(t => t.provenance?.catalog_key === "lanin-cara-sur-puerto-canoa");
  await check("profile-overrun-disclosed", "A beginner with only a demanding local trail receives an explicit profile warning", source("lanin-cara-sur-puerto-canoa"),
    { destination: "Neuquén", experience: "principiante", difficulty: "facil" }, demanding, r => {
      assert.equal(r.recommendation.difficulty, "dificil");
      assert.ok(r.recommendation.preferenceAdjustments.some(w => w.includes("supera ese nivel")));
      assert.ok(!r.recommendation.explanation.includes("Está dentro del nivel"));
    });
  await check("partial-geometry-keeps-missing-ascent", "Incomplete Tapé Porá geometry cannot acquire a full-route ascent", source("mburucuya-tape-pora"),
    { duration: "1-2", difficulty: "facil", experience: "principiante" }, null, r => {
      assert.equal(r.recommendation.name, "Histórico Tapé Porá - Mburucuyá"); assert.equal(r.recommendation.ascentM, null);
    });
  return { schemaVersion: 1, evaluatedAt: new Date().toISOString(), runtime: { node: process.version, platform: process.platform }, evaluationType: "functional_conformance_with_documented_catalog",
    dataScope: "Repository definitions; IDs and historical ascent references from the 2026-10-18 local export. No RDS access.",
    catalog: { records: catalog.length, withoutSources: catalog.filter(c => !c.sources.length).length,
      partiallyVerified: catalog.filter(c => c.catalogVerification === "partial").length,
      unconfirmedTotalDuration: catalog.filter(c => !c.durationScopeVerified).length,
      newRecomputableDemProfiles: validateElevationEvidence(), missingAscentReferences: catalog.filter(c => c.ascentM == null).length,
      historicalAscentReferences: snapshot.candidates.filter(c => c.ascentM != null).length },
    scenariosPassed: results.length, scenarios: results,
    pendingDocumentation: rows.filter(t => t.provenance?.review?.unconfirmed_fields.length).map(t => ({ name: t.name,
      unconfirmedFields: t.provenance.review.unconfirmed_fields, finding: t.provenance.review.finding,
      sources: t.provenance.sources })),
    pendingElevation: trails.filter(t => !t.provenance.mapping.navigation_ready).map(t => ({ name: t.name,
      reason: "Partial geometry: do not extrapolate a full-route ascent", geometrySource: t.provenance.mapping.source_url })),
    limitations: ["Scenarios are deterministic functional checks, not sampled human observations or training labels.",
      "Passing checks does not demonstrate satisfaction, physical suitability, clinical safety or field accuracy.",
      "Profile matching, priority order and shorter-route tie breaking remain explicit, unvalidated product policies.",
      "DEM values are estimates over the stored geometry, not field measurements or GPS altitude samples.",
      "A source confirming a destination does not verify missing attributes of its trail."] };
}
async function main() {
  const report = await runValidation();
  const inputs = ["backend/src/ai/assistant.ts", "backend/src/ai/catalog.ts", "backend/src/ai/schemas.ts", "backend/src/ai/contracts.ts",
    "backend/src/trailElevation.js", "backend/src/data/reviewedTrailFacts.js", "backend/src/data/additionalTrails.js", "backend/src/data/reviewedTrailFacts20261021.json",
    "backend/src/data/recommendationElevation20261021.json", "backend/src/data/legacyTrails.js", "backend/src/data/additionalTrailDefinitions.js",
    "backend/src/data/additionalTrailRoutes.json", "backend/src/data/catalogExpansion20261017.js", "backend/src/data/catalogExpansionRoutes20261017.json",
    "backend/src/data/realTrailRoutes.js", "training/data/trail-ranking/catalog.json", "backend/scripts/validateCatalogRecommendations.js"];
  report.inputSha256 = Object.fromEntries(inputs.map(file => [file, crypto.createHash("sha256").update(fs.readFileSync(path.resolve(__dirname, "../..", file))).digest("hex")]));
  const directory = path.resolve(__dirname, "../../docs/catalog-validation-2026-10-21");
  fs.mkdirSync(directory, { recursive: true });
  fs.writeFileSync(path.join(directory, "results.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify({ passed: report.scenariosPassed, catalog: report.catalog, report: "docs/catalog-validation-2026-10-21/results.json" }));
}
module.exports = { repositoryRows, validateElevationEvidence, runValidation };
if (require.main === module) main().catch(e => { console.error(e.message); process.exitCode = 1; });
