const review = require("./reviewedTrailFacts20261021.json");
const byName = new Map(review.entries.map(entry => [entry.name, entry]));

// Apply only to the repository's original definitions. Existing database records
// are changed only by explicit seeding/import, never by reading recommendations.
function applyReviewedFacts(trail) {
  const entry = byName.get(trail.name);
  if (!entry) return trail;
  return { ...trail, ...(entry.difficulty ? { difficulty: entry.difficulty } : {}),
    provenance: { ...trail.provenance, checked_at: review.reviewed_at,
      route_type: entry.route_type, duration_basis: entry.duration_basis,
      sources: entry.sources, distance_basis: entry.distance_basis || "catalog_record_unconfirmed",
      official_distance_km: entry.official_distance_km ?? null,
      review: { confirmed_fields: entry.confirmed_fields, unconfirmed_fields: entry.unconfirmed_fields,
        finding: entry.finding, warning: entry.warning || null } } };
}
module.exports = { applyReviewedFacts, review };
