const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const reader = path.join(__dirname, 'persistence-reader.cjs');
const invoke = (args, input = Buffer.alloc(0), env = process.env) => spawnSync(process.execPath, [reader, ...args],
  { input, env, encoding: 'utf8', timeout: 10000 });

test('persistence reader rejects all CLI connection arguments', () => {
  for (const args of [[':memory:'], ['file:fixture.sqlite?mode=memory&cache=shared'],
    [path.join(os.tmpdir(), 'fixture.sqlite')], ['../misendero-functional-ABC123'],
    ['misendero-functional-ABC123'], ['misendero-functional-ABC123;mode=memory']]) {
    const result = invoke(args);
    assert.equal(result.error, undefined);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /Persistence reader accepts no CLI arguments/);
  }
});

test('stdin accepts SQLite bytes rather than a filename or URI', () => {
  for (const input of ['', ':memory:', 'file:fixture.sqlite?mode=memory', path.join(os.tmpdir(), 'fixture.sqlite')]) {
    const result = invoke([], Buffer.from(input));
    assert.equal(result.error, undefined);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /Expected a SQLite snapshot on stdin/);
  }
});

test('a malformed SQLite snapshot is cleaned up after refusal', (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'misendero-reader-test-'));
  t.after(() => {
    assert.equal(path.dirname(path.resolve(directory)), path.resolve(os.tmpdir()));
    assert.ok(path.basename(directory).startsWith('misendero-reader-test-'));
    fs.rmSync(directory, { recursive: true, force: true });
  });
  const input = Buffer.alloc(512);
  Buffer.from('SQLite format 3\0').copy(input);
  const result = invoke([], input, { ...process.env, TEMP: directory, TMP: directory, TMPDIR: directory });
  assert.equal(result.error, undefined);
  assert.equal(result.status, 1);
  assert.deepEqual(fs.readdirSync(directory), []);
});
