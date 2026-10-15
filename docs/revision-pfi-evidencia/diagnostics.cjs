const fs = require('fs');
const path = require('path');
const vm = require('vm');
const ts = require('../../node_modules/typescript');
const root = path.resolve(__dirname, '../..');
const cache = new Map();
const sandboxProcess = Object.freeze({ env: Object.freeze({}) });
function loadTs(relative) {
  const filename = path.resolve(root, relative);
  if (cache.has(filename)) return cache.get(filename);
  const output = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true }
  }).outputText;
  const module = { exports: {} };
  const localRequire = (name) => {
    if (name === 'expo-file-system/legacy') return { documentDirectory: 'file:///audit-only/' };
    if (name.startsWith('.')) {
      const target = path.resolve(path.dirname(filename), name);
      return name.endsWith('.json') ? JSON.parse(fs.readFileSync(target, 'utf8')) : loadTs(path.relative(root, target + '.ts'));
    }
    throw new Error('Unexpected dependency: ' + name);
  };
  vm.runInNewContext(
    output,
    { exports: module.exports, module, require: localRequire, console, process: sandboxProcess },
    { filename }
  );
  cache.set(filename, module.exports);
  return module.exports;
}
const geo = loadTs('services/geoUtils.ts');
const maps = loadTs('services/mapTileCache.ts');
const routes = require(path.join(root, 'backend/src/data/realTrailRoutes.js'));
const tilePlans = [13,14,15].flatMap(zoom => Object.entries(routes).map(([name, points]) => {
  const tiles = maps.getOfflineTilePlanForTrail({ route_coordinates: JSON.stringify(points), map_zoom: zoom });
  const byLayer = { standard: 0, terrain: 0 };
  for (const tile of tiles) byLayer[tile.layer]++;
  return { name, zoom, total: tiles.length, byLayer, capped: tiles.length === 220 };
}));
const infer = loadTs('ai/inferenceEngine.ts');
const models = ['fatigue', 'risk', 'routeDifficulty'].map((name) => {
  const data = JSON.parse(fs.readFileSync(path.join(root, 'ai/models', name + 'Metrics.json'), 'utf8'));
  return { name, rows: data.dataset.rows_total, testRows: data.dataset.rows_test, accuracy: data.metrics.test.accuracy,
    macroF1: data.metrics.test.f1_macro, byLabel: data.dataset.rows_by_label, testByLabel: Object.fromEntries(data.labels.map(label => [label, data.classification_report[label].support])), guardrail: data.guardrails.status };
});
const white = '#FFFFFF';
function luminance(hex) {
  const v = [1,3,5].map(i => Number.parseInt(hex.slice(i,i+2),16)/255).map(c=>c<=0.04045?c/12.92:((c+0.055)/1.055)**2.4);
  return v[0]*0.2126+v[1]*0.7152+v[2]*0.0722;
}
function contrast(a,b) { return +( (Math.max(luminance(a),luminance(b))+0.05)/(Math.min(luminance(a),luminance(b))+0.05)).toFixed(2); }
console.log(JSON.stringify({
  note: 'Static source diagnostics; no network, device sensors or database used. Tile plans use explicit zoom=13/14/15, not persisted database values.',
  tilePlans,
  missingSpo2Example: infer.predictPhysioRisk({ hr: 90, speedKmh: 3, elapsedMinutes: 10, fatigue: 'bajo' }),
  models,
  tokenContrast: { whiteOnDanger: contrast(white, '#D84C3F'), mutedOnPage: contrast('#6E7A73', '#F6FAF7') }
}, null, 2));
