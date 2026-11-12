const legacy = require("./reviewedTrailFacts20261021.json");
const entries = new Map(legacy.entries.map(entry => [entry.name, entry]));
const reviewId = "catalog-duration-review-2026-11-12";
const rechecked = new Set(["Sendero a Confluencia", "Lahuan Solitario - Puerto Chucao", "Caminata al Cerro Morado", "Laguna del Tesoro - Aconquija"]);

// Match the existing record, not merely a route name. A changed route or any
// independently supplied provenance must be inspected before replacing it.
const expected = new Map([
  ["Sendero a Confluencia", ["Parque Provincial Aconcagua, Mendoza", "4 a 5 h", 14]],
  ["Volcan Lanin - Base a Refugio BIM", ["Parque Nacional Lanin, Neuquen", "6 a 8 h", 13]],
  ["Garganta del Diablo de Tilcara", ["Tilcara, Jujuy", "1 h 30 min a 2 h", 3.14]],
  ["Garganta del Diablo - Quebrada de las Conchas", ["Cafayate, Salta", "30 a 45 min", 0.65]],
  ["Lahuan Solitario - Puerto Chucao", ["Parque Nacional Los Alerces, Chubut", "1 h 30 min", 3]],
  ["Sendero El Mollar - El Palmar", ["Parque Nacional El Palmar, Entre Rios", "30 a 45 min", 1.4]],
  ["Ascenso Cerro Tres Picos", ["Sierra de la Ventana, Buenos Aires", "8 a 10 h", 18.3]],
  ["Caminata al Cerro Morado", ["Parque Provincial Ischigualasto, San Juan", "3 h", 5.73]],
  ["Campo de Piedra Pomez", ["Antofagasta de la Sierra, Catamarca", "1 a 2 h", 2]],
  ["Laguna del Tesoro - Aconquija", ["Parque Nacional Aconquija, Tucuman", "10 a 12 h", 20.6]],
]);

function reviewLegacyDuration(row) {
  const identity = expected.get(row.name);
  if (!identity || row.provenance != null) return row;
  const [location, duration, distanceKm] = identity;
  if (row.location !== location || row.duration !== duration || !(Math.abs(Number(row.distance_km) - distanceKm) < 0.0001)) return row;
  const entry = entries.get(row.name);
  const sources = [...entry.sources];
  let finding = entry.finding;
  let warning = entry.warning ?? null;
  if (row.name === "Sendero a Confluencia") {
    sources.push({ title: "Gobierno de Mendoza — Trekking de día a Confluencia", url: "https://www.mendoza.gov.ar/prensa/mas-de-300-personas-visitaron-el-aconcagua-en-diez-dias/" });
    finding = "Las referencias describen Horcones–Confluencia–Horcones. Mendoza publicó 4–5 h (también 5 h en su nota de prensa); Turismo Nación indica 6–8 h. El alcance de ida y vuelta está documentado, pero los tiempos difieren.";
    warning = "El regreso está incluido en las referencias, pero las fuentes difieren (4–5 h y 6–8 h). Las 4–5 h de la ficha no se usan para comprobar tu rango. Confirmá el tiempo y acceso con el parque.";
  } else if (row.name === "Laguna del Tesoro - Aconquija") {
    sources.push({ title: "La Ruta Natural — Parque Nacional Aconquija", url: "https://larutanatural.gob.ar/es/imperdible/154/parque-nacional-aconquija" });
    finding = "Tucumán Turismo y La Ruta Natural publican 6 h de ida desde Cochuna. No se encontró tiempo oficial de regreso; las referencias tampoco coinciden en distancia total.";
    warning = "Las fuentes publican 6 h solo de ida. Las 10–12 h de la ficha no son un total confirmado. Consultá el regreso y las condiciones de los cruces de agua con el parque.";
  }
  const confirmedFields = entry.confirmed_fields.filter(field => row.name !== "Laguna del Tesoro - Aconquija" || !["distance_km", "difficulty"].includes(field));
  if (row.name === "Sendero a Confluencia") confirmedFields.push("duration_scope");
  const minutes = { "official_round_trip": 90, "official_total_itinerary": 180 }[entry.duration_basis];
  return { ...row, provenance: {
    duration_review_id: reviewId, checked_at: rechecked.has(row.name) ? "2026-11-12" : legacy.reviewed_at, route_type: entry.route_type,
    duration_basis: entry.duration_basis, sources,
    ...(minutes ? { duration_minutes_min: minutes, duration_minutes_max: minutes } : {}),
    ...(warning ? { source_notice: warning } : {}),
    review: { confirmed_fields: confirmedFields, unconfirmed_fields: row.name === "Laguna del Tesoro - Aconquija" ? ["duration", "distance_km", "difficulty"] : entry.unconfirmed_fields,
      finding, warning },
  } };
}

module.exports = { reviewLegacyDuration };
