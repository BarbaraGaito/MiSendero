const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { root } = require("./coverage-scope.cjs");
const output = path.resolve(root, process.argv.find((arg) => arg.startsWith("--output="))?.slice(9) || "coverage");
fs.mkdirSync(output, { recursive: true });
fs.writeFileSync(path.join(output, "environment.json"), JSON.stringify(require("./coverage-environment.cjs")(root), null, 2) + "\n");
let failed = false;
for (const component of ["client", "backend"]) {
  const cwd = component === "client" ? root : path.join(root, "backend");
  const directory = path.join(output, component);
  fs.mkdirSync(directory, { recursive: true });
  // A crashed run must never reuse another execution's successful evidence.
  for (const file of ["test-results.json", "coverage-summary.json", "coverage-final.json", "lcov.info"]) {
    fs.rmSync(path.join(directory, file), { force: true });
  }
  const jest = require.resolve("jest/bin/jest", { paths: [cwd] });
  const args = [jest, "--coverage", "--runInBand", "--json", `--outputFile=${path.join(directory, "test-results.json")}`,
    `--coverageDirectory=${directory}`, ...process.argv.filter((arg) => /^--(?:randomize|seed=|showSeed)/.test(arg))];
  const result = spawnSync(process.execPath, args, { cwd, stdio: "inherit", env: { ...process.env, TZ: "UTC" } });
  if (result.status !== 0) failed = true;
}
const report = require("./summarize-coverage.cjs");
const summary = report(output);
// Requirement RNF-11 is a weighted line-coverage gate across the declared scope.
// Branches, functions and statements remain visible and do not inherit this claim.
if (failed || !require("./coverage-policy.cjs")(summary)) process.exitCode = 1;
