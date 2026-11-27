const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
function run(args = process.argv.slice(2)) {
  const python = path.join(root, ".venv-ai", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  if (!fs.existsSync(python)) throw new Error("Prepará .venv-ai con training/python/requirements-public.lock.txt.");
  if (!["prepare", "select", "evaluate", "validate"].includes(args[0])) throw new Error("Uso: npm run ai:field -- prepare|select|evaluate|validate [--run v1]");
  const result = spawnSync(python, [path.join(root, "training/python/field_ai.py"), ...args], { cwd: root, stdio: "inherit", env: { ...process.env, PYTHONUTF8: "1" } });
  if (result.error) throw result.error;
  return result.status ?? 1;
}
if (require.main === module) process.exitCode = run();
module.exports = { run };
