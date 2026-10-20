const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const scope = require('../coverage-scope.cjs');
const cases = require('./cases.cjs');
const root = scope.root;
const option = (name, fallback) => process.argv.find(arg => arg.startsWith(`--${name}=`))?.slice(name.length + 3) || fallback;
const seed = Number(option('seed', '20261017'));
if (!Number.isSafeInteger(seed)) throw new Error('The seed must be an integer');
const output = path.resolve(root, option('output', `validation/functional/${new Date().toISOString().slice(0, 10)}/seed-${seed}`));
if (fs.existsSync(output) && fs.readdirSync(output).length) throw new Error(`Evidence directory is not empty: ${output}`);
fs.mkdirSync(output, { recursive: true });
const scratch = path.join(root, 'coverage', `functional-${Date.now()}-${seed}`);
const startedAt = new Date().toISOString();
const json = (name, value) => fs.writeFileSync(path.join(output, name), JSON.stringify(value, null, 2) + '\n');
const relative = file => path.relative(root, file).replaceAll('\\', '/');
const sha = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const stages = [];
function run(name, executable, args, cwd = root) {
  const started = new Date().toISOString();
  const result = spawnSync(executable, args, { cwd, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024,
    env: { ...process.env, TZ: 'UTC' } });
  const evidence = `${name}.txt`;
  fs.writeFileSync(path.join(output, evidence), `$ executable: ${executable}\n$ args: ${JSON.stringify(args)}\n$ cwd: ${cwd}\n\nSTDOUT\n${result.stdout || ''}\nSTDERR\n${result.stderr || ''}`);
  const stage = { name, executable, args, cwd, startedAt: started, finishedAt: new Date().toISOString(), exitCode: result.status,
    error: result.error?.message || null, evidence };
  stages.push(stage);
  json('commands.json', stages);
  console.log(`${name}: exit ${result.status}; ${relative(path.join(output, evidence))}`);
  return result;
}
const inventory = run('device-inventory', 'powershell.exe', ['-NoProfile', '-Command',
  "$c=@((Join-Path $env:LOCALAPPDATA 'Android/Sdk/platform-tools/adb.exe'),(Join-Path $env:LOCALAPPDATA 'Android/Sdk/emulator/emulator.exe')); [pscustomobject]@{commands=@(Get-Command adb,emulator -ErrorAction SilentlyContinue | ForEach-Object {$_.Source}); candidates=@($c | ForEach-Object {[pscustomobject]@{path=$_;exists=(Test-Path -LiteralPath $_)}}); sdkRoot=$env:ANDROID_SDK_ROOT; androidHome=$env:ANDROID_HOME} | ConvertTo-Json -Depth 4; exit 0"]);
const nativeInventory = (() => { try { return JSON.parse(inventory.stdout); } catch { return { raw: 'See device-inventory.txt' }; } })();
const deviceCandidates = [...(nativeInventory.commands || []), ...(nativeInventory.candidates || []).filter(c => c.exists && /adb\.exe$/i.test(c.path)).map(c => c.path)];
let adb = null;
if (deviceCandidates.length) adb = run('adb-devices', deviceCandidates[0], ['devices', '-l']);
const tools = require('./environment-tools.cjs')(root);
json('environment.json', {
  startedAt, calendarDate: new Intl.DateTimeFormat('sv-SE', { timeZone: 'America/Argentina/Buenos_Aires' }).format(new Date()),
  calendarTimezone: 'America/Argentina/Buenos_Aires', testTimezone: 'UTC', os: { platform: os.platform(), release: os.release(), architecture: os.arch() },
  node: process.version, ...tools,
  packages: require('../coverage-environment.cjs')(root), nativeInventory,
  connectedDevices: adb ? { evidence: 'adb-devices.txt', exitCode: adb.status } : null,
  executionScope: 'Node/Jest; React Test Renderer; controlled native/network boundaries; SQLite; Express/Supertest with pg-mem',
  limitations: ['No native application build was launched by this command.', 'No physical field trial, battery autonomy measurement, wearable measurement or real SOS delivery was performed.',
    'PostgreSQL is emulated with pg-mem; SQLite native mobile bindings and graphical tile rendering require separate validation.'],
});
run('typecheck', process.execPath, [require.resolve('typescript/bin/tsc'), '--noEmit']);
run('backend-build', process.execPath, [require.resolve('typescript/bin/tsc', { paths: [path.join(root, 'backend')] }), '-p', 'tsconfig.ai.json'], path.join(root, 'backend'));
run('coverage-tools', process.execPath, ['--test', 'testing/coverage-tools.test.cjs']);
run('regression', process.execPath, ['testing/run-coverage.cjs', `--output=${scratch}`, '--randomize', `--seed=${seed}`, '--showSeed']);
const probeJest = require.resolve('jest/bin/jest', { paths: [path.join(root, 'backend')] });
run('acceptance-probe', process.execPath, [probeJest, '--runInBand', '--randomize', `--seed=${seed}`, '--testMatch=**/*.probe.js',
  '--runTestsByPath', 'tests/functional/reportRetry.probe.js', '--json', `--outputFile=${path.join(output, 'probe-results.json')}`], path.join(root, 'backend'));
