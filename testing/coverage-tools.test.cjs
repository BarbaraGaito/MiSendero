const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const summarize = require("./summarize-coverage.cjs");
const coveragePath = require("./coverage-paths.cjs");
const accepts = require("./coverage-policy.cjs");
test("coverage sums disjoint counters rather than averaging percentages and detects omitted source files", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "misendero-coverage-"));
  const measures = (covered, total) => Object.fromEntries(["lines", "statements", "branches", "functions"].map((key) => [key, { total, covered, skipped: 0, pct: 100 * covered / total }]));
  try {
    const output = path.join(root, "coverage");
    fs.mkdirSync(output);
    fs.writeFileSync(path.join(output, "environment.json"), JSON.stringify({ lock_matches: true }));
    const scope = { root, client: ["client.js", "unimported.js"], backend: ["backend.js"] };
    for (const file of [...scope.client, ...scope.backend]) fs.writeFileSync(path.join(root, file), "module.exports = 1;\n");
    for (const [component, file, covered, total] of [["client", "client.js", 9, 10], ["backend", "backend.js", 40, 100]]) {
      fs.mkdirSync(path.join(output, component));
      fs.writeFileSync(path.join(output, component, "coverage-summary.json"), JSON.stringify({ total: measures(covered, total), [path.join(root, file)]: measures(covered, total) }));
      fs.writeFileSync(path.join(output, component, "coverage-final.json"), "{}");
      fs.writeFileSync(path.join(output, component, "lcov.info"), `TN:\nSF:${file}\nDA:1,1\nend_of_record\n`);
      fs.writeFileSync(path.join(output, component, "test-results.json"), JSON.stringify({ numTotalTestSuites: 1, numPassedTests: 2, numFailedTests: 0, numPendingTests: 0, success: true }));
    }
    let report = summarize(output, scope); assert.equal(report.integrity.complete, false); assert.equal(report.integrity.missing[0].file, "unimported.js"); assert.equal(accepts(report), false);
    assert.deepEqual(report.environment, { lock_matches: true });
    const filename = path.join(output, "client", "coverage-summary.json"), imported = JSON.parse(fs.readFileSync(filename));
    imported[path.join(root, "unimported.js")] = measures(0, 100); fs.writeFileSync(filename, JSON.stringify(imported));
    report = summarize(output, scope); assert.equal(report.integrity.complete, true); assert.equal(report.combined.lines.covered, 49); assert.equal(report.combined.lines.total, 210); assert.equal(report.combined.lines.pct, 23.3333); assert.equal(accepts(report), false);
    assert.ok(fs.readFileSync(path.join(output, "modules.csv"), "utf8").includes("unimported.js")); assert.equal(report.inventory[0].sha256.length, 64);
    assert.ok(fs.readFileSync(path.join(output, "lcov.info"), "utf8").includes("SF:backend/backend.js"));
    assert.ok(fs.readFileSync(path.join(output, "index.html"), "utf8").includes("unimported.js"));
  } finally {
    assert.equal(path.dirname(path.resolve(root)), path.resolve(os.tmpdir()));
    assert.ok(path.basename(root).startsWith("misendero-coverage-"));
    fs.rmSync(root, { recursive: true, force: true });
  }
});

function temporaryRepository(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "misendero-coverage-paths-"));
  t.after(() => {
    assert.equal(path.dirname(path.resolve(root)), path.resolve(os.tmpdir()));
    assert.ok(path.basename(root).startsWith("misendero-coverage-paths-"));
    fs.rmSync(root, { recursive: true, force: true });
  });
  fs.mkdirSync(path.join(root, "coverage"));
  return root;
}

test("coverage paths allow relative and absolute destinations under coverage, including new subdirectories", (t) => {
  const root = temporaryRepository(t);
  const expected = path.join(root, "coverage", "repeat", "summary.json");
  assert.equal(coveragePath(path.join("coverage", "repeat", "summary.json"), root), expected);
  assert.equal(coveragePath(expected, root), expected);
});

