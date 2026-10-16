module.exports = (report) => report.integrity.complete
  && report.environment?.lock_matches !== false
  && Object.values(report.components).every((component) => component.tests.success && !component.tests.failed && !component.tests.pending)
  && report.combined.lines.total > 0
  && report.combined.lines.covered / report.combined.lines.total >= 0.85;
