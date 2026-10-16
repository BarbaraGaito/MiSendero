const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const defaultScope = require("./coverage-scope.cjs");
const metrics = ["lines", "statements", "branches", "functions"];
const empty = () => Object.fromEntries(metrics.map((metric) => [metric, { total: 0, covered: 0, skipped: 0, pct: 100 }]));
const add = (target, source) => {
  for (const metric of metrics) {
    for (const key of ["total", "covered", "skipped"]) target[metric][key] += source[metric][key];
    target[metric].pct = target[metric].total ? Number((100 * target[metric].covered / target[metric].total).toFixed(4)) : 100;
  }
};
const digest = (file) => crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
const escape = (text) => String(text).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll('"', "&quot;");
const csv = (values) => values.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(",");
function summarize(output, scope = defaultScope) {
  const relative = (file) => path.relative(scope.root, file).replaceAll("\\", "/");
  const combined = empty(), components = {}, groups = {}, inventory = [], missing = [], unexpected = [];
  const inputs = [], lcov = [];
  for (const component of ["client", "backend"]) {
    const directory = path.join(output, component);
    const summaryPath = path.join(directory, "coverage-summary.json");
    const file = JSON.parse(fs.readFileSync(summaryPath, "utf8"));
    const tests = JSON.parse(fs.readFileSync(path.join(directory, "test-results.json"), "utf8"));
    const project = component === "client" ? scope.root : path.join(scope.root, "backend");
    lcov.push(fs.readFileSync(path.join(directory, "lcov.info"), "utf8").replace(/^SF:(.+)$/gm,
      (_match, source) => `SF:${relative(path.resolve(project, source.trim()))}`));
    components[component] = { ...file.total, tests: { suites: tests.numTotalTestSuites, passed: tests.numPassedTests, failed: tests.numFailedTests, pending: tests.numPendingTests, success: tests.success } };
    inputs.push({ file: relative(summaryPath), sha256: digest(summaryPath), coverage_sha256: digest(path.join(directory, "coverage-final.json")) });
    const byPath = new Map(Object.entries(file).filter(([name]) => name !== "total").map(([name, value]) => [relative(name), value]));
    for (const source of scope[component]) {
      const measures = byPath.get(source);
      if (!measures) missing.push({ component, file: source });
      const row = { component, file: source, sha256: digest(path.join(scope.root, source)), ...(measures || empty()), present: !!measures };
      inventory.push(row);
      const group = source.startsWith("backend/") ? source.split("/").slice(0, source.startsWith("backend/src/") && source.split("/").length > 3 ? 3 : 2).join("/")
        : source.startsWith("mobile/") ? source.split("/").slice(0, 2).join("/") : source.includes("/") ? source.split("/")[0] : "configuración de distribución";
      groups[group] ||= empty(); add(groups[group], row); add(combined, row);
    }
    for (const filename of byPath.keys()) if (!scope[component].includes(filename)) unexpected.push({ component, file: filename });
  }
  const summary = { generated_at: new Date().toISOString(), provider: "babel/Istanbul", metric_for_requirement: "lines", threshold: 85,
    formula: "100 * sum(covered executable source lines) / sum(executable source lines), not mean of percentages",
    components, groups, combined, integrity: { complete: !missing.length && !unexpected.length, missing, unexpected }, inputs, inventory,
    environment: fs.existsSync(path.join(output, "environment.json")) ? JSON.parse(fs.readFileSync(path.join(output, "environment.json"))) : null };
  fs.writeFileSync(path.join(output, "summary.json"), JSON.stringify(summary, null, 2) + "\n");
  fs.writeFileSync(path.join(output, "lcov.info"), lcov.join("\n"));
  fs.writeFileSync(path.join(output, "modules.csv"), [csv(["component", "file", ...metrics.flatMap((metric) => [`${metric}_covered`, `${metric}_total`, `${metric}_percent`]), "source_sha256"]),
    ...inventory.map((row) => csv([row.component, row.file, ...metrics.flatMap((metric) => [row[metric].covered, row[metric].total, row[metric].pct]), row.sha256]))].join("\n") + "\n");
  const table = (entries) => `<table><thead><tr><th>Componente / módulo</th>${metrics.map((metric) => `<th>${metric}</th>`).join("")}</tr></thead><tbody>${entries.map(([name, data]) => `<tr><th>${escape(name)}</th>${metrics.map((metric) => `<td>${data[metric].covered}/${data[metric].total} (${data[metric].pct}%)</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  fs.writeFileSync(path.join(output, "index.html"), `<!doctype html><html lang="es"><meta charset="utf-8"><title>MiSendero — cobertura real</title><style>body{font:16px system-ui;margin:32px}table{border-collapse:collapse;margin:24px 0}td,th{border:1px solid #bbb;padding:8px;text-align:left}th{background:#eee}</style><h1>MiSendero: cobertura instrumentada</h1><p>${escape(summary.generated_at)} · Babel/Istanbul · objetivo: 85% de líneas.</p><p>Agregado ponderado. Las pruebas de dispositivo, extremo a extremo y usabilidad requieren evidencia independiente.</p><p>Inventario completo: ${summary.integrity.complete}. Archivos ausentes: ${missing.length}; fuera del alcance: ${unexpected.length}.</p><a href="client/index.html">HTML cliente</a> · <a href="backend/index.html">HTML backend</a> · <a href="modules.csv">CSV por módulo</a> · <a href="summary.json">JSON con hashes</a>${table([["Total", combined], ...Object.entries(groups)])}${table(inventory.map((row) => [row.file, row]))}</html>`);
  console.log(JSON.stringify({ output: relative(output), complete: summary.integrity.complete, components: Object.fromEntries(Object.entries(components).map(([name, item]) => [name, item.lines])), combined: combined.lines, missing, unexpected }));
  return summary;
}
module.exports = summarize;
if (require.main === module) summarize(path.resolve(defaultScope.root, process.argv[2] || "coverage"));