for (const name of ['summary.json', 'modules.csv', 'environment.json']) {
  const source = path.join(scratch, name);
  if (fs.existsSync(source)) fs.copyFileSync(source, path.join(output, `coverage-${name}`));
}
const reports = [];
for (const component of ['client', 'backend']) {
  const source = path.join(scratch, component, 'test-results.json');
  if (fs.existsSync(source)) {
    const report = JSON.parse(fs.readFileSync(source));
    reports.push({ component, report, evidence: `${component}-results.json` });
    fs.copyFileSync(source, path.join(output, `${component}-results.json`));
    fs.copyFileSync(path.join(scratch, component, 'coverage-summary.json'), path.join(output, `${component}-coverage.json`));
  }
}
if (fs.existsSync(path.join(output, 'probe-results.json'))) reports.push({ component: 'acceptance-probe', report: JSON.parse(fs.readFileSync(path.join(output, 'probe-results.json'))), evidence: 'probe-results.json' });
const assertions = reports.flatMap(({ component, report, evidence }) => report.testResults.flatMap(suite => suite.assertionResults.map(assertion => ({
  component, file: relative(suite.name), fullName: assertion.fullName, status: assertion.status,
  durationMs: assertion.duration, evidence, failureMessages: assertion.failureMessages,
}))));
const matrix = cases.map(scenario => {
  const selections = scenario.selectors.map(selector => {
    const matched = assertions.filter(assertion => assertion.file === selector.file && assertion.fullName.includes(selector.title));
    return { ...selector, matched, status: !matched.length ? 'Sin evidencia' : matched.some(test => test.status === 'failed') ? 'Fallido' : matched.every(test => test.status === 'passed') ? 'Aprobado' : 'No ejecutado' };
  });
  const automatedStatus = selections.some(selection => selection.status === 'Fallido') ? 'Fallido' : selections.every(selection => selection.status === 'Aprobado') ? 'Aprobado en el alcance automatizado' : 'Sin evidencia completa';
  return { ...scenario, automated: { status: automatedStatus, selections },
    obtained: selections.flatMap(selection => selection.matched.map(test => `${test.status}: ${test.fullName}`)),
    evidence: [...new Set(selections.flatMap(selection => selection.matched.map(test => test.evidence)))],
    status: automatedStatus === 'Fallido' ? 'Fallo observado' : 'Validación parcial por nivel',
    endToEnd: { status: 'No ejecutado', obtained: 'No se lanzó una build de la aplicación conectada al backend.', evidence: [] },
    manual: { status: 'No ejecutado', obtained: 'Protocolo definido; no se registró una sesión manual de validación.', evidence: [] },
    physicalDevice: { status: 'No ejecutado', obtained: 'No se utilizó un teléfono ni wearable físico en esta campaña.', evidence: [] },
  };
});
json('matrix.json', matrix);
const csv = values => values.map(value => `"${String(value).replaceAll('"', '""')}"`).join(',');
fs.writeFileSync(path.join(output, 'matrix.csv'), [csv(['ID', 'RF_RNF', 'objetivo', 'precondiciones', 'datos', 'pasos', 'esperado', 'obtenido_automatizado', 'evidencia', 'estado', 'E2E', 'manual', 'dispositivo', 'observaciones']),
  ...matrix.map(row => csv([row.id, row.requirements.join('; '), row.objective, row.preconditions.join(' | '), row.data.join(' | '), row.steps.map((step, index) => `${index + 1}. ${step}`).join(' | '), row.expected,
    row.obtained.join(' | '), row.evidence.join('; '), row.automated.status, row.endToEnd.status, row.manual.status, row.physicalDevice.status, row.observation]))].join('\n') + '\n');
