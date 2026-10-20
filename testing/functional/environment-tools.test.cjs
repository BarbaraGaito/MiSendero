const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const environmentTools = require('./environment-tools.cjs');

test('Git metadata and npm version are read without trusting executables on PATH', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'misendero-tools-'));
  const previousPath = process.env.PATH;
  try {
    // Even a PATH containing only attacker-controlled candidates must not be used.
    for (const filename of ['git.exe', 'git.cmd', 'cmd.exe', 'npm.cmd', 'git', 'npm']) {
      fs.writeFileSync(path.join(directory, filename), 'untrusted executable', { mode: 0o755 });
    }
    process.env.PATH = directory;
    const result = environmentTools(path.resolve(__dirname, '../..'));
    assert.match(result.gitHead, /^[a-f0-9]{40,64}$/);
    assert.equal(typeof result.worktree, 'string');
    assert.ok(result.npm === null || /^\d+\.\d+\.\d+/.test(result.npm));
  } finally {
    if (previousPath === undefined) delete process.env.PATH;
    else process.env.PATH = previousPath;
    assert.equal(path.dirname(path.resolve(directory)), path.resolve(os.tmpdir()));
    assert.ok(path.basename(directory).startsWith('misendero-tools-'));
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
