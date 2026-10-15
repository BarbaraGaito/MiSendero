const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const root = path.resolve(__dirname, "..");
const pythonDir = path.join(root, "training", "python");
const candidates = process.platform === "win32"
  ? [path.join(root, ".venv-ai", "Scripts", "python.exe"), "C:\\Windows\\py.exe"]
  : [path.join(root, ".venv-ai", "bin", "python"), "/usr/bin/python3"];
const python = candidates.find((candidate) => fs.existsSync(candidate));
if (!python) throw new Error("Install Python and training/python/requirements.txt in .venv-ai first.");
const args = process.argv.slice(2);
let command;
if (args[0] === "--prepare") command = [path.join(pythonDir, "prepare_public.py")];
else if (args[0] === "--fetch") command = [path.join(pythonDir, "fetch_public.py"), ...args.slice(1)];
else if (args[0] === "--test") command = ["-m", "unittest", "discover", "-s", pythonDir, "-p", "test_*.py", "-v"];
else if (args[0] === "--validate") command = [path.join(pythonDir, "validate_public.py")];
else command = [path.join(pythonDir, "train_public.py"), ...args];
// Research forests use native public labels and are never copied over the
// app's old low/medium/high models. Their metrics declare scope and limitations.
execFileSync(python, command, { cwd: root, stdio: "inherit" });
