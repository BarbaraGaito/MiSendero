const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const reader = path.join(__dirname, 'persistence-reader.cjs');
const invoke = args => spawnSync(process.execPath, [reader, ...args], { encoding: 'utf8', timeout: 10000 });

test('persistence reader rejects filenames, SQLite URIs and malformed fixture identifiers', () => {
  for (const args of [[], [':memory:'], ['file:fixture.sqlite?mode=memory&cache=shared'],
    [path.join(os.tmpdir(), 'fixture.sqlite')], ['../misendero-functional-ABC123'],
    ['misendero-functional-ABC123;mode=memory'], ['misendero-functional-ABC123', 'extra']]) {
    const result = invoke(args);
    assert.equal(result.error, undefined);
    assert.equal(result.status, 1);
    assert.match(result.stderr, /Expected a temporary persistence fixture identifier/);
  }
});

test('persistence reader rejects a fixture directory redirected outside its expected location', (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'misendero-functional-'));
  const target = fs.mkdtempSync(path.join(os.tmpdir(), 'misendero-reader-'));
  t.after(() => {
    for (const temporary of [directory, target]) {
      assert.equal(path.dirname(path.resolve(temporary)), path.resolve(os.tmpdir()));
      assert.match(path.basename(temporary), /^misendero-(?:functional|reader)-[A-Za-z0-9]{6}$/);
      fs.rmSync(temporary, { recursive: true, force: true });
    }
  });
  const sentinel = path.join(target, 'fixture.sqlite');
  fs.writeFileSync(sentinel, 'preserve external bytes');
  fs.rmdirSync(directory);
  fs.symlinkSync(target, directory, process.platform === 'win32' ? 'junction' : 'dir');
  const result = invoke([path.basename(directory)]);
  assert.equal(result.error, undefined);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Persistence fixture must be a regular file without symbolic links/);
  assert.equal(fs.readFileSync(sentinel, 'utf8'), 'preserve external bytes');
});
