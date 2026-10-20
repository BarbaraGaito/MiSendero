// Read-only export from the catalog, never users/activities or production writes.
const fs = require("fs");
const path = require("path");
const { createHash } = require("crypto");
const { z } = require("zod");
const { verifiedCatalog } = require("../dist/ai/catalog");
const { compatibleCandidates, destinationMatches, normalize, resolveDestination } = require("../dist/ai/catalog");
const { destinationIsSafe } = require("../dist/ai/assistant");
const { preferencesSchema } = require("../dist/ai/schemas");
const { featureSpec, featuresFor } = require("../dist/ai/features");
const { cachedElevation } = require("../src/trailElevation");
const digest = (text) => createHash("sha256").update(text).digest("hex");
const anonymousId = z.string().regex(/^[A-Za-z0-9_-]{8,80}$/);
const labelSchema = z.object({ queryId: anonymousId, splitGroupId: anonymousId,
  preferences: preferencesSchema.extend({ experience: z.enum(["principiante", "intermedio", "avanzado"]) }), trailId: z.number().int().positive(), relevance: z.number().int().min(0).max(3),
  source: z.enum(["expert_judgment", "consented_user_rating"]), consentVerified: z.literal(true),
  synthetic: z.literal(false), completeCandidateSet: z.literal(true) }).strict();

function prepareLabels(labels, candidates) {
  const queries = new Map();
  for (const raw of labels) {
    const row = labelSchema.parse(raw);
    if (!destinationIsSafe(row.preferences.destination)) throw new Error("Invalid preference destination");
    const preferences = { ...row.preferences, destination: normalize(row.preferences.destination), trailTypes: [...row.preferences.trailTypes].sort((a, b) => a.localeCompare(b, "en")) };
    const resolved = resolveDestination(candidates, preferences.destination);
    if (resolved.suggestions.length) throw new Error("Ambiguous preference destination");
    // Aliases of the same catalog area must share a holdout group.
    const area = candidates.filter((c) => destinationMatches(c, resolved.destination)).map((c) => c.trailId).sort((a, b) => a - b);
    const preferenceKey = digest(JSON.stringify({ ...preferences, destination: area }));
    let query = queries.get(row.queryId);
    if (!query) { query = { preferenceKey, splitGroupId: row.splitGroupId, eligible: compatibleCandidates(candidates, preferences), rows: [] }; queries.set(row.queryId, query); }
    if (query.preferenceKey !== preferenceKey || query.splitGroupId !== row.splitGroupId) throw new Error("Inconsistent query preferences/group");
    const candidate = query.eligible.find((c) => c.trailId === row.trailId);
    if (!candidate || query.rows.some((r) => r.trailId === row.trailId)) throw new Error("Duplicate, missing, or incompatible catalog candidate");
    query.rows.push({ queryId: row.queryId, splitGroupId: row.splitGroupId, preferenceKey, trailId: row.trailId,
      features: featuresFor(preferences, candidate), relevance: row.relevance, source: row.source,
      consentVerified: true, synthetic: false, eligible: true });
  }
  for (const query of queries.values()) if (query.rows.length !== query.eligible.length) throw new Error("Every eligible candidate must be explicitly judged; unchosen trails are not negative labels");
  return [...queries.values()].flatMap((q) => q.rows).sort((a, b) => a.queryId.localeCompare(b.queryId) || a.trailId - b.trailId);
}
async function main() {
  const args = process.argv.slice(2);
  if (args.length && (args.length !== 2 || args[0] !== "--labels")) throw new Error("Usage: prepareTrailRanking.js [--labels path/to/consented-labels.jsonl]");
  require("dotenv").config({ path: path.resolve(__dirname, "../.env"), quiet: true });
  const pool = await require("../src/db").getPool();
  try {
    const rows = (await pool.query("SELECT * FROM trails ORDER BY id")).rows;
    const candidates = verifiedCatalog(rows.map((r) => ({ ...r, verified_ascent_m: cachedElevation(r)?.ascent_m ?? null })));
    const tables = (await pool.query("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")).rows.map((r) => r.table_name);
    const audit = { exportedAt: new Date().toISOString(), catalogRecords: rows.length, eligibleRecords: candidates.length,
      excludedRecords: rows.length - candidates.length, withProvenance: rows.filter((r) => r.provenance?.sources?.length).length,
      catalogOnlyRecords: candidates.filter(c => c.catalogVerification === "catalog_only").length,
      withUnconfirmedDurationScope: candidates.filter(c => c.durationScopeVerified === false).length,
      withDocumentedTerrain: candidates.filter((c) => c.terrain != null).length,
      withAscentReference: candidates.filter((c) => c.ascentM != null).length,
      preferenceOrRankingTables: tables.filter((t) => /recommend|preference|relevance|ranking/.test(t)),
      labeledQueriesAvailable: 0, labeledQueriesNote: "No preference/relevance collection exists in this application; catalog attributes are not relevance labels.",
      featureSchemaVersion: featureSpec.version };
    const directory = path.resolve(__dirname, "../../training/data/trail-ranking");
    fs.mkdirSync(directory, { recursive: true });
    let labels = [];
    if (args.length) {
      if (fs.statSync(args[1]).size > 100 * 1024 * 1024) throw new Error("Labels file too large");
      labels = fs.readFileSync(args[1], "utf8").split(/\r?\n/).filter((l) => l.trim()).map((l) => JSON.parse(l));
    }
    const prepared = prepareLabels(labels, candidates);
    audit.labeledQueriesAvailable = new Set(prepared.map((r) => r.queryId)).size;
    audit.labeledRowsPrepared = prepared.length;
    const catalogText = JSON.stringify({ schemaVersion: 1, audit, candidates }, null, 2) + "\n";
    fs.writeFileSync(path.join(directory, "catalog.json"), catalogText);
    const privateDir = path.join(directory, "prepared");
    fs.mkdirSync(privateDir, { recursive: true });
    const examples = prepared.map((r) => JSON.stringify(r)).join("\n") + (prepared.length ? "\n" : "");
    fs.writeFileSync(path.join(privateDir, "examples.jsonl"), examples);
    fs.writeFileSync(path.join(privateDir, "manifest.json"), JSON.stringify({ schemaVersion: 1,
      featureSchemaVersion: featureSpec.version, featureNames: featureSpec.names,
      preparationCodeSha256: digest([__filename, path.resolve(__dirname, "../src/ai/catalog.ts"), path.resolve(__dirname, "../src/ai/features.ts"), path.resolve(__dirname, "../src/ai/schemas.ts")].map((file) => fs.readFileSync(file, "utf8")).join("\n")),
      catalogSha256: digest(catalogText), examplesSha256: digest(examples), catalogSize: candidates.length,
      synthetic: false, completeCandidateJudgments: true, rowCount: prepared.length }, null, 2) + "\n");
    console.log(JSON.stringify(audit, null, 2));
  } finally { await pool.end(); }
}
module.exports = { prepareLabels };
if (require.main === module) main().catch((error) => { console.error(error.code ? `Catalog export failed (${error.code})` : "Catalog export failed; check configuration and build first."); process.exitCode = 1; });
