const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const summarize = require("./summarize-coverage.cjs");
const accepts = require("./coverage-policy.cjs");
test("coverage sums disjoint counters rather than averaging percentages and detects omitted source files", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "misendero-coverage-"));
  const measures = (covered, total) => Object.fromEntries(["lines", "statements", "branches", "functions"].map((key) => [key, { total, covered, skipped: 0, pct: 100 * covered / total }]));
  try {
    const scope = { root, client: ["client.js", "unimported.js"], backend: ["backend.js"] };
    for (const file of [...scope.client, ...scope.backend]) fs.writeFileSync(path.join(root, file), "module.exports = 1;\n");
    for (const [component, file, covered, total] of [["client", "client.js", 9, 10], ["backend", "backend.js", 40, 100]]) {
      fs.mkdirSync(path.join(root, component));
      fs.writeFileSync(path.join(root, component, "coverage-summary.json"), JSON.stringify({ total: measures(covered, total), [path.join(root, file)]: measures(covered, total) }));
      fs.writeFileSync(path.join(root, component, "coverage-final.json"), "{}");
      fs.writeFileSync(path.join(root, component, "lcov.info"), `TN:\nSF:${file}\nDA:1,1\nend_of_record\n`);
      fs.writeFileSync(path.join(root, component, "test-results.json"), JSON.stringify({ numTotalTestSuites: 1, numPassedTests: 2, numFailedTests: 0, numPendingTests: 0, success: true }));
    }
    let report = summarize(root, scope); assert.equal(report.integrity.complete, false); assert.equal(report.integrity.missing[0].file, "unimported.js"); assert.equal(accepts(report), false);
    const filename = path.join(root, "client", "coverage-summary.json"), imported = JSON.parse(fs.readFileSync(filename));
    imported[path.join(root, "unimported.js")] = measures(0, 100); fs.writeFileSync(filename, JSON.stringify(imported));
    report = summarize(root, scope); assert.equal(report.integrity.complete, true); assert.equal(report.combined.lines.covered, 49); assert.equal(report.combined.lines.total, 210); assert.equal(report.combined.lines.pct, 23.3333); assert.equal(accepts(report), false);
    assert.ok(fs.readFileSync(path.join(root, "modules.csv"), "utf8").includes("unimported.js")); assert.equal(report.inventory[0].sha256.length, 64);
    assert.ok(fs.readFileSync(path.join(root, "lcov.info"), "utf8").includes("SF:backend/backend.js"));
  } finally {
    assert.equal(path.dirname(path.resolve(root)), path.resolve(os.tmpdir()));
    assert.ok(path.basename(root).startsWith("misendero-coverage-"));
    fs.rmSync(root, { recursive: true, force: true });
  }
});
test("the 85% gate uses exact counters and rejects failed, pending and empty runs", () => {
  const report = { integrity: { complete: true }, components: { client: { tests: { success: true, failed: 0, pending: 0 } } }, combined: { lines: { covered: 85, total: 100 } } };
  assert.equal(accepts(report), true); report.combined.lines = { covered: 84999, total: 100000 }; assert.equal(accepts(report), false);
  report.combined.lines = { covered: 100, total: 100 }; report.components.client.tests.pending = 1; assert.equal(accepts(report), false);
  report.components.client.tests.pending = 0; report.components.client.tests.success = false; assert.equal(accepts(report), false);
  report.components.client.tests.success = true; report.combined.lines = { covered: 0, total: 0 }; assert.equal(accepts(report), false);
  report.combined.lines = { covered: 100, total: 100 }; report.environment = { lock_matches: false }; assert.equal(accepts(report), false);
});
