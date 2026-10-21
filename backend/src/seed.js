const { query } = require("./db");
const seedTrailData = require("./data/legacyTrails");
const { applyReviewedFacts } = require("./data/reviewedTrailFacts");
const additionalTrails = require("./data/additionalTrails");
const nationalParks = require("./data/nationalParks");
const logger = require("./logger");

// Earlier versions seeded these status reports as if hikers had sent them.
// Reports must only come from real users, so any remaining copy is removed.
const fabricatedReports = [
  ["Barro y rocas sueltas", "Tramo humedo en sectores de bosque."],
  ["Sendero transitable", "Buena senalizacion en los cruces principales."],
  ["Nieve o hielo", "Precaucion en el ascenso final."],
  ["Viento fuerte", "Rafagas cerca del mirador."],
  ["Barro", "Piso resbaladizo en bajadas."],
  ["Transitable con mucha humedad", "Pasarelas humedas."],
];

const legacyTrailNames = [
  ["Base del Volcan Lanin", "Volcan Lanin - Base a Refugio BIM"],
  ["Alerce Milenario", "Lahuan Solitario - Puerto Chucao"],
  ["Sendero El Palmar", "Sendero El Mollar - El Palmar"],
  ["Circuito Valle de la Luna", "Caminata al Cerro Morado"],
];

const migrateLegacyTrailNames = async () => {
  for (const [oldName, currentName] of legacyTrailNames) {
    await query(
      `
        UPDATE trails
        SET name = $2
        WHERE name = $1
          AND NOT EXISTS (SELECT 1 FROM trails WHERE name = $2)
      `,
      [oldName, currentName]
    );
  }
};

const seedTrails = async () => {
  for (const trail of [...seedTrailData.map(applyReviewedFacts), ...additionalTrails]) {
    await query(
      `
        INSERT INTO trails (
          name, location, difficulty, duration, distance_km, description,
          image_url, center_lat, center_lng, map_zoom, route_coordinates, provenance
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        ON CONFLICT (name) DO UPDATE SET
          location = EXCLUDED.location,
          difficulty = EXCLUDED.difficulty,
          duration = EXCLUDED.duration,
          distance_km = EXCLUDED.distance_km,
          description = EXCLUDED.description,
          image_url = EXCLUDED.image_url,
          center_lat = EXCLUDED.center_lat,
          center_lng = EXCLUDED.center_lng,
          map_zoom = EXCLUDED.map_zoom,
          route_coordinates = EXCLUDED.route_coordinates,
          provenance = COALESCE(EXCLUDED.provenance, trails.provenance)
      `,
      [
        trail.name,
        trail.location,
        trail.difficulty,
        trail.duration,
        trail.distance_km,
        trail.description,
        trail.image_url,
        trail.center_lat,
        trail.center_lng,
        trail.map_zoom,
        JSON.stringify(trail.route_coordinates),
        trail.provenance ? JSON.stringify(trail.provenance) : null,
      ]
    );
  }
  for (const park of nationalParks) {
    const { trails: names, ...profile } = park;
    await query(`INSERT INTO national_parks (slug, profile) VALUES ($1, $2)
      ON CONFLICT (slug) DO UPDATE SET profile = EXCLUDED.profile`, [park.slug, JSON.stringify(profile)]);
    for (const name of names) {
      await query("UPDATE trails SET national_park_slug = $1 WHERE name = $2", [park.slug, name]);
    }
  }
};

const removeFabricatedReports = async () => {
  for (const [issueSummary, details] of fabricatedReports) {
    await query(
      "DELETE FROM trail_reports WHERE reporter_name = $1 AND issue_summary = $2 AND details = $3",
      ["Senderista verificado", issueSummary, details]
    );
  }
};

const seedDatabase = async () => {
  await migrateLegacyTrailNames();
  await seedTrails();
  await removeFabricatedReports();
};

module.exports = seedDatabase;

if (require.main === module) {
  seedDatabase()
    .then(() => {
      logger.info("Datos de ejemplo cargados correctamente");
      process.exit(0);
    })
    .catch((error) => {
      logger.error(error, "Error al cargar los datos de ejemplo");
      process.exit(1);
    });
}