test("coverage aggregation refuses absolute, parent traversal and sibling-prefix escapes before reading reports", (t) => {
  const root = temporaryRepository(t);
  const scope = { root, client: [], backend: [] };
  for (const output of [root, path.join(root, "outside"), path.join(root, "coverage", "..", "outside"),
    path.join(root, "coverage-other"), path.join("coverage", "..", "outside")]) {
    assert.throws(() => summarize(output, scope), /Coverage path must stay inside/);
  }
  assert.equal(fs.existsSync(path.join(root, "outside")), false);
});

test("coverage paths reject directory links, including a redirected coverage root", (t) => {
  const root = temporaryRepository(t);
  const outside = path.join(root, "outside");
  fs.mkdirSync(outside);
  const output = path.join(root, "coverage", "linked");
  fs.symlinkSync(outside, output, process.platform === "win32" ? "junction" : "dir");
  assert.throws(() => summarize(output, { root, client: [], backend: [] }), /Coverage path must not contain symbolic links/);
  if (process.platform === "win32") fs.rmdirSync(output);
  else fs.unlinkSync(output);
  fs.rmdirSync(path.join(root, "coverage"));
  fs.symlinkSync(outside, path.join(root, "coverage"), process.platform === "win32" ? "junction" : "dir");
  assert.throws(() => coveragePath("coverage/new/report.json", root), /Coverage path must not contain symbolic links/);
  assert.deepEqual(fs.readdirSync(outside), []);
});

test("coverage aggregation rejects internal file links, including dangling destinations", (t) => {
  const root = temporaryRepository(t);
  const outside = path.join(root, "outside.json");
  fs.writeFileSync(outside, "{\"preserved\":true}");
  const output = path.join(root, "coverage");
  for (const filename of ["environment.json", "summary.json", "lcov.info", "modules.csv", "index.html",
    "client/coverage-summary.json", "backend/coverage-final.json"]) {
    const link = path.join(output, filename);
    fs.mkdirSync(path.dirname(link), { recursive: true });
    for (const target of [outside, path.join(root, "missing.json")]) {
      try {
        fs.symlinkSync(target, link, "file");
      } catch (error) {
        if (["EPERM", "EACCES", "ENOSYS"].includes(error.code)) {
          t.skip("OS does not permit file symbolic links; directory junctions are tested separately");
          return;
        }
        throw error;
      }
      assert.throws(() => summarize(output, { root, client: [], backend: [] }), /Coverage path must not contain symbolic links/);
      fs.unlinkSync(link);
    }
  }
  assert.equal(fs.readFileSync(outside, "utf8"), "{\"preserved\":true}");
  assert.equal(fs.existsSync(path.join(root, "missing.json")), false);
});

test("all internal report paths are checked for links before data I/O", (t) => {
  const root = temporaryRepository(t);
  const output = path.join(root, "coverage");
  const originalLstat = fs.lstatSync;
  let redirected;
  t.mock.method(fs, "lstatSync", (filename, options) => filename === redirected
    ? { isSymbolicLink: () => true } : originalLstat(filename, options));
  for (const filename of ["environment.json", "summary.json", "lcov.info", "modules.csv", "index.html",
    ...["client", "backend"].flatMap(component => ["coverage-summary.json", "test-results.json", "lcov.info", "coverage-final.json"]
      .map(file => `${component}/${file}`))]) {
    redirected = path.join(output, filename);
    assert.throws(() => summarize(output, { root, client: [], backend: [] }), /Coverage path must not contain symbolic links/);
  }
});

test("both coverage CLIs reject external output without creating evidence", (t) => {
  const root = temporaryRepository(t);
  const outside = path.join(root, "outside");
  for (const [script, argument] of [["summarize-coverage.cjs", outside], ["run-coverage.cjs", `--output=${outside}`]]) {
    const result = spawnSync(process.execPath, [path.join(__dirname, script), argument], { encoding: "utf8", timeout: 10000 });
    assert.equal(result.error, undefined);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /Coverage path must stay inside/);
    assert.equal(fs.existsSync(outside), false);
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
