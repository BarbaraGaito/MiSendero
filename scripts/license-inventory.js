// Inventory of the locked dependency graph, not a legal approval of its licences.
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const root = path.resolve(__dirname, "..");
const rows = [];
for (const scope of ["app", "backend"]) {
  const base = scope === "app" ? root : path.join(root, "backend");
  const lockPath = path.join(base, "package-lock.json");
  const bytes = fs.readFileSync(lockPath);
  const lock = JSON.parse(bytes);
  const lockHash = crypto.createHash("sha256").update(bytes).digest("hex");
  for (const [location, item] of Object.entries(lock.packages || {})) {
    if (!location || item.link) continue;
    let installed = {};
    try { installed = JSON.parse(fs.readFileSync(path.join(base, location, "package.json"), "utf8")); } catch {}
    rows.push({ scope, package: item.name || installed.name || location.split("node_modules/").pop(), version: item.version,
      license: item.license || installed.license || "REQUIERE_REVISION", development: !!item.dev,
      resolved: item.resolved || "", integrity: item.integrity || "", location, lock_sha256: lockHash });
  }
}
const columns = ["scope", "package", "version", "license", "development", "resolved", "integrity", "location", "lock_sha256"];
const csv = [columns.join(","), ...rows.map((row) => columns.map((column) => `"${String(row[column] ?? "").replaceAll('"', '""')}"`).join(","))].join("\n") + "\n";
const destination = path.join(root, "docs", "dependency-licenses.csv");
fs.writeFileSync(destination, csv);
console.log(`Dependency inventory: ${rows.length} entries; ${rows.filter((row) => row.license === "REQUIERE_REVISION").length} without licence metadata.`);
