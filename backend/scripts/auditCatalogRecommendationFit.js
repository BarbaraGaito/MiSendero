// Replay the current repository rules on repository data or a public API snapshot.
const { readFileSync } = require("node:fs");
const { createHash } = require("node:crypto");
const { repositoryRows } = require("./validateCatalogRecommendations");
const { planBeginnerCatalog } = require("./importBeginnerCatalog");
const { recommendTrail, destinationIsSafe } = require("../dist/ai/assistant");
const { verifiedCatalog, destinationMatches, experienceFits, candidateDurationFits, landscapeFits } = require("../dist/ai/catalog");

async function main() {
  const args = process.argv.slice(2);
  const snapshotArg = args.indexOf("--snapshot");
  const snapshotPath = snapshotArg < 0 ? null : args[snapshotArg + 1];
  const project = args.includes("--project");
  if ((snapshotArg >= 0 && !snapshotPath) || (project && !snapshotPath)) throw new Error("Use --snapshot FILE [--project]");
  const raw = snapshotPath ? readFileSync(snapshotPath) : null;
  const snapshot = raw ? JSON.parse(raw.toString("utf8")) : null;
  if (snapshot && (!Array.isArray(snapshot.rows) || !snapshot.rows.length || !snapshot.rows.every(row => Number.isSafeInteger(row.id) && row.id > 0))) {
    throw new Error("Invalid public catalog snapshot");
  }
  const baseline = snapshot ? snapshot.rows : repositoryRows({ includeBeginner: false });
  const plan = project ? planBeginnerCatalog(baseline) : null;
  const changed = new Map(plan?.durationReviews.map(({ after }) => [after.id, after]));
  const maxId = Math.max(...baseline.map(row => row.id));
  const rows = plan ? [...baseline.map(row => changed.get(row.id) ?? row), ...plan.pending.map((row, index) => ({ ...row, id: maxId + index + 1 }))]
    : snapshot || args.includes("--baseline") ? baseline : repositoryRows();
  const catalog = verifiedCatalog(rows);
  const queryCatalog = args.includes("--all-destinations") ? catalog : verifiedCatalog(baseline);
  const destinations = [...new Set(queryCatalog.map(c => c.location))].filter(destinationIsSafe).sort();
  const experiences = ["principiante", "intermedio", "avanzado"];
  const landscapes = ["naturaleza", "montaña", "cascadas", "lagos", "bosques", "miradores", "cualquiera"];
  const durations = ["menos-1", "1-2", "2-4", "4-6", "mas-6", "cualquiera"];
  const difficulties = ["facil", "moderada", "dificil", "cualquiera"];
  const cases = { total: 0, outsideDestination: 0, exact: 0, alternatives: 0, durationMismatch: 0,
    landscapeMismatch: 0, difficultyMismatch: 0, exceedsExperience: 0, adjustmentPresenceMismatch: 0, experienceFlagMismatch: 0 };
  const byExperience = {};
  const statuses = {};
  for (const experience of experiences) {
    const group = byExperience[experience] = { total: 0, exact: 0, exceedsExperience: 0, destinationsWithoutFit: [] };
    for (const destination of destinations) {
      if (!catalog.some(c => destinationMatches(c, destination) && experienceFits(c, { experience }))) {
        group.destinationsWithoutFit.push(destination);
      }
      for (const type of landscapes) for (const duration of durations) for (const difficulty of difficulties) {
        const prefs = { destination, trailTypes: [type], duration, difficulty, experience };
        const result = await recommendTrail(prefs, rows);
        cases.total++;
        group.total++;
        statuses[result.status] = (statuses[result.status] ?? 0) + 1;
        if (result.status !== "ok") continue;
        const item = result.recommendation;
        if (!destinationMatches(item, destination)) cases.outsideDestination++;
        const durationMismatch = !candidateDurationFits(item, duration);
        const landscapeMismatch = !landscapeFits(item, prefs);
        const difficultyMismatch = difficulty !== "cualquiera" && item.difficulty !== difficulty;
        const exceedsExperience = !experienceFits(item, prefs);
        const isAlternative = durationMismatch || landscapeMismatch || difficultyMismatch || exceedsExperience;
        if (isAlternative) cases.alternatives++;
        else { cases.exact++; group.exact++; }
        if (durationMismatch) cases.durationMismatch++;
        if (landscapeMismatch) cases.landscapeMismatch++;
        if (difficultyMismatch) cases.difficultyMismatch++;
        if (exceedsExperience) { cases.exceedsExperience++; group.exceedsExperience++; }
        if (isAlternative !== Boolean(item.preferenceAdjustments?.length)) cases.adjustmentPresenceMismatch++;
        if (exceedsExperience !== (item.exceedsExperience === true)) cases.experienceFlagMismatch++;
      }
    }
  }
  console.log(JSON.stringify({ scope: "Unweighted functional grid, not observed demand or satisfaction",
    input: snapshot ? { url: snapshot.url, retrievedAt: snapshot.retrievedAt, sha256: createHash("sha256").update(raw).digest("hex"),
      mode: plan ? "projected_changes_on_public_snapshot" : "public_snapshot", algorithm: "repository_checkout" } : { mode: "repository_data" },
    ...(plan ? { importProjection: { insert: plan.pending.map(row => row.name), review: plan.durationReviews.map(({ before, after }) =>
      ({ name: before.name, durationBefore: before.duration, durationAfter: after.duration, basis: after.provenance.duration_basis })) } } : {}),
    catalogRecords: catalog.length,
    durationCoverage: { knownTotal: catalog.filter(row => row.durationScopeVerified && row.routeType !== "point_to_point").length,
      knownOneWay: catalog.filter(row => row.durationScopeVerified && row.routeType === "point_to_point").length,
      unknownOrConflicting: catalog.filter(row => !row.durationScopeVerified).length,
      estimated: catalog.filter(row => row.durationScopeVerified && row.durationIsEstimated).length },
    destinations: destinations.length, statuses, cases, byExperience }, null, 2));
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
