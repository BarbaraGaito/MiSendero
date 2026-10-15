const { query } = require("./db");
const realTrailRoutes = require("./data/realTrailRoutes");
const additionalTrails = require("./data/additionalTrails");
const nationalParks = require("./data/nationalParks");
const logger = require("./logger");

const commonsImage = (fileName) =>
  `https://commons.wikimedia.org/wiki/Special:FilePath/${encodeURIComponent(fileName)}?width=1400`;

const seedTrailData = [
  {
    name: "Sendero a Confluencia",
    location: "Parque Provincial Aconcagua, Mendoza",
    difficulty: "Media",
    duration: "4 a 5 h",
    distance_km: 14,
    description:
      "Trekking clasico de aproximacion al Aconcagua desde Horcones hasta el campamento Confluencia, con vistas de alta montana.",
    image_url: commonsImage("Aconcagua confluencia.jpg"),
    // https://informacionoficial.mendoza.gob.ar/energiayambiente/aconcagua/
    center_lat: -32.791647,
    center_lng: -69.954137,
    map_zoom: 13,
    route_coordinates: realTrailRoutes.confluencia,
  },
  {
    name: "Volcan Lanin - Base a Refugio BIM",
    location: "Parque Nacional Lanin, Neuquen",
    difficulty: "Alta",
    duration: "6 a 8 h",
    distance_km: 13,
    description:
      "Ruta normal desde la base del volcan Lanin hasta el refugio BIM, con fuerte desnivel, ambiente andino y vistas al cono volcanico.",
    image_url: commonsImage("Argentina - Neuquén - Volcán Lanín.jpg"),
    // Coordenadas de Base y Refugio BIM publicadas por Parques Nacionales.
    center_lat: -39.603285,
    center_lng: -71.455579,
    map_zoom: 13,
    route_coordinates: realTrailRoutes.lanin,
  },
  {
    name: "Garganta del Diablo de Tilcara",
    location: "Tilcara, Jujuy",
    difficulty: "Media",
    duration: "1 h 30 min a 2 h",
    distance_km: 3.14,
    description:
      "Recorrido desde Tilcara hacia la quebrada y cascada de la Garganta del Diablo, con vistas de la Quebrada de Humahuaca.",
    image_url: commonsImage("Quebrada de Humahuaca 01.jpg"),
    // Traza peatonal directa registrada en OSM, desde el inicio del camino
    // hasta la cascada. No se calcula una ruta entre origen y destino.
    center_lat: -23.590954,
    center_lng: -65.38109,
    map_zoom: 14,
    route_coordinates: realTrailRoutes.tilcara,
  },
  {
    name: "Garganta del Diablo - Quebrada de las Conchas",
    location: "Cafayate, Salta",
    difficulty: "Baja",
    duration: "30 a 45 min",
    distance_km: 0.65,
    description:
      "Caminata corta entre paredones rojizos y formaciones naturales de la Quebrada de las Conchas, en los Valles Calchaquies.",
    image_url: commonsImage("Quebrada de las Conchas- Salta-.jpg"),
    center_lat: -25.848843,
    center_lng: -65.701041,
    map_zoom: 17,
    route_coordinates: realTrailRoutes.saltaGarganta,
  },
  {
    name: "Lahuan Solitario - Puerto Chucao",
    location: "Parque Nacional Los Alerces, Chubut",
    difficulty: "Baja",
    duration: "1 h 30 min",
    distance_km: 3,
    description:
      "Sendero desde la pasarela del rio Arrayanes hasta Puerto Chucao, bordeando el rio Menendez y pasando junto a un lahuan de unos 300 anos.",
    image_url: commonsImage("Alerce milenario.jpg"),
    // https://www.argentina.gob.ar/node/276965
    center_lat: -42.728261,
    center_lng: -71.749203,
    map_zoom: 15,
    route_coordinates: realTrailRoutes.lahuanSolitario,
  },
  {
    name: "Sendero El Mollar - El Palmar",
    location: "Parque Nacional El Palmar, Entre Rios",
    difficulty: "Baja",
    duration: "30 a 45 min",
    distance_km: 1.4,
    description:
      "Circuito oficial junto al camping que atraviesa palmares y muestra el manejo de especies vegetales exoticas del Parque Nacional El Palmar.",
    image_url: commonsImage("Parque nacional El Palmar Entre Ríos.JPG"),
    // https://www.argentina.gob.ar/parquesnacionales/centro/parque-nacional-el-palmar/actividades
    center_lat: -31.862273,
    center_lng: -58.211157,
    map_zoom: 17,
    route_coordinates: realTrailRoutes.elMollar,
  },
  {
    name: "Ascenso Cerro Tres Picos",
    location: "Sierra de la Ventana, Buenos Aires",
    difficulty: "Alta",
    duration: "8 a 10 h",
    distance_km: 18.3,
    description:
      "Ascenso al punto mas alto de la provincia de Buenos Aires, con pendientes sostenidas y amplias vistas serranas.",
    image_url: commonsImage("Cerro Tres Picos.jpg"),
    center_lat: -38.145914,
    center_lng: -61.990366,
    map_zoom: 13,
    route_coordinates: realTrailRoutes.tresPicos,
  },
  {
    name: "Caminata al Cerro Morado",
    location: "Parque Provincial Ischigualasto, San Juan",
    difficulty: "Alta",
    duration: "3 h",
    distance_km: 5.73,
    description:
      "Trekking oficial hasta la cumbre del Cerro Morado, el punto mas alto de Ischigualasto, con vistas panoramicas del Valle de la Luna.",
    image_url: commonsImage("Ischigualasto, prov. de San Juan, Argentina.jpg"),
    // https://www.ischigualasto.gob.ar/?page_id=1823
    center_lat: -30.163187,
    center_lng: -67.825007,
    map_zoom: 14,
    route_coordinates: realTrailRoutes.cerroMorado,
  },
  {
    name: "Campo de Piedra Pomez",
    location: "Antofagasta de la Sierra, Catamarca",
    difficulty: "Baja",
    duration: "1 a 2 h",
    distance_km: 2,
    description:
      "Caminata corta entre formaciones de piedra pomez, paisaje de puna y suelos volcanicos en Antofagasta de la Sierra.",
    image_url: commonsImage("Campo de Piedra Pomez.jpg"),
    center_lat: -26.58907,
    center_lng: -67.486533,
    map_zoom: 16,
    route_coordinates: realTrailRoutes.piedraPomez,
  },
  {
    name: "Laguna del Tesoro - Aconquija",
    location: "Parque Nacional Aconquija, Tucuman",
    difficulty: "Alta",
    duration: "10 a 12 h",
    distance_km: 20.6,
    description:
      "Sendero exigente desde el portal Cochuna hacia Laguna del Tesoro, atravesando yungas y ambiente de montana del Aconquija.",
    image_url: commonsImage("VistadeTafidelValle.jpg"),
    // https://www.tucumanturismo.gob.ar/articulos/articulo/960/senderos-parque-nacional-aconquija
    center_lat: -27.300308,
    center_lng: -65.940232,
    map_zoom: 13,
    route_coordinates: realTrailRoutes.lagunaTesoro,
  },
];

