// Isolated Node process: production SQL/repositories, a private file-backed SQLite snapshot.
// Native identity and SMS boundaries are controlled; this is not an app restart.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const Module = require('node:module');
const ts = require('typescript');
const { DatabaseSync } = require('node:sqlite');
const root = path.resolve(__dirname, '../..');
// The parent sends committed database bytes on stdin, never a connection string.
if (process.argv.length !== 2) {
  throw new Error('Persistence reader accepts no CLI arguments');
}
const snapshot = fs.readFileSync(0);
if (!snapshot.subarray(0, 16).equals(Buffer.from('SQLite format 3\0'))) {
  throw new Error('Expected a SQLite snapshot on stdin');
}
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'misendero-reader-'));
const fixtureFilename = path.join(directory, 'fixture.sqlite');
let database;
process.once('exit', () => {
  database?.close();
  for (const suffix of ['', '-journal', '-wal', '-shm']) fs.rmSync(`${fixtureFilename}${suffix}`, { force: true });
  fs.rmdirSync(directory);
});
fs.writeFileSync(fixtureFilename, snapshot, { flag: 'wx' });
database = new DatabaseSync(fixtureFilename);
let owner = 901;
const adapter = {
  closeAsync: async () => {},
  execAsync: async sql => database.exec(sql),
  runAsync: async (sql, args = []) => {
    const result = database.prepare(sql).run(...args);
    return { changes: result.changes, lastInsertRowId: Number(result.lastInsertRowid) };
  },
  getAllAsync: async (sql, args = []) => database.prepare(sql).all(...args),
  getFirstAsync: async (sql, args = []) => database.prepare(sql).get(...args) ?? null,
  withTransactionAsync: async work => {
    database.exec('BEGIN');
    try { await work(); database.exec('COMMIT'); }
    catch (error) { database.exec('ROLLBACK'); throw error; }
  },
};
const originalLoad = Module._load;
Module._load = function (name, parent, main) {
  if (name === 'react-native') return { Platform: { OS: 'ios' } };
  if (name === 'expo-crypto') return { randomUUID: require('node:crypto').randomUUID };
  if (name.endsWith('/protectedStorage')) return { openProtectedDatabase: async () => adapter };
  if (name === 'expo-sqlite') return { openDatabaseAsync: async () => adapter };
  if (name === 'expo-sms') return {};
  if (parent?.filename.startsWith(root) && /(?:^|\/)authSession$/.test(name)) {
    return { getAuthSession: async () => ({ token: 'fixture', user: { id: owner } }) };
  }
  return originalLoad.call(this, name, parent, main);
};
require.extensions['.ts'] = (module, filename) => {
  const result = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    fileName: filename,
  });
  module._compile(result.outputText, filename);
};
(async () => {
  const route = require('../../services/routeSession.ts');
  const tracking = require('../../services/routeTracking.ts');
  const session = await route.getActiveRouteSession();
  const summary = await tracking.getRouteTrackingSummary(7, 1792231200000);
  const queued = database.prepare('SELECT status, payload_json FROM pending_operations WHERE user_id = ?').all(owner);
  const maps = database.prepare('SELECT status FROM offline_maps WHERE user_id = ?').all(owner);
  owner = 902;
  const otherAccount = await route.getActiveRouteSession();
  process.stdout.write(JSON.stringify({ session, summary, queued, maps, otherAccount }));
})().catch(error => { console.error(error); process.exitCode = 1; });