const totals = Object.fromEntries(reports.map(({ component, report }) => [component, { suites: report.numTotalTestSuites, total: report.numTotalTests, passed: report.numPassedTests, failed: report.numFailedTests, pending: report.numPendingTests, success: report.success }]));
const summary = { startedAt, finishedAt: new Date().toISOString(), seed, totals, caseCount: cases.length,
  automatedCases: { supported: matrix.filter(row => row.automated.status === 'Aprobado en el alcance automatizado').length, failed: matrix.filter(row => row.automated.status === 'Fallido').length, missing: matrix.filter(row => row.automated.status === 'Sin evidencia completa').length },
  scope: 'Scenario support is partial by validation level. Code coverage is an independent indicator.',
  coverage: fs.existsSync(path.join(output, 'coverage-summary.json')) ? JSON.parse(fs.readFileSync(path.join(output, 'coverage-summary.json'))).combined : null,
  sourceReports: reports.map(({ component, evidence }) => ({ component, evidence })), commands: stages,
};
json('summary.json', summary);
const markdown = ['# Matriz funcional de MiSendero', '', `Ejecución: ${startedAt}. Semilla: ${seed}.`, '',
  'Los resultados automatizados se limitan a las aserciones enlazadas. Ningún escenario se declara validado en dispositivo o de extremo a extremo.', '',
  '| ID | Escenario | RF/RNF | Automatización | E2E / manual / dispositivo |', '|---|---|---|---|---|',
  ...matrix.map(row => `| ${row.id} | ${row.title} | ${row.requirements.join(', ')} | ${row.automated.status} | No ejecutados |`), '',
  ...matrix.flatMap(row => [`## ${row.id} — ${row.title}`, '', `**RF/RNF:** ${row.requirements.join(', ')}. **Prioridad:** ${row.priority}.`, '', `**Objetivo:** ${row.objective}`, '',
    '**Precondiciones:**', '', ...row.preconditions.map(value => `- ${value}`), '', '**Datos:**', '', ...row.data.map(value => `- ${value}`), '', '**Pasos del protocolo manual/dispositivo:**', '',
    ...row.steps.map((value, index) => `${index + 1}. ${value}`), '', `**Resultado esperado:** ${row.expected}`, '', `**Resultado obtenido — automatización:** ${row.automated.status}.`, '',
    ...row.automated.selections.flatMap(selection => selection.matched.length ? selection.matched.map(test => `- ${selection.level}; ${test.file} — ${test.fullName}: **${test.status}**. Evidencia: [${test.evidence}](${test.evidence}).${test.failureMessages.length ? ' La aserción y el valor obtenido se conservan en el JSON y en acceptance-probe.txt.' : ''}`) : [`- Sin evidencia para ${selection.file}: ${selection.title}.`]), '',
    '**Resultado obtenido — E2E, manual y dispositivo:** No ejecutados. Evidencia: ninguna.', '', `**Estado:** ${row.status}.`, '', `**Observaciones:** ${row.observation}`, ''])];
fs.writeFileSync(path.join(output, 'matrix.md'), markdown.join('\n'));
const sourceFiles = new Set([...scope.client, ...scope.backend, 'package.json', 'package-lock.json', 'backend/package.json', 'backend/package-lock.json', 'jest.config.js', 'backend/jest.config.js', '.gitignore']);
function walk(directory) {
  for (const entry of fs.readdirSync(path.join(root, directory), { withFileTypes: true })) {
    const filename = `${directory}/${entry.name}`;
    if (entry.name === 'node_modules') continue;
    if (entry.isDirectory()) walk(filename);
    else sourceFiles.add(filename);
  }
}
for (const directory of ['testing', 'services/__tests__', 'mobile/screens/__tests__', 'mobile/components/__tests__', 'mobile/hooks/__tests__', 'database/__tests__', 'ai/__tests__', 'backend/tests']) if (fs.existsSync(path.join(root, directory))) walk(directory);
json('source-manifest.json', [...sourceFiles].filter(file => fs.existsSync(path.join(root, file))).sort((a, b) => a.localeCompare(b, 'en')).map(file => ({ file, sha256: sha(path.join(root, file)) })));
json('evidence-manifest.json', fs.readdirSync(output).sort((a, b) => a.localeCompare(b, 'en')).filter(file => file !== 'evidence-manifest.json').map(file => ({ file, sha256: sha(path.join(output, file)) })));
const failed = stages.some(stage => stage.exitCode !== 0) || matrix.some(row => row.automated.status !== 'Aprobado en el alcance automatizado');
console.log(JSON.stringify({ output: relative(output), totals, cases: summary.automatedCases, result: failed ? 'FAILURES_RETAINED' : 'PASSED_WITHIN_AUTOMATED_SCOPE' }));
process.exitCode = failed ? 1 : 0;
