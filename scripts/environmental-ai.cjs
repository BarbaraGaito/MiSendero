const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const root = path.resolve(__dirname, "..");
const candidates = process.platform === "win32"
  ? [path.join(root, ".venv-ai/Scripts/python.exe"), "C:/Windows/py.exe"]
  : [path.join(root, ".venv-ai/bin/python"), "/usr/bin/python3"];
const python = candidates.find((p) => fs.existsSync(p));
if (!python) throw new Error("Install training/python/requirements-environmental.txt in .venv-ai");
const [command = "audit", ...args] = process.argv.slice(2);
const run = (file, extra = []) => execFileSync(python, [path.join(root, "training/python", file), ...extra], { cwd: root, stdio: "inherit" });
if (command === "audit") {
  execFileSync(process.execPath, [path.join(root, "backend/scripts/exportEnvironmentalGeography.js")], { cwd: root, stdio: "inherit" });
  run("environmental_sources.py", args); run("describe_environmental_data.py"); run("audit_environmental_access.py");
} else if (command === "train") run("train_environmental.py", args);
else if (command === "fire-fetch") {
  execFileSync(process.execPath, [path.join(root, "backend/scripts/exportEnvironmentalGeography.js")], { cwd: root, stdio: "inherit" });
  run("fire_sources.py", args);
}
else if (command === "fire-validate") run("audit_fire_results.py", args);
else if (command === "fire-test") execFileSync(python, ["-m", "unittest", "discover", "-s", "training/python", "-p", "test_fire_data.py", "-v"], { cwd: root, stdio: "inherit" });
else if (command === "validate") run("audit_environmental_results.py", args);
else if (command === "predict") {
  run("predict_environmental.py", args);
  run("predict_fire.py");
  execFileSync(process.execPath, [path.join(root, "backend/scripts/exportEnvironmentalSnapshots.js")], { cwd: root, stdio: "inherit" });
}
else if (command === "test") execFileSync(python, ["-m", "unittest", "discover", "-s", "training/python", "-p", "test_environmental.py", "-v"], { cwd: root, stdio: "inherit" });
else throw new Error("Use audit, fire-fetch, fire-test, fire-validate, train, validate, predict or test");
