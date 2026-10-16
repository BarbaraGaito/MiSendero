const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
module.exports = (root) => {
  const mismatches = [], components = {};
  for (const component of ["client", "backend"]) {
    const base = component === "client" ? root : path.join(root, "backend");
    const manifest = JSON.parse(fs.readFileSync(path.join(base, "package.json")));
    const bytes = fs.readFileSync(path.join(base, "package-lock.json"));
    const lock = JSON.parse(bytes), installed = {};
    const names = new Set([...Object.keys(manifest.dependencies || {}), ...Object.keys(manifest.devDependencies || {}),
      "babel-plugin-istanbul", "istanbul-lib-coverage", "istanbul-lib-instrument", ...(component === "client" ? ["react-test-renderer"] : [])]);
    for (const name of names) {
      let version = null;
      try { version = JSON.parse(fs.readFileSync(path.join(base, "node_modules", name, "package.json"))).version; } catch {}
      const locked = lock.packages[`node_modules/${name}`]?.version ?? null;
      installed[name] = { installed: version, locked };
      if (!version || version !== locked) mismatches.push({ component, name, installed: version, locked });
    }
    components[component] = { lock_sha256: crypto.createHash("sha256").update(bytes).digest("hex"), packages: installed };
  }
  return { recorded_at: new Date().toISOString(), node: process.version, platform: process.platform, architecture: process.arch,
    test_timezone: "UTC", lock_matches: !mismatches.length, mismatches, components };
};
