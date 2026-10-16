// Research code has a separate denominator and a different instrumentation engine.
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const root = path.resolve(__dirname, "..");
const python = process.env.PYTHON_COVERAGE_EXECUTABLE || path.join(root, ".venv-ai", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const directory = path.join(root, "coverage", "python");
fs.mkdirSync(directory, { recursive: true });
const env = { ...process.env, TZ: "UTC", PYTHONHASHSEED: "0", COVERAGE_FILE: path.join(directory, ".coverage") };
const commands = [
  ["run", "--rcfile=testing/python-coverage.ini", "-m", "unittest", "discover", "-s", "training/python", "-p", "test_*.py", "-v"],
  ["json", "--rcfile=testing/python-coverage.ini", "-o", path.join(directory, "coverage.json")],
  ["xml", "--rcfile=testing/python-coverage.ini", "-o", path.join(directory, "coverage.xml")],
  ["html", "--rcfile=testing/python-coverage.ini", "-d", path.join(directory, "html")],
  ["report", "--rcfile=testing/python-coverage.ini"],
];
let failed = false;
for (const args of commands) {
  const result = spawnSync(python, ["-m", "coverage", ...args], { cwd: root, env, encoding: "utf8" });
  const output = `${result.stdout || ""}${result.stderr || ""}`;
  process.stdout.write(output);
  fs.appendFileSync(path.join(directory, "execution.log"), `${JSON.stringify([python, "-m", "coverage", ...args])}\n${output}\nexit=${result.status}\n`);
  if (result.error || result.status !== 0) { failed = true; break; }
}
if (failed) process.exitCode = 1;
