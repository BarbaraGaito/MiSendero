const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
// Full first-party JS/TS scope. Never derive the denominator from test imports.
// Tests, mocks and declaration-only .d.ts files are not production executable code.
function walk(directory) {
  return fs.readdirSync(path.join(root, directory), { withFileTypes: true }).flatMap((entry) => {
    const file = `${directory}/${entry.name}`;
    if (["node_modules", "__tests__", "tests", "__mocks__"].includes(entry.name)) return [];
    if (entry.isDirectory()) return walk(file);
    return /\.(?:[cm]?js|tsx?)$/.test(entry.name) && !/\.d\.ts$|\.(?:test|spec)\./.test(entry.name) ? [file] : [];
  });
}
const client = ["app", "mobile", "services", "database", "ai", "types", "scripts"].flatMap(walk)
  .concat(["app.config.js", "metro.config.js"]).sort((a, b) => a.localeCompare(b, "en"));
const backend = ["backend/src", "backend/scripts"].flatMap(walk).sort((a, b) => a.localeCompare(b, "en"));
module.exports = { root, client, backend };
