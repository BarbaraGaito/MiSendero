const fs = require("node:fs");
const path = require("node:path");

// The repository root is trusted configuration, never a CLI argument.
module.exports = function coveragePath(filename, root) {
  const base = path.resolve(root, "coverage");
  const resolved = path.resolve(root, filename);
  const relative = path.relative(base, resolved);
  if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error("Coverage path must stay inside the repository coverage directory");
  }
  // Check every component, including absent destinations and dangling links.
  // Reject links rather than trusting a resolved, potentially external target.
  let current = base;
  for (const segment of ["", ...relative.split(path.sep).filter(Boolean)]) {
    current = path.join(current, segment);
    if (fs.lstatSync(current, { throwIfNoEntry: false })?.isSymbolicLink()) {
      throw new Error("Coverage path must not contain symbolic links");
    }
  }
  return resolved;
};
