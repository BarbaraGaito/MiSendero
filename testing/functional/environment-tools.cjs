const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

module.exports = function environmentTools(root) {
  const gitCandidates = process.platform === 'win32'
    ? ['C:\\Program Files\\Git\\cmd\\git.exe', 'C:\\Program Files (x86)\\Git\\cmd\\git.exe']
    : ['/usr/bin/git'];
  const executable = gitCandidates.find(filename => fs.existsSync(filename));
  if (!executable) throw new Error('Git is missing from the trusted installation directories');
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => key.toUpperCase() !== 'PATH'));
  env.PATH = path.dirname(executable);
  const options = { cwd: root, encoding: 'utf8', env, windowsHide: true };
  const revision = spawnSync(executable, ['rev-parse', 'HEAD'], options);
  const worktree = spawnSync(executable, ['status', '--short'], options);
  if (revision.error || revision.status !== 0 || worktree.error || worktree.status !== 0) {
    throw new Error('Unable to read Git execution metadata');
  }
  // Read the installed npm version as data; do not launch cmd or npm via PATH.
  const npmCandidates = process.platform === 'win32'
    ? [path.join(path.dirname(process.execPath), 'node_modules/npm/package.json')]
    : [path.resolve(path.dirname(process.execPath), '../lib/node_modules/npm/package.json'),
      '/usr/share/nodejs/npm/package.json', '/usr/lib/node_modules/npm/package.json', '/usr/local/lib/node_modules/npm/package.json'];
  const npmManifest = npmCandidates.find(filename => fs.existsSync(filename));
  return { gitHead: revision.stdout.trim(), worktree: worktree.stdout,
    npm: npmManifest ? JSON.parse(fs.readFileSync(npmManifest, 'utf8')).version : null };
};