const seedReports = [
  {
    trailName: "Sendero a Confluencia",
    issue_summary: "Barro y rocas sueltas",
    severity: "Media",
    trail_state: "Precaucion",
    cause: "Lluvia",
    details: "Tramo humedo en sectores de bosque.",
    daysAgo: 1,
  },
  {
    trailName: "Volcan Lanin - Base a Refugio BIM",
    issue_summary: "Sendero transitable",
    severity: "Leve",
    trail_state: "Transitable",
    cause: "Mantenimiento",
    details: "Buena senalizacion en los cruces principales.",
    daysAgo: 2,
  },
  {
    trailName: "Garganta del Diablo de Tilcara",
    issue_summary: "Nieve o hielo",
    severity: "Alta",
    trail_state: "Paso dificil",
    cause: "Deshielo",
    details: "Precaucion en el ascenso final.",
    daysAgo: 3,
  },
  {
    trailName: "Ascenso Cerro Tres Picos",
    issue_summary: "Viento fuerte",
    severity: "Media",
    trail_state: "Precaucion",
    cause: "Viento",
    details: "Rafagas cerca del mirador.",
    daysAgo: 4,
  },
  {
    trailName: "Sendero El Mollar - El Palmar",
    issue_summary: "Barro",
    severity: "Media",
    trail_state: "Precaucion",
    cause: "Lluvia",
    details: "Piso resbaladizo en bajadas.",
    daysAgo: 5,
  },
  {
    trailName: "Caminata al Cerro Morado",
    issue_summary: "Transitable con mucha humedad",
    severity: "Leve",
    trail_state: "Transitable",
    cause: "Lluvia",
    details: "Pasarelas humedas.",
    daysAgo: 6,
  },
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
  for (const trail of [...seedTrailData, ...additionalTrails]) {
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

const seedTrailReports = async () => {
  const { rows: existing } = await query("SELECT COUNT(*)::int AS count FROM trail_reports");

  if (existing[0].count > 0) return;

  for (const report of seedReports) {
    const { rows: trailRows } = await query("SELECT id FROM trails WHERE name = $1", [
      report.trailName,
    ]);
    const trail = trailRows[0];

    if (!trail) continue;

    await query(
      `
        INSERT INTO trail_reports (
          trail_id, issue_summary, severity, trail_state, cause,
          blocks_path, details, reporter_name, created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now() - ($9 || ' days')::interval)
      `,
      [
        trail.id,
        report.issue_summary,
        report.severity,
        report.trail_state,
        report.cause,
        false,
        report.details,
        "Senderista verificado",
        report.daysAgo,
      ]
    );
  }
};

const seedDatabase = async () => {
  await migrateLegacyTrailNames();
  await seedTrails();
  await seedTrailReports();
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
