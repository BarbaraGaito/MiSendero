// Verify retained evidence and compare independent executions without rerunning tests.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const digest = filename => crypto.createHash('sha256').update(fs.readFileSync(filename)).digest('hex');
const json = filename => JSON.parse(fs.readFileSync(filename, 'utf8'));
const directories = process.argv.slice(2).map(directory => path.resolve(directory));
assert(directories.length, 'Usage: node testing/functional/verify.cjs <run-directory> [<repeat-directory>]');
const executions = directories.map(directory => {
  for (const record of json(path.join(directory, 'evidence-manifest.json'))) {
    assert.equal(digest(path.join(directory, record.file)), record.sha256, `Evidence changed: ${record.file}`);
  }
  const manifest = json(path.join(directory, 'source-manifest.json'));
  for (const record of manifest) assert.equal(digest(path.join(root, record.file)), record.sha256, `Source differs from execution: ${record.file}`);
  const summary = json(path.join(directory, 'summary.json'));
  const matrix = json(path.join(directory, 'matrix.json'));
  assert.equal(matrix.length, 15);
  const assertions = [];
  for (const { component, evidence } of summary.sourceReports) {
    const report = json(path.join(directory, evidence));
    assert.equal(report.numPassedTests, summary.totals[component].passed);
    assert.equal(report.numFailedTests, summary.totals[component].failed);
    for (const suite of report.testResults) for (const test of suite.assertionResults) {
      assertions.push(`${component}:${path.relative(root, suite.name).replaceAll('\\', '/')}:${test.fullName}:${test.status}`);
    }
  }
  for (const row of matrix) for (const selection of row.automated.selections) {
    assert(selection.matched.length, `Missing assertion evidence: ${row.id} / ${selection.title}`);
  }
  const coverage = json(path.join(directory, 'coverage-summary.json'));
  assert.equal(coverage.integrity.complete, true);
  console.log(JSON.stringify({ directory: path.relative(root, directory), integrity: 'verified', totals: summary.totals, scenarios: summary.automatedCases }));
  return { assertions: assertions.sort(), coverage: Object.fromEntries(['lines', 'statements', 'branches', 'functions'].map(metric => [metric, coverage.combined[metric]])), manifest };
});
if (executions.length > 1) for (const execution of executions.slice(1)) {
  assert.deepEqual(execution.assertions, executions[0].assertions, 'Assertion outcomes differ between runs');
  assert.deepEqual(execution.coverage, executions[0].coverage, 'Coverage counters differ between runs');
  assert.deepEqual(execution.manifest, executions[0].manifest, 'Source inputs differ between runs');
}
if (executions.length > 1) console.log('Independent runs: identical assertion outcomes, coverage counters and source hashes.');
